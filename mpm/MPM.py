# Import packages
import numpy as np
import warp as wp
# Import source
from Scene import Scene
from Body import Plane
import linalg
import init_properties
import rasterize
import particle_updates
import grid_functions
import grid_updates
import handle_collisions
import time

class MPM:
    scene: Scene
    p: dict     # parameters
    pp: dict    # particle properties
    num_p: float
    gp: dict    # grid properties
    num_g: float
    interp: dict
    frame: int

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        E0 = scene.initial_young_modulus
        nu = scene.poisson_ratio
        mu0 = E0 / (2 * (1 + nu))
        lam0 = E0 * nu / ((1 + nu) * (1 - nu))
        self.p = {
            "dt": scene.dt,
            "h": scene.spacing,
            "alpha": scene.alpha,
            "lb": 1.0-scene.theta_c,
            "ub": 1.0+scene.theta_s,
            "zeta": float(scene.hardening_coefficient),
            "mu0": mu0,
            "lam0": lam0,
            "init_density": scene.initial_density,
            "init_ym": scene.initial_young_modulus,
            "poisson_ratio": scene.poisson_ratio
        }
        self.num_p = len(scene.mass)
        self.pp = {
            "mass": scene.mass,
            "volume": np.empty(shape=self.num_p, dtype=np.float32),
            "density": np.empty(shape=self.num_p, dtype=np.float32),
            "position": scene.position,
            "velocity": scene.velocity,
            "grad_velocity": np.zeros(shape=(self.num_p,2,2), dtype=np.float32),
            "viWi": np.zeros(shape=(self.num_p,2), dtype=np.float32),
            "F": np.zeros(shape=(self.num_p,2,2), dtype=np.float32),
            "J": np.ones(shape=self.num_p, dtype=np.float32),
            "FE": np.zeros(shape=(self.num_p,2,2), dtype=np.float32),
            "JE": np.ones(shape=self.num_p, dtype=np.float32),
            "FP": np.zeros(shape=(self.num_p,2,2), dtype=np.float32),
            "JP": np.ones(shape=self.num_p, dtype=np.float32),
            "mu": np.empty(shape=self.num_p, dtype=np.float32),
            "lam": np.empty(shape=self.num_p, dtype=np.float32)
        }
        for i in range(self.num_p):
            self.pp["F"][i] = np.eye(2, dtype=float)
            self.pp["FE"][i] = np.eye(2, dtype=float)
            self.pp["FP"][i] = np.eye(2, dtype=float)
        self.num_g = len(scene.grid)
        self.gp = {
            "position": scene.grid,
            "velocity": np.empty(shape=(self.num_g,2), dtype=np.float32),
            "mass": np.empty(shape=self.num_g, dtype=np.float32),
            "density": np.empty(shape=self.num_g, dtype=np.float32)
        }
        self.interp = {
            "wip": np.empty(shape=(self.num_g, self.num_p), dtype=np.float32),
            "gwip": np.empty(shape=(self.num_g, self.num_p, 2), dtype=np.float32)
        }
        self.bodies = scene.bodies
        self.frame = 0

    def get_position(self):
        return np.array(self.pp["position"])

    def init_animation(self, implicit=False, device="cpu"):
        wp.init()
        self.move_to_device(device=device)

    def move_to_device(self, device="cpu"):
        # Move particle properties
        self.pp["mass"] = wp.array(self.pp["mass"], dtype=wp.float32, device=device)
        self.pp["volume"] = wp.array(self.pp["volume"], dtype=wp.float32, device=device)
        self.pp["density"] = wp.array(self.pp["density"], dtype=wp.float32, device=device)
        self.pp["position"] = wp.array(self.pp["position"], dtype=wp.vec2, device=device)
        self.pp["velocity"] = wp.array(self.pp["velocity"], dtype=wp.vec2, device=device)
        self.pp["grad_velocity"] = wp.array(self.pp["grad_velocity"], dtype=wp.mat22, device=device)
        self.pp["viWi"] = wp.array(self.pp["viWi"], dtype=wp.vec2, device=device)
        self.pp["F"] = wp.array(self.pp["F"], dtype=wp.mat22, device=device)
        self.pp["FE"] = wp.array(self.pp["FE"], dtype=wp.mat22, device=device)
        self.pp["JE"] = wp.array(self.pp["JE"], dtype=wp.float32, device=device)
        self.pp["FP"] = wp.array(self.pp["FP"], dtype=wp.mat22, device=device)
        self.pp["JP"] = wp.array(self.pp["JP"], dtype=wp.float32, device=device)
        self.pp["mu"] = wp.array(self.pp["mu"], dtype=wp.float32, device=device)
        self.pp["lam"] = wp.array(self.pp["lam"], dtype=wp.float32, device=device)
        # Move grid properties
        self.gp["position"] = wp.array(self.gp["position"], dtype=wp.vec2, device=device)
        self.gp["velocity"] = wp.array(self.gp["velocity"], dtype=wp.vec2, device=device)
        self.gp["mass"] = wp.array(self.gp["mass"], dtype=wp.float32, device=device)
        self.gp["density"] = wp.array(self.gp["density"], dtype=wp.float32, device=device)
        # Move interpolation values
        self.interp["wip"] = wp.array(self.interp["wip"], dtype=wp.float32, device=device)
        self.interp["gwip"] = wp.array(self.interp["gwip"], dtype=wp.vec2, device=device)

    def reset_scratchpad(self, device="cpu"):
        self.gp["mass"] = wp.zeros_like(self.gp["mass"])
        self.gp["velocity"] = wp.zeros_like(self.gp["velocity"])

    def step(self, implicit=False, device="cpu") -> None:
        """
        Execute one time step.
        """
        # Step 0: reset scratchpad
        self.reset_scratchpad(device=device)
        # Step 1: rasterize particle data to the grid
        #start = time.time()
        ## Update values
        wp.launch(kernel=grid_functions.construct_interpolations,
                  dim=[self.num_g, self.num_p],
                  inputs=[self.interp["wip"], self.interp["gwip"], self.gp["position"], self.pp["position"], self.p["h"]],
                  device=device)
        wp.launch(kernel=rasterize.rasterize_mass,
                  dim=self.num_g,
                  inputs=[self.pp["mass"], self.interp["wip"], self.gp["mass"]],
                  device=device)
        wp.launch(kernel=rasterize.rasterize_velocity,
                  dim=self.num_g,
                  inputs=[self.pp["mass"], self.pp["velocity"], self.interp["wip"], self.gp["mass"], self.gp["velocity"]],
                  device=device)
        ## Make checks
        mass_check = wp.empty(shape=self.num_g, dtype=wp.int8, device=device)
        wp.launch(kernel=linalg.is_positive_1d,
                  dim=self.num_g,
                  inputs=[mass_check, self.gp["mass"]],
                  device=device)
        wip_check = wp.empty(shape=(self.num_g, self.num_p), dtype=wp.int8, device=device)
        wp.launch(kernel=linalg.is_positive_2d,
                  dim=[self.num_g, self.num_p],
                  inputs=[wip_check, self.interp["wip"]],
                  device=device)
        #print("Step 1 took " + str(time.time() - start) + " to run")

        # Step 2: compute particle volumes and densities
        if self.frame == 0:
            #start = time.time()
            wp.launch(kernel=init_properties.init_cell_density,
                      dim=self.num_g,
                      inputs=[self.gp["density"], self.gp["mass"], self.p["h"]],
                      device=device)
            wp.launch(kernel=init_properties.init_particle_density,
                      dim=self.num_p,
                      inputs=[self.pp["density"], self.gp["mass"], self.interp["wip"].transpose(), self.p["h"]],
                      device=device)
            wp.launch(kernel=init_properties.init_particle_volume,
                      dim=self.num_p,
                      inputs=[self.pp["volume"], self.pp["mass"], self.pp["density"]],
                      device=device)
            #print("Step 2 took " + str(time.time() - start) + " to run")

        # Step 3: compute grid forces
        #start = time.time()
        ## Compute shifted elastic deformation
        particle_updates.update_grad_velocity(self.pp["grad_velocity"], self.gp["velocity"], self.interp["gwip"].transpose(), wip_check.transpose())
        fe_shifted = wp.zeros_like(self.pp["FE"])
        wp.copy(fe_shifted, self.pp["FE"])
        wp.launch(kernel=particle_updates.shift_deformation,
                  dim=self.num_p,
                  inputs=[fe_shifted, self.pp["grad_velocity"], self.p["dt"]],
                  device=device)
        je_shifted = wp.zeros_like(self.pp["JE"], device=device)
        wp.launch(kernel=linalg.array_determinant,
                  dim=self.num_p,
                  inputs=[je_shifted, fe_shifted],
                  device=device)
        ## Compute stresses
        stresses = wp.zeros_like(self.pp["F"], device=device)
        wp.launch(kernel=particle_updates.construct_lame,
                  dim=self.num_p,
                  inputs=[self.pp["mu"], self.pp["lam"], self.pp["JP"], self.p["mu0"], self.p["lam0"], self.p["zeta"]],
                  device=device)
        particle_updates.get_stresses(stresses, fe_shifted, je_shifted, self.pp["FP"], self.pp["JP"], self.pp["mu"], self.pp["lam"])
        ## Compute grid forces
        grid_forces = wp.zeros_like(self.gp["velocity"], device=device)
        wp.launch(kernel=grid_updates.compute_grid_forces,
                  dim=self.num_g,
                  inputs=[grid_forces, self.pp["volume"], self.interp["gwip"], stresses, mass_check],
                  device=device)
        #print("Step 3 took " + str(time.time() - start) + " to run")

        # Step 4: update velocities on grid
        #start = time.time()
        vg_temp = wp.zeros_like(self.gp["velocity"])
        wp.launch(kernel=grid_updates.update_grid_velocities_with_ext_forces,
                  dim=self.num_g,
                  inputs=[vg_temp, self.gp["velocity"], self.gp["mass"], grid_forces, wp.vec2(0.0,-9.81), self.p["dt"]],
                  device=device)
        #print("Step 4 took " + str(time.time() - start) + " to run")

        # Step 5: handle grid-based body collisions
        #start = time.time()
        ## Put necessary resources onto CPU
        grid_coords = self.p["h"] * self.gp["position"].numpy()
        grid_masses = self.gp["mass"].numpy()
        velocities = vg_temp.numpy()
        velocities = handle_collisions.handle_grid_collisions(grid_coords, velocities,  self.p["dt"], self.bodies, grid_masses)
        #print("Step 5 took " + str(time.time() - start) + " to run")

        # Step 6: solve the linear system
        #start = time.time()
        if not implicit:
            vg_temp = wp.array(velocities, dtype=wp.vec2, device=device)
            new_vg = wp.zeros_like(vg_temp, device=device)
            wp.launch(kernel=grid_updates.solve_grid_velocity_explicit,
                      dim=self.num_g,
                      inputs=[new_vg, vg_temp],
                      device=device)
        else:
            velocities = grid_updates.solve_grid_velocity_implicit(velocities,
                                                      self.gp["mass"].numpy(),
                                                      self.interp["gwip"].numpy(),
                                                      self.pp["FE"].numpy(),
                                                      self.pp["FP"].numpy(),
                                                      self.pp["volume"].numpy(),
                                                      self.p["dt"],
                                                      1.0,
                                                      self.p["mu0"],
                                                      self.p["lam0"],
                                                      self.p["zeta"])
            new_vg = wp.array(velocities, dtype=wp.vec2, device=device)
        #print("Step 6 took " + str(time.time() - start) + " to run")

        # Step 7: update deformation gradient
        #start = time.time()
        ## Update matrices
        particle_updates.update_grad_velocity(self.pp["grad_velocity"], new_vg, self.interp["gwip"].transpose(), wip_check.transpose())
        particle_updates.update_deformations(self.pp["FE"],
                                             self.pp["FP"],
                                             self.pp["F"],
                                             self.pp["grad_velocity"],
                                             self.p["dt"],
                                             self.p["lb"],
                                             self.p["ub"],
                                             device=device)
        ## Update determinants
        wp.launch(kernel=linalg.array_determinant,
                  dim=self.num_p,
                  inputs=[self.pp["JE"], self.pp["FE"]],
                  device=device)
        wp.launch(kernel=linalg.array_determinant,
                  dim=self.num_p,
                  inputs=[self.pp["JP"], self.pp["FP"]],
                  device=device)
        #print(max(np.array(self.pp["JE"])), max(np.array(self.pp["JP"])))
        #print("Step 7 took " + str(time.time() - start) + " to run")

        # Step 8: update particle velocities
        #start = time.time()
        if self.frame == 0:
            particle_updates.compute_vW(self.pp["viWi"], self.gp["velocity"], self.interp["wip"].transpose())
        new_viWi = wp.zeros_like(self.pp["viWi"])
        particle_updates.compute_vW(new_viWi, new_vg, self.interp["wip"].transpose())
        wp.launch(kernel=particle_updates.update_particle_velocity,
                  dim=self.num_p,
                  inputs=[self.pp["velocity"], new_viWi, self.pp["viWi"], self.p["alpha"]],
                  device=device)
        self.pp["viWi"] = new_viWi
        #print("Step 8 took " + str(time.time() - start) + " to run")

        # Step 9: particle-based body collisions
        #start = time.time()
        particle_positions = self.pp["position"].numpy()
        particle_velocities = self.pp["velocity"].numpy()
        new_vp = handle_collisions.handle_particle_collisions(particle_positions, particle_velocities, self.p["dt"], self.bodies)
        self.pp["velocity"] = wp.array(new_vp, dtype=wp.vec2, device=device)
        #print("Step 9 took " + str(time.time() - start) + " to run")

        # Step 10: update particle positions
        #start = time.time()
        wp.launch(kernel=particle_updates.update_particle_position,
                  dim=self.num_p,
                  inputs=[self.pp["position"], self.pp["velocity"], self.p["dt"]],
                  device=device)
        #print("Step 10 took " + str(time.time() - start) + " to run")

        # Clean up
        self.frame += 1
