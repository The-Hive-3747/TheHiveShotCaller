"""Application configuration (docs/api.md "Config dict shape")."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import field_constants as C
from .resources import base_dir

ROOT = base_dir()   # project root from source; bundle dir when frozen


def default_data_dir() -> Path:
    r"""Frozen: %LOCALAPPDATA%\HiveShotTracker\data (writable); from source: <repo>/data."""
    if getattr(sys, "frozen", False):
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "HiveShotTracker" / "data"
    return ROOT / "data"


SOURCE_KINDS = ("file", "device", "rtmp", "url")


class SourceConfig(BaseModel):
    cam_id: str
    kind: str = "file"                       # file | device | rtmp | url
    target: Union[str, int] = ""
    width: Optional[int] = 1920
    height: Optional[int] = 1080
    fps_hint: Optional[float] = 60
    backend: str = "auto"
    loop: bool = False
    realtime: bool = True


class RobotConfig(BaseModel):
    length: float = C.ROBOT_LENGTH
    width: float = C.ROBOT_WIDTH
    height: float = C.ROBOT_HEIGHT
    launch_exit_height: float = C.ROBOT_LAUNCH_EXIT_HEIGHT


class DetectorSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    min_radius_px: float = 4
    max_radius_px: float = 60
    pollen_hsv: list[list[int]] = [[15, 100, 100], [38, 255, 255]]
    nectar_hsv: list[list[int]] = [[125, 60, 60], [170, 255, 255]]
    motion_thresh: float = 25
    # The MOG2 motion model runs on a frame scaled by this factor (of the processed frame);
    # 1.0 = full resolution. 0.5 halves the detector cost; set 1.0 to restore the old behaviour.
    motion_scale: float = Field(0.5, gt=0.0, le=1.0)


def _default_sources() -> list[SourceConfig]:
    return [SourceConfig(cam_id=f"cam{i}", kind="file",
                         target=f"fixtures/synth_basic/cam{i}.mp4", loop=False, realtime=True)
            for i in (0, 1)]


DEFAULT_SESSION_TEMPLATE = "Practice {date} {time}"


def format_session_name(template: str, now: Optional[float] = None) -> str:
    """Fill {date} (YYYY-MM-DD) and {time} (HH:MM, local) into a session name template."""
    t = time.localtime(now)
    return template.format(date=time.strftime("%Y-%m-%d", t), time=time.strftime("%H:%M", t))


def _default_profiles() -> dict[str, dict[str, Any]]:
    """Named config patches (apply with PUT /api/config)."""
    return {"arducam_1080p90": {"sources": [
        {"cam_id": f"cam{i}", "kind": "device", "target": i, "width": 1920, "height": 1080,
         "fps_hint": 90, "backend": "msmf", "loop": False, "realtime": True}
        for i in (0, 1)]}}


def _default_intrinsics() -> dict[str, dict[str, Any]]:
    """Nominal intrinsics used for a camera that has none (first entry is used)."""
    return {"arducam_2.3mp_110": {"fx": 771.0, "fy": 771.0, "cx": 960.0, "cy": 540.0,
                                  "dist": [0.0, 0.0, 0.0, 0.0, 0.0],
                                  "width": 1920, "height": 1080}}


class AppConfig(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=_default_sources)
    calibration_path: str = "data/calibration.json"
    alliance: str = "red"
    hive_up_cell: str = "audience"
    robot: RobotConfig = Field(default_factory=RobotConfig)
    burst_gap_s: float = 1.5
    settle_time_s: float = 0.75
    detector: DetectorSection = Field(default_factory=DetectorSection)
    preview_fps: float = 15
    stitch_gap_s: float = Field(2.0, ge=0.0)       # max gap for 3D fragment stitching; 0 = off
    finalize_delay_s: float = Field(0.5, ge=0.0)   # source seconds after last 2D track closes
    session_name_template: str = DEFAULT_SESSION_TEMPLATE
    session_idle_end_min: float = Field(10.0, ge=0.0)   # end the session after this idle time; 0 = off
    autosave_csv: bool = True                      # write data/exports/<session>.csv when it ends idle
    profiles: dict[str, dict[str, Any]] = Field(default_factory=_default_profiles)
    default_intrinsics: dict[str, dict[str, Any]] = Field(default_factory=_default_intrinsics)
    # name of a profile whose `intrinsics` slot ({width,height,fx,fy,cx,cy,dist}, measured on
    # the real lens) replaces the generic default intrinsics; None = use the default
    active_profile: Optional[str] = None
    # inside wall to inside wall, measured on the real field ("measure wall to wall");
    # drives the field bounds in /api/field/geometry and the 3D viewer
    field_size_in: float = Field(144.0, ge=60.0, le=400.0)
    hive_tags_verified: bool = False               # trust the HIVE AprilTag layout (up CELL from tags)

    @field_validator("session_name_template")
    @classmethod
    def _check_template(cls, v: str) -> str:
        try:
            format_session_name(v)
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError("session_name_template may only use {date} and {time}") from e
        return v

    @model_validator(mode="after")
    def _check_sources(self) -> "AppConfig":
        seen: set[str] = set()
        for s in self.sources:
            if not s.cam_id.strip():
                raise ValueError("source cam_id must not be empty")
            if s.cam_id in seen:
                raise ValueError(f"duplicate source cam_id {s.cam_id!r}: cam_ids must be unique")
            seen.add(s.cam_id)
            if s.kind not in SOURCE_KINDS:
                raise ValueError(f"source {s.cam_id!r}: kind {s.kind!r} must be one of "
                                 + "|".join(SOURCE_KINDS))
            if isinstance(s.target, str) and not s.target.strip():
                raise ValueError(f"source {s.cam_id!r}: target must not be empty")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load(path: Union[str, Path]) -> AppConfig:
    p = Path(path)
    if not p.exists():
        return AppConfig()
    return AppConfig.model_validate(json.loads(p.read_text(encoding="utf-8")))


def save(path: Union[str, Path], cfg: AppConfig) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(p)


def merge(base: dict, patch: dict) -> dict:
    """Deep-merge dicts; lists and scalars in patch replace."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_path(p: Union[str, Path], data_dir: Path) -> Path:
    """Relative data/... maps into data_dir; other relative paths into the project root."""
    path = Path(p)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return data_dir.joinpath(*path.parts[1:])
    return ROOT / path
