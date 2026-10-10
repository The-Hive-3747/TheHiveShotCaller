"""Shared data contracts. All modules import from here; nobody redefines these.

Units: inches for length, seconds for time, inches/second for speed, degrees
for angles unless a field name ends in `_rad`. Field coordinate frame is
defined in `hiveshot.field` (origin at field center on the tile surface,
Z up, X toward the audience side, Y along the HIVE beam).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BallType(str, Enum):
    POLLEN = "pollen"
    NECTAR = "nectar"
    UNKNOWN = "unknown"


class ShotResult(str, Enum):
    MADE = "made"            # entered the up CELL and stayed in
    BOUNCE_OUT = "bounce_out"  # entered the up CELL opening, then left it
    MISS = "miss"            # never entered the up CELL opening
    UNKNOWN = "unknown"      # track lost before a decision was possible


class SourceKind(str, Enum):
    FILE = "file"
    DEVICE = "device"        # USB / capture card, by index or name
    RTMP = "rtmp"            # URL served by the bundled RTMP server
    URL = "url"              # any other ffmpeg-readable URL


@dataclass
class Detection2D:
    """One ball observation in one camera frame."""
    cam_id: str
    frame_idx: int
    t: float                 # capture timestamp, seconds, camera clock
    u: float                 # pixel x
    v: float                 # pixel y
    radius_px: float
    ball_type: BallType = BallType.UNKNOWN
    confidence: float = 1.0


@dataclass
class Track2D:
    cam_id: str
    track_id: int
    detections: list[Detection2D] = field(default_factory=list)


@dataclass
class Point3D:
    t: float                 # seconds, common clock after sync
    x: float
    y: float
    z: float
    residual_in: float = 0.0  # triangulation residual, inches


@dataclass
class Track3D:
    track_id: int
    points: list[Point3D] = field(default_factory=list)
    ball_type: BallType = BallType.UNKNOWN


@dataclass
class ParabolaFit:
    """y_up = a*s^2 + b*s + c in the vertical shot plane, where s is horizontal
    distance along the shot direction from the launch point (inches)."""
    a: float
    b: float
    c: float
    rmse_in: float
    launch_angle_deg: float
    exit_speed_ips: float    # inches per second


@dataclass
class DragFit:
    """Point-mass with quadratic drag: a = -g z_hat - k |v| v."""
    v0: tuple[float, float, float]
    p0: tuple[float, float, float]
    k_per_in: float
    rmse_in: float


@dataclass
class Shot:
    shot_id: int
    session_id: str
    t_launch: float
    burst_id: int
    burst_index: int         # 1..4 position within burst
    ball_type: BallType
    result: ShotResult
    exit_speed_ips: Optional[float]
    launch_angle_deg: Optional[float]
    launch_azimuth_deg: Optional[float]
    launch_point: Optional[tuple[float, float, float]]
    apex_z_in: Optional[float]
    parabola: Optional[ParabolaFit]
    drag: Optional[DragFit]
    track: Optional[Track3D]
    clip_path: Optional[str] = None
    notes: str = ""


@dataclass
class TipEvent:
    t: float
    session_id: str
    alliance: str            # "red" | "blue"
    new_up_cell: str         # "audience" | "far"
    caused_by_shot_id: Optional[int]


@dataclass
class CameraIntrinsics:
    cam_id: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    dist: tuple[float, ...]  # OpenCV distortion coefficients (k1 k2 p1 p2 k3 ...)
    reprojection_rmse_px: float = 0.0


@dataclass
class CameraExtrinsics:
    """Rotation (Rodrigues vector) and translation mapping field coords to
    camera coords: X_cam = R @ X_field + t. Translation in inches."""
    cam_id: str
    rvec: tuple[float, float, float]
    tvec: tuple[float, float, float]
    rmse_in: float = 0.0


@dataclass
class SessionStats:
    session_id: str
    shots: int
    made: int
    bounce_out: int
    miss: int
    unknown: int
    make_rate: float
    by_ball_type: dict[str, dict[str, int]]
    failure_order_hist: dict[int, int]   # burst_index -> count of non-made shots
    bounce_out_order_hist: dict[int, int]
    tips: int
    mean_exit_speed_ips: Optional[float]
    mean_launch_angle_deg: Optional[float]
