"""Trajectory fitting: parabola (no drag) and point-mass with quadratic drag.

Units: inches, seconds, inches/second. Z is up.
"""

from __future__ import annotations

import math
from typing import Union

import numpy as np
from scipy.optimize import least_squares

from .field_constants import (
    AIR_DENSITY_KG_M3,
    DRAG_CD_DEFAULT,
    GRAVITY_IPS2,
    NECTAR_DIAMETER,
    NECTAR_MASS_G,
    POLLEN_DIAMETER,
    POLLEN_MASS_G,
)
from .models import BallType, DragFit, ParabolaFit, Point3D, Track3D

IN_TO_M = 0.0254
K_MAX_PER_IN = 0.01


def _as_array(track: Union[Track3D, np.ndarray]) -> np.ndarray:
    """Return an (N,4) float array [t, x, y, z]."""
    if isinstance(track, Track3D):
        arr = np.array([[p.t, p.x, p.y, p.z] for p in track.points], float)
    else:
        arr = np.asarray(track, float)
    if arr.ndim != 2 or arr.shape[1] != 4:
        raise ValueError("track must be (N,4) [t,x,y,z]")
    if arr.shape[0] < 4:
        raise ValueError("need at least 4 points to fit a trajectory")
    return arr


def _shot_direction(xy: np.ndarray) -> np.ndarray:
    """Unit horizontal direction by PCA, oriented first point -> last point."""
    centered = xy - xy.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    d = vt[0]
    if float(np.dot(xy[-1] - xy[0], d)) < 0.0:
        d = -d
    return d


def fit_parabola(track: Union[Track3D, np.ndarray]) -> ParabolaFit:
    """Fit z = a s^2 + b s + c in the vertical shot plane.

    s is horizontal distance along the PCA direction from the first point.
    Exit speed comes from the time parameterization: s(t) linear gives v_h,
    and z(t) = z0 + vz*t - g/2 t^2 (g fixed) gives vz at the first sample.
    """
    arr = _as_array(track)
    t = arr[:, 0] - arr[0, 0]
    xy = arr[:, 1:3]
    z = arr[:, 3]
    d = _shot_direction(xy)
    s = (xy - xy[0]) @ d

    a, b, c = np.polyfit(s, z, 2)
    resid = z - (a * s * s + b * s + c)
    rmse = float(np.sqrt(np.mean(resid**2)))

    vh = float(np.polyfit(t, s, 1)[0])
    # z + g/2 t^2 = z0 + vz t  (linear in t)
    vz, _z0 = np.polyfit(t, z + 0.5 * GRAVITY_IPS2 * t * t, 1)
    speed = math.hypot(vh, float(vz))
    angle = math.degrees(math.atan(float(b)))
    return ParabolaFit(a=float(a), b=float(b), c=float(c), rmse_in=rmse,
                       launch_angle_deg=angle, exit_speed_ips=speed)


def _accel(v: np.ndarray, k: float) -> np.ndarray:
    sp = float(np.sqrt(v @ v))
    return np.array([-k * sp * v[0], -k * sp * v[1], -GRAVITY_IPS2 - k * sp * v[2]])


def _rk4_step(p: np.ndarray, v: np.ndarray, k: float, h: float):
    a1 = _accel(v, k)
    k1p, k1v = v, a1
    v2 = v + 0.5 * h * k1v
    k2p, k2v = v2, _accel(v2, k)
    v3 = v + 0.5 * h * k2v
    k3p, k3v = v3, _accel(v3, k)
    v4 = v + h * k3v
    k4p, k4v = v4, _accel(v4, k)
    p_new = p + h / 6.0 * (k1p + 2 * k2p + 2 * k3p + k4p)
    v_new = v + h / 6.0 * (k1v + 2 * k2v + 2 * k3v + k4v)
    return p_new, v_new


_COARSE_STEP_S = 1 / 60       # RK4 node spacing used for densely sampled (high fps) tracks
_USE_COARSE = True


