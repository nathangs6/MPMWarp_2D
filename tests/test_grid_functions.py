import os
import sys
test_directory = os.path.dirname(__file__)
src_dir = os.path.join(test_directory, '..', 'mpm')
sys.path.append(src_dir)
import grid_functions as src
import warp as wp
import numpy as np
TOL = 0.00001

@wp.kernel
def evaluate_N(inputs: wp.array(dtype=wp.float32), outputs: wp.array(dtype=wp.float32)) -> None:
    i = wp.tid()
    outputs[i] = src.N(inputs[i])

def test_N_first_range():
    # Test first range
    wp.init()
    #kernel_N = make_kernel(src.N, wp.float32, "n_test_kernel", src)
    test_input = [0.5, -0.5, 0.4]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_N,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [23/48, 23/48, 202/375]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL

def test_N_second_range():
    wp.init()
    test_input = [1.5, -1.8, 1.1]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_N,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [1/48, 1/750, 243/2000]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL

def test_N_third_range():
    wp.init()
    test_input = [4.0, -5.0, -2.5, -2.2]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_N,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [0.0, 0.0, 0.0, 0.0]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL

###############
### Test dN ###
###############
@wp.kernel
def evaluate_dN(inputs: wp.array(dtype=wp.float32), outputs: wp.array(dtype=wp.float32)) -> None:
    i = wp.tid()
    outputs[i] = src.dN(inputs[i])

def test_dN_first_range():
    wp.init()
    test_input = [0.5, -0.5, -0.1, 0.9]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_dN,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [-5/8, 5/8, 37/200, -117/200]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL

def test_dN_second_range():
    wp.init()
    test_input = [1.5, -1.5, -1.8, 1.1]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_dN,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [-1/8, 1/8, 1/50, -81/200]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL

def test_dN_third_range():
    wp.init()
    test_input = [4.0, -5.0, -2.5, -2.2]
    m = len(test_input)
    test_input = wp.array(test_input, dtype=wp.float32, device="cpu")
    test_output = wp.zeros(m, dtype=wp.float32, device="cpu")
    wp.launch(kernel=evaluate_dN,
              dim=m,
              inputs=[test_input, test_output],
              device="cpu")
    actual = np.array(test_output)
    expected = [0.0, 0.0, 0.0, 0.0]
    for i in range(m):
        assert abs(actual[i] - expected[i]) <= TOL


def test_construct_interpolation():
    wp.init()
    wip = wp.empty(shape=(3,4), dtype=float, device="cpu")
    gwip = wp.empty(shape=(3,4), dtype=wp.vec2, device="cpu")
    np_indices = np.array([
        [0,0],
        [2,4],
        [4,-3]], dtype=np.float32)
    i = wp.from_numpy(np_indices, dtype=wp.vec2, device="cpu")
    np_points = np.array([
        [0,0],
        [1,3],
        [0.1,0.2],
        [0.4,-0.2]], dtype=np.float32)
    p = wp.from_numpy(np_points, dtype=wp.vec2, device="cpu")
    h = 0.1
    wp.launch(kernel=src.construct_interpolations,
              dim=[3,4],
              inputs=[wip, gwip, i, p, h],
              device="cpu")
    actual = np.array(wip)
    expected = np.array([
        [4/9, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1/9]], dtype=np.float32)
    assert np.linalg.norm(actual - expected) <= TOL
