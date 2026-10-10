import math

import numpy as np
import pytest

from hiveshot import physics
from hiveshot.field_constants import GRAVITY_IPS2
from hiveshot.models import BallType, ParabolaFit, Point3D, Track3D

V0 = np.array([200.0, 100.0, 300.0])
P0 = np.array([10.0, -20.0, 12.0])


def ballistic(noise, seed=0, hz=60.0, dur=0.8):
    t = np.arange(0, dur, 1 / hz)
    pos = P0[None, :] + V0[None, :] * t[:, None]
    pos[:, 2] -= 0.5 * GRAVITY_IPS2 * t * t
    rng = np.random.default_rng(seed)
    pos = pos + rng.normal(0, noise, pos.shape)
    return np.column_stack([t, pos])


def test_parabola_recovers_launch_parameters():
    arr = ballistic(0.1)
    f = physics.fit_parabola(arr)
    vh = math.hypot(V0[0], V0[1])
    true_speed = float(np.linalg.norm(V0))
    true_angle = math.degrees(math.atan2(V0[2], vh))
    assert f.exit_speed_ips == pytest.approx(true_speed, rel=0.02)
    assert abs(f.launch_angle_deg - true_angle) < 1.0
    assert f.a == pytest.approx(-GRAVITY_IPS2 / (2 * vh**2), rel=0.03)
    assert f.rmse_in < 0.3


def test_parabola_accepts_track3d_and_rejects_short():
    arr = ballistic(0.0)
    tr = Track3D(1, [Point3D(*row) for row in arr])
    f = physics.fit_parabola(tr)
    assert f.rmse_in < 1e-6
    assert f.c == pytest.approx(P0[2], abs=1e-6)
    with pytest.raises(ValueError):
        physics.fit_parabola(arr[:3])


def test_azimuth_direction_independent_of_sign():
    # A shot travelling toward -X must still give a positive launch angle.
    arr = ballistic(0.0)
    arr[:, 1] = -arr[:, 1]
    f = physics.fit_parabola(arr)
    assert f.launch_angle_deg > 0
    assert f.exit_speed_ips == pytest.approx(float(np.linalg.norm(V0)), rel=1e-3)


def test_simulate_without_drag_matches_closed_form():
    sim = physics.simulate(P0, V0, 0.0, 1 / 60, 0.8)
    t = sim[:, 0]
    expected_z = P0[2] + V0[2] * t - 0.5 * GRAVITY_IPS2 * t * t
    assert np.allclose(sim[:, 3], expected_z, atol=1e-6)
    assert np.allclose(sim[:, 1], P0[0] + V0[0] * t, atol=1e-6)


def test_simulate_drag_slows_ball():
    free = physics.simulate(P0, V0, 0.0, 1 / 60, 0.8)
    drag = physics.simulate(P0, V0, 0.002, 1 / 60, 0.8)
    assert drag[-1, 1] < free[-1, 1]


def test_fit_drag_recovers_k_and_v0():
    k_true = 0.002
    sim = physics.simulate(P0, V0, k_true, 1 / 60, 1.0)
    rng = np.random.default_rng(1)
    noisy = sim.copy()
    noisy[:, 1:] += rng.normal(0, 0.1, noisy[:, 1:].shape)
    d = physics.fit_drag(noisy)
    assert d.k_per_in == pytest.approx(k_true, rel=0.25)
    assert np.linalg.norm(np.array(d.v0) - V0) / np.linalg.norm(V0) < 0.03
    assert d.rmse_in < 0.3


def test_fit_drag_noiseless_is_accurate():
    sim = physics.simulate(P0, V0, 0.002, 1 / 60, 1.0)
    d = physics.fit_drag(sim)
    assert d.k_per_in == pytest.approx(0.002, rel=0.02)
    assert d.rmse_in < 0.05


def test_drag_k_for_pollen_matches_reference():
    expected = 0.0558 / 39.37
    assert physics.drag_k_for(BallType.POLLEN) == pytest.approx(expected, rel=0.20)
    # Linear in Cd.
    assert physics.drag_k_for(BallType.POLLEN, cd=1.1) == pytest.approx(
        2 * physics.drag_k_for(BallType.POLLEN), rel=1e-9)
    ratio = physics.drag_k_for(BallType.NECTAR) / physics.drag_k_for(BallType.POLLEN)
    assert 0.3 < ratio < 3


def test_exit_speed_at_first_visible():
    arr = ballistic(0.0)
    speed, pt = physics.exit_speed_at_first_visible(arr)
    assert speed == pytest.approx(float(np.linalg.norm(V0)), rel=1e-3)
    assert (pt.x, pt.y, pt.z) == pytest.approx(tuple(P0), abs=1e-6)


def test_apex():
    arr = ballistic(0.0, dur=1.0)
    true_apex = P0[2] + V0[2] ** 2 / (2 * GRAVITY_IPS2)
    assert physics.apex(arr) == pytest.approx(true_apex, rel=1e-3)
    assert physics.apex(physics.fit_parabola(arr)) == pytest.approx(true_apex, rel=1e-3)


def test_equation_string():
    s = physics.equation_string(ParabolaFit(-0.0123, 0.84, 12.0, 0.0, 40.0, 300.0))
    assert s == "z = -0.0123 s^2 + 0.84 s + 12.0 (in)"