def _integrate_at(p0, v0, k: float, times: np.ndarray, max_step: float = 1 / 60) -> np.ndarray:
    """Positions (N,3) at ascending `times` (relative to launch, times[0] may be 0).

    Same RK4 scheme as `_rk4_step`, written with scalars: it runs hundreds of times per drag
    fit and holds the GIL, so the numpy-per-step version starved the camera threads. When the
    samples are much denser than `_COARSE_STEP_S` (240 fps footage) the trajectory is
    integrated on a 1/60 s grid and read at the sample times with cubic Hermite interpolation
    (positions and velocities are known at the nodes; interpolation error << 1e-4 in for a
    ball flight), which is 4x fewer RK4 steps for the same data.
    """
    times = np.asarray(times, float)
    n_t = len(times)
    dense = n_t > 8 and times[-1] > 0 and float(np.min(np.diff(times))) < 0.6 * _COARSE_STEP_S
    if _USE_COARSE and dense and max_step >= _COARSE_STEP_S - 1e-12:
        return _integrate_coarse(p0, v0, k, times)
    px, py, pz = (float(x) for x in p0)
    vx, vy, vz = (float(x) for x in v0)
    out = np.empty((n_t, 3))
    tc = 0.0
    for i, tt in enumerate(times):
        span = float(tt) - tc
        if span > 0:
            n = max(1, int(math.ceil(span / max_step)))
            px, py, pz, vx, vy, vz = _rk4_n(px, py, pz, vx, vy, vz, k, span / n, n)
            tc = float(tt)
        out[i, 0], out[i, 1], out[i, 2] = px, py, pz
    return out


def _rk4_n(px, py, pz, vx, vy, vz, k, h, n):
    """`n` RK4 steps of size `h` of a = -g z_hat - k|v|v; returns (p, v) as six floats."""
    g = GRAVITY_IPS2
    sqrt = math.sqrt
    h2, h6 = 0.5 * h, h / 6.0
    for _ in range(n):
        s1 = k * sqrt(vx * vx + vy * vy + vz * vz)
        a1x, a1y, a1z = -s1 * vx, -s1 * vy, -g - s1 * vz
        v2x, v2y, v2z = vx + h2 * a1x, vy + h2 * a1y, vz + h2 * a1z
        s2 = k * sqrt(v2x * v2x + v2y * v2y + v2z * v2z)
        a2x, a2y, a2z = -s2 * v2x, -s2 * v2y, -g - s2 * v2z
        v3x, v3y, v3z = vx + h2 * a2x, vy + h2 * a2y, vz + h2 * a2z
        s3 = k * sqrt(v3x * v3x + v3y * v3y + v3z * v3z)
        a3x, a3y, a3z = -s3 * v3x, -s3 * v3y, -g - s3 * v3z
        v4x, v4y, v4z = vx + h * a3x, vy + h * a3y, vz + h * a3z
        s4 = k * sqrt(v4x * v4x + v4y * v4y + v4z * v4z)
        a4x, a4y, a4z = -s4 * v4x, -s4 * v4y, -g - s4 * v4z
        px += h6 * (vx + 2 * v2x + 2 * v3x + v4x)
        py += h6 * (vy + 2 * v2y + 2 * v3y + v4y)
        pz += h6 * (vz + 2 * v2z + 2 * v3z + v4z)
        vx += h6 * (a1x + 2 * a2x + 2 * a3x + a4x)
        vy += h6 * (a1y + 2 * a2y + 2 * a3y + a4y)
        vz += h6 * (a1z + 2 * a2z + 2 * a3z + a4z)
    return px, py, pz, vx, vy, vz


def _integrate_coarse(p0, v0, k: float, times: np.ndarray) -> np.ndarray:
    t_end = float(times[-1])
    n = max(1, int(math.ceil(t_end / _COARSE_STEP_S)))
    h = t_end / n
    nodes = np.empty((n + 1, 6))
    st = (*(float(x) for x in p0), *(float(x) for x in v0))
    nodes[0] = st
    for j in range(1, n + 1):
        st = _rk4_n(*st, k, h, 1)
        nodes[j] = st
    j = np.minimum((times / h).astype(int), n - 1)
    j = np.maximum(j, 0)
    u = ((times - j * h) / h)[:, None]
    p_a, v_a = nodes[j, 0:3], nodes[j, 3:6]
    p_b, v_b = nodes[j + 1, 0:3], nodes[j + 1, 3:6]
    u2, u3 = u * u, u * u * u
    h00, h10 = 2 * u3 - 3 * u2 + 1, u3 - 2 * u2 + u
    h01, h11 = -2 * u3 + 3 * u2, u3 - u2
    return h00 * p_a + h10 * h * v_a + h01 * p_b + h11 * h * v_b


def simulate(p0, v0, k: float, dt: float, t_max: float) -> np.ndarray:
    """RK4 point-mass trajectory with a = -g z_hat - k|v|v.

    Returns (N,4) [t,x,y,z] sampled every dt from 0 to t_max inclusive.
    """
    n = int(round(t_max / dt))
    p = np.asarray(p0, float).copy()
    v = np.asarray(v0, float).copy()
    out = np.empty((n + 1, 4))
    out[0] = [0.0, *p]
    for i in range(1, n + 1):
        p, v = _rk4_step(p, v, k, dt)
        out[i] = [i * dt, *p]
    return out


def fit_drag(track: Union[Track3D, np.ndarray]) -> DragFit:
    """Nonlinear least squares for p0, v0, k of the quadratic-drag model.

    p0 and v0 refer to the first sample time. Residuals cover all three axes.
    """
    arr = _as_array(track)
    t = arr[:, 0] - arr[0, 0]
    pos = arr[:, 1:4]
    d = _shot_direction(arr[:, 1:3])
    vh = float(np.polyfit(t, (arr[:, 1:3] - arr[0, 1:3]) @ d, 1)[0])
    vz = float(np.polyfit(t, pos[:, 2] + 0.5 * GRAVITY_IPS2 * t * t, 1)[0])
    v_init = np.array([vh * d[0], vh * d[1], vz])
    p_init = pos[0].copy()

    kscale = 1e-3

    def resid(x):
        sim = _integrate_at(x[0:3], x[3:6], x[6] * kscale, t)
        return (sim - pos).ravel()

    x0 = np.concatenate([p_init, v_init, [0.5]])  # k0 = 5e-4/in
    lo = np.concatenate([p_init - 50, v_init - 1000, [0.0]])
    hi = np.concatenate([p_init + 50, v_init + 1000, [K_MAX_PER_IN / kscale]])
    sol = least_squares(resid, x0, bounds=(lo, hi), x_scale=np.array([1, 1, 1, 50, 50, 50, 1.0]))
    rmse = float(np.sqrt(np.mean(sol.fun**2)))
    return DragFit(v0=tuple(float(x) for x in sol.x[3:6]),
                   p0=tuple(float(x) for x in sol.x[0:3]),
                   k_per_in=float(sol.x[6] * kscale), rmse_in=rmse)


def drag_k_for(ball_type: BallType, cd: float = DRAG_CD_DEFAULT) -> float:
    """Drag constant k in 1/inch for a = -k |v| v with v in in/s, a in in/s^2.

    SI: k_SI = 0.5 * rho * Cd * A / m  [1/m], A = pi r^2 (r in m), m in kg.
    In SI, a_m = k_SI |v_m| v_m. With v_m = 0.0254 v_in and a_in = a_m / 0.0254:
    a_in = k_SI * 0.0254 * |v_in| v_in, so k_in = k_SI * 0.0254 (= k_SI / 39.37).
    UNKNOWN is treated as pollen.
    """
    if ball_type == BallType.NECTAR:
        diameter_in, mass_kg = NECTAR_DIAMETER, NECTAR_MASS_G / 1000.0
    else:
        diameter_in, mass_kg = POLLEN_DIAMETER, POLLEN_MASS_G / 1000.0
    r_m = 0.5 * diameter_in * IN_TO_M
    area = math.pi * r_m * r_m
    k_si = 0.5 * AIR_DENSITY_KG_M3 * cd * area / mass_kg
    return k_si * IN_TO_M


def exit_speed_at_first_visible(track: Union[Track3D, np.ndarray]) -> tuple[float, Point3D]:
    """Speed (in/s) at the first point from a quadratic fit of the first 5 points."""
    arr = _as_array(track)
    m = arr[: min(5, len(arr))]
    t = m[:, 0] - m[0, 0]
    vel = np.empty(3)
    for ax in range(3):
        coeffs = np.polyfit(t, m[:, 1 + ax], 2)
        vel[ax] = coeffs[1]  # derivative at t=0
    pt = Point3D(t=float(m[0, 0]), x=float(m[0, 1]), y=float(m[0, 2]), z=float(m[0, 3]))
    return float(np.linalg.norm(vel)), pt


def apex(track_or_fit: Union[Track3D, np.ndarray, ParabolaFit]) -> float:
    """Maximum height z. For a fit: the parabola vertex if it opens downward
    and lies at s >= 0, else c. For a track: the fit vertex if at s >= 0
    (possibly extrapolated), else the maximum observed z."""
    if isinstance(track_or_fit, ParabolaFit):
        f = track_or_fit
        if f.a < 0 and f.b > 0:
            return float(f.c - f.b * f.b / (4.0 * f.a))
        return float(f.c)
    arr = _as_array(track_or_fit)
    f = fit_parabola(arr)
    if f.a < 0 and f.b > 0:
        return float(f.c - f.b * f.b / (4.0 * f.a))
    return float(np.max(arr[:, 3]))


def equation_string(fit: ParabolaFit) -> str:
    return f"z = {fit.a:.4f} s^2 + {fit.b:.2f} s + {fit.c:.1f} (in)".replace("+ -", "- ")
