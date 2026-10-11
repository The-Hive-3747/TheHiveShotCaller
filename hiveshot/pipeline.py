"""Live pipeline: capture -> detect -> track2d -> stereo recon -> shots -> store -> events.

Threads: one worker per camera (detect + 2D track + preview + clip ring buffer) and one
reconstruction thread (every 0.5 s pairs closed tracks across the two cameras).

Dev convenience (documented): if config.calibration_path does not exist and a file source
has a sibling ``<stem>_truth.json`` (the synthetic fixtures), the calibration embedded in
that truth JSON is used. Real calibrations always take precedence.

Shot finalization: a reconstructed 3D track is finalized (classified, stored, emitted)
once its last 2D track has been closed for ``finalize_delay_s`` (default 0.5 s of source
time), unless it is a *stitch candidate*: stitching is enabled (``stitch_gap_s`` > 0) and the
track ended in mid-air (above LANDED_Z_IN and not within EXTEND_PLANE_IN of the up-CELL
opening plane), in which case it is held up to ``stitch_gap_s`` for a continuation fragment
(ball left the view and re-entered). On the regenerated fixtures (all truth points in frame)
no fragment is ever stitched; the heuristic is kept for real footage, ``stitch_gap_s=0``
disables it. Source time is used, so realtime=False runs behave like live ones.

Opening extrapolation: a ball entering the CELL vanishes from view, so a track whose last
measured point lies within EXTEND_PLANE_IN (6 in) of the opening plane (outside, approaching)
is extended ballistically by at most EXTEND_MAX_S (0.15 s) to reach the crossing, and the
shot notes say so. Tracks ending elsewhere are never extrapolated.

The detect / track2d / recon modules are imported lazily inside start() so the app still
starts if one of them is missing.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

from . import config as cfgmod
from .field import CELLS, HiveState, cell_opening_plane
from .field_constants import APRILTAG_IDS, GRAVITY_IPS2
from .ingest import Frame, MultiCapture, SourceSpec, VideoSource
from .models import (
    BallType,
    CameraExtrinsics,
    CameraIntrinsics,
    Point3D,
    ShotResult,
    SourceKind,
    TipEvent,
    Track2D,
    Track3D,
)
from .rtmp_server import RtmpServer, RtmpServerError
from .shots import (
    assign_bursts,
    build_shot,
    classify_track,
    dropped_note,
    opening_classifier,
    summarize,
)
from .stats import compute_stats, stats_to_dict
from .store import Store

log = logging.getLogger("hiveshot.pipeline")

PREVIEW_WIDTH = 960
CLIP_WIDTH = 480
CLIP_SECONDS = 3.0           # minimum ring length; see Pipeline._ring_seconds
UNASSIGNED_SESSION = "unassigned"
TIP_LINK_WINDOW_S = 3.0      # a tip is attributed to a MADE shot launched at most this long before it
STALL_AFTER_S = 2.0          # a camera without frames for this long (wall) is ignored by _clock
STOP_JOIN_S = 10.0
SAFE_LIVE_KEYS = ("burst_gap_s", "settle_time_s", "finalize_delay_s", "stitch_gap_s",
                  "robot", "preview_fps", "session_name_template", "session_idle_end_min",
                  "autosave_csv", "hive_tags_verified")
TAG_SCAN_WIDTH = 960           # AprilTag id scans run on a copy this wide (640 lost the
                               # small HIVE tags of a 1080p camera in the tests)
TAG_SCAN_PERIOD_S = 1.0       # AprilTag scans per camera at most this often (wall time)
HIVE_TAG_PERIOD_S = 0.5       # learned-HIVE-tag scans per camera (~2 Hz)
HIVE_VOTES = 3                # consecutive agreeing samples before a state change is committed
HIVE_VOTE_MIN_S = 0.25        # ... spread over at least this much wall time
HIVE_MIN_CONFIDENCE = 0.5     # tagkit.infer_hive_state confidence needed to count a vote
HIVE_MATCH_PX = 12.0          # max mean corner reprojection error to accept a learned state
HIVE_MARGIN_PX = 6.0          # the runner-up state must be worse by at least this much
PENDING_MAX_AGE_S = 10.0
RECON_PERIOD_S = 0.2
QUEUE_SECONDS = 0.3             # capture queue depth in seconds of video
QUEUE_MAX_FRAMES = 96
QUEUE_MAX_BYTES = 192 * 1024 * 1024    # per camera
CAM_PRIORITY = 2                # Windows thread priority of capture + camera threads
SWITCH_INTERVAL_S = 0.0005       # GIL hand-over interval while a pipeline runs
AUX_QUEUE_MAX = 64              # frames waiting for the preview/ring helper thread
OFFSET_REESTIMATE_S = 30.0
OFFSET_REESTIMATE_LOW_CONF_S = 3.0   # an ambiguous estimate is revisited sooner
OFFSET_CONFIDENT = 0.3
# Largest plausible camera-to-camera clock offset by source kind: two USB cameras on this PC
# share one clock; network sources (RTMP/URL) do not; recorded files are in between.
OFFSET_LAG_DEVICE_S = 0.1
OFFSET_LAG_FILE_S = 0.5
OFFSET_LAG_NETWORK_S = 2.0
UNPAIRED_MIN_HITS = 3           # a 2D track with this many detections ...
UNPAIRED_MIN_SPAN_S = 0.3       # ... over this long that finds no partner may be a lost shot
UNPAIRED_OVERLAP_S = 0.1        # ... unless a reconstructed shot covers its time (+- this)
LENS_POOR_RMSE_PX = 2.0          # lens calibration above this is "measured_poor"
LENS_OK_RMSE_PX = 1.0            # ... and between this and the above passes with a warning
MAX_LOOP_RESTARTS = 3           # camera loop restarts per minute before giving up
WATCHDOG_PERIOD_S = 2.0         # pipeline health check interval
DETECT_STALL_S = 3.0            # frames arrive but the detector has not run for this long
RECON_STALL_S = 10.0            # tracks are pending but no reconstruction cycle completed
# 3D fragment stitching (config stitch_gap_s / finalize_delay_s): a ball that leaves the
# cameras' view and re-enters is reconstructed as separate fragments; join them when a
# ballistic extrapolation of the earlier part lands on the start of the later part.
LANDED_Z_IN = 10.0
FRAG_TOL_BASE_IN = 6.0
FRAG_TOL_PER_S_IN = 15.0
# A ball entering the CELL disappears from view. If the last measured point is within
# EXTEND_PLANE_IN of the opening plane and its ballistic extrapolation crosses the opening
# within EXTEND_MAX_S, the crossing is appended so the shot can classify as made.
EXTEND_PLANE_IN = 6.0
EXTEND_MAX_S = 0.15
EXTEND_STEP_S = 1.0 / 60.0
EXTEND_STEP_IN = 1.5          # ... but at most this far along the path per step
# Moving average of the per-stage timers exposed in status()["timing"].
TIMING_ALPHA = 0.02
TIMING_STAGES = ("detect_ms", "track_ms", "preview_ms", "ring_ms")
DROP_EVENTS_MAX = 2000
SHOT_WINDOW_TAIL_S = 0.05
RING_POOL_MAX = 8


class ConfigConflict(RuntimeError):
    """Raised when a live config change cannot be applied while the pipeline runs."""


@dataclasses.dataclass
class _PendingTip:
    tip_id: int
    tip: TipEvent
    caused_by: Optional[int] = None


@dataclasses.dataclass
class _Chain:
    track: Track3D
    closed_t: float          # source time at which the last contributing 2D track closed
    fragments: int = 1


class _LockstepReader:
    """File reader with back-pressure (never drops). Used for realtime=False files so a
    fast decoder cannot overrun the processing loop. Same surface as CaptureThread."""

    def __init__(self, spec: SourceSpec, maxsize: int = 4):
        self.spec = spec
        self._q: queue.Queue[Frame] = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest: Optional[Frame] = None
        self._times: collections.deque[float] = collections.deque(maxlen=500)
        self.frames_read = 0
        self.dropped = 0
        self.reconnects = 0
        self.last_error: Optional[str] = None
        self.props: dict = {}
        self.finished = False

    def start(self) -> "_LockstepReader":
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"lockstep-{self.spec.cam_id}")
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            src = VideoSource(self.spec)
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            self.finished = True
            return
        self.props = src.props()
        try:
            while not self._stop.is_set():
                fr = src.read()
                if fr is None:
                    break
                self._latest = fr
                self.frames_read += 1
                self._times.append(time.perf_counter())
                while not self._stop.is_set():
                    try:
                        self._q.put(fr, timeout=0.05)
                        break
                    except queue.Full:
                        continue
        finally:
            src.close()
            self.finished = True

    def get(self, timeout: Optional[float] = None) -> Optional[Frame]:
        try:
            return self._q.get(timeout=timeout if timeout is not None else 0.1)
        except queue.Empty:
            return None

    def latest(self) -> Optional[Frame]:
        return self._latest

    def stats(self) -> dict:
        now = time.perf_counter()
        ts = [t for t in list(self._times) if now - t <= 2.0]     # list(): the reader appends
        fps = (len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) >= 2 and ts[-1] > ts[0] else 0.0
        return {"fps": fps, "dropped": 0, "frames_read": self.frames_read,
                "is_alive": bool(self._thread and self._thread.is_alive()),
                "last_error": self.last_error, "reconnects": 0, "props": dict(self.props)}

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self, timeout: float = 2.0) -> None:
        self.request_stop()
        if self._thread:
            self._thread.join(timeout)


def hive_state_key(alliance: str, up_cell: str) -> str:
    return f"{alliance}_{up_cell}"


HIVE_IDS = frozenset(i for ids in APRILTAG_IDS.values() for i in ids)


def _queue_depth(reader, fr) -> int:
    """Frames the capture queue may hold before it drops the oldest: about QUEUE_SECONDS of
    video (a GIL stall in another thread must not cost frames), at least 8, and within
    QUEUE_MAX_BYTES for this frame size."""
    try:
        fps = float((reader.props or {}).get("fps") or 0.0)
    except (AttributeError, TypeError, ValueError):
        fps = 0.0
    fps = fps if fps > 1.0 else 30.0
    depth = max(8, min(QUEUE_MAX_FRAMES, round(QUEUE_SECONDS * fps)))
    return int(max(8, min(depth, QUEUE_MAX_BYTES // max(1, int(fr.image.nbytes)))))


def _thread_priority(level: int, native_id: Optional[int] = None) -> None:
    """Windows thread priority (-1 below normal ... +2 highest) for the calling thread, or
    for the thread with `native_id`: camera and capture threads outrank the reconstruction,
    clip and tag threads when the CPU is contended. No-op elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentThread.restype = wintypes.HANDLE
        k32.OpenThread.restype = wintypes.HANDLE
        k32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        if native_id is None:
            k32.SetThreadPriority(k32.GetCurrentThread(), int(level))
            return
        h = k32.OpenThread(0x0020, False, int(native_id))      # THREAD_SET_INFORMATION
        if h:
            k32.SetThreadPriority(h, int(level))
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        log.debug("SetThreadPriority unavailable", exc_info=True)


_TIMER_LOCK = threading.Lock()
_TIMER_USERS = 0


def _fine_timers(on: bool) -> None:
    """Windows' default 15.6 ms timer tick turns every short sleep/wait into ~16 ms, which
    batches a 240 fps stream into bursts of four frames. Ask for 1 ms while a pipeline
    runs; a shorter GIL switch interval keeps the camera threads from queueing behind the
    reconstruction thread."""
    global _TIMER_USERS
    with _TIMER_LOCK:
        if on:
            _TIMER_USERS += 1
            if _TIMER_USERS == 1:
                sys.setswitchinterval(SWITCH_INTERVAL_S)
                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.winmm.timeBeginPeriod(1)
                    except Exception:  # noqa: BLE001
                        log.debug("timeBeginPeriod unavailable", exc_info=True)
        elif _TIMER_USERS > 0:
            _TIMER_USERS -= 1
            if _TIMER_USERS == 0:
                sys.setswitchinterval(0.005)
                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.winmm.timeEndPeriod(1)
                    except Exception:  # noqa: BLE001
                        pass



_SOURCE_RANK = ["none", "default_intrinsics", "fixture", "click", "hive", "kit"]


def _source_of_solve(rec: Optional[dict]) -> str:
    """Provenance word of a recorded extrinsics solve ({source, tags_used})."""
    if not rec:
        return "click"                      # solved before solves were recorded
    ids = [int(t) for t in rec.get("tags_used", [])]
    if rec.get("source") == "clicks" or not ids:
        return "click"
    return "kit" if any(100 <= t <= 103 for t in ids) else "hive"


def calibration_state() -> dict[str, str]:
    """{alliance: up cell} the cameras are calibrated against: `field.CALIBRATION_STATE`
    (both audience CELLs up), whatever the pipeline's current HIVE state is."""
    from . import field
    cs = getattr(field, "CALIBRATION_STATE", None) or {}
    out = {al: "audience" for al in field.ALLIANCES}
    for al, hs in dict(cs).items():
        out[str(al)] = str(getattr(hs, "up_cell", hs))
    return out


def calibration_hive_defs() -> dict[int, np.ndarray]:
    """Computed corners {id: (4,3)} of the HIVE tags of BOTH alliances in the calibration
    state (`tagkit.hive_tag_defs` per alliance), independent of the pipeline's HIVE state."""
    from . import field, tagkit
    out: dict[int, np.ndarray] = {}
    for al, up in calibration_state().items():
        try:
            for i, c in tagkit.hive_tag_defs(al, field.HiveState(al, up)).items():
                out[int(i)] = np.asarray(c, float).reshape(4, 3)
        except Exception:  # noqa: BLE001
            log.debug("calibration HIVE tags of %s unavailable", al, exc_info=True)
    return out


def computed_hive_defs(alliance: str, up_cell: str, up_only: bool = False
                       ) -> dict[int, np.ndarray]:
    """Computed field-frame corners {id: (4,3)} of the HIVE tags of `alliance` with `up_cell`
    up, from the field CAD (tagkit.hive_tag_defs): the tags of both cells at the heights they
    have in that state, or only the up CELL's with `up_only`. {} if unavailable."""
    try:
        from . import tagkit
        from .field import HiveState
        if up_only:
            out = tagkit.up_cell_tag_corners(alliance, up_cell)
        else:
            out = tagkit.hive_tag_defs(alliance, HiveState(alliance, up_cell))
        return {int(i): np.asarray(c, float).reshape(4, 3) for i, c in dict(out).items()}
    except Exception:  # noqa: BLE001
        log.debug("computed HIVE tag positions unavailable", exc_info=True)
        return {}


def tag_roll(corners: np.ndarray) -> float:
    """In-image roll (degrees) of a tag: direction of its top edge (corner 0 -> corner 1)."""
    d = np.asarray(corners, float).reshape(4, 2)
    return float(np.degrees(np.arctan2(d[1][1] - d[0][1], d[1][0] - d[0][0])))


def infer_hive_state(dets: dict, intr: CameraIntrinsics, ext: CameraExtrinsics, table: dict,
                     alliance: str, max_px: float = HIVE_MATCH_PX,
                     margin_px: float = HIVE_MARGIN_PX) -> Optional[str]:
    """Which CELL is up, from one camera's AprilTag detections `{id: (4,2) corners}` and the
    learned table `{state_key: {id: (4,3) field corners}}`: project every learned state's
    tags into the camera and pick the state whose projections match the detected corners.
    None when fewer than 2 tags match a state, the best error exceeds `max_px`, or the
    runner-up is not clearly worse."""
    from .calib import project
    scores: dict[str, float] = {}
    for cell in CELLS:
        tab = table.get(hive_state_key(alliance, cell))
        if not tab:
            continue
        ids = [i for i in dets if i in tab]
        if len(ids) < 2:
            continue
        errs = []
        for i in ids:
            proj = project(intr, ext, np.asarray(tab[i], float))
            errs.append(float(np.mean(np.linalg.norm(proj - np.asarray(dets[i], float), axis=1))))
        scores[cell] = sum(errs) / len(errs)
    if not scores:
        return None
    best = min(scores, key=lambda c: scores[c])
    if scores[best] > max_px:
        return None
    rest = [v for c, v in scores.items() if c != best]
    if rest and min(rest) - scores[best] < margin_px:
        return None
    return best


class _LowResMotion:
    """MOG2 background model run on a smaller copy of the frame; the foreground mask is
    scaled back (nearest) so the colour gating and contour steps keep full detail. The
    motion model dominates the detector cost, and balls stay many pixels wide."""

    def __init__(self, bg, scale: float):
        self.bg = bg
        self.scale = scale

    def apply(self, img, learningRate: float = -1.0):
        h, w = img.shape[:2]
        small = cv2.resize(img, (max(1, round(w * self.scale)), max(1, round(h * self.scale))),
                           interpolation=cv2.INTER_AREA)
        return cv2.resize(self.bg.apply(small, learningRate=learningRate), (w, h),
                          interpolation=cv2.INTER_NEAREST)


def _make_detector(cfg, motion_scale: float):
    from .detect import BallDetector  # lazy, like the other pipeline stages
    if not 0.0 < motion_scale < 1.0:
        return BallDetector(cfg)

    class LowMotionDetector(BallDetector):
        def reset(self) -> None:
            super().reset()
            self._bg = _LowResMotion(self._bg, motion_scale)

    return LowMotionDetector(cfg)


class ScaledDetector:
    """BallDetector driven on a frame that is downscaled exactly once (INTER_AREA).

    The wrapped detector runs at process_scale 1.0 on the small frame with its pixel radius
    limits scaled accordingly, which is equivalent to BallDetector(process_scale=s) on the
    full frame; detections are mapped back to full-resolution pixel coordinates. The small
    frame is returned to the caller so the preview and clip ring buffer can be cut from it
    instead of resizing the full-resolution frame again."""

    def __init__(self, cfg, motion_scale: float = 1.0):
        s = float(cfg.process_scale)
        self.scale = s
        self._small: Optional[np.ndarray] = None
        self.det = _make_detector(dataclasses.replace(
            cfg, process_scale=1.0, min_radius_px=cfg.min_radius_px * s,
            max_radius_px=cfg.max_radius_px * s), motion_scale)
        self.draw = self.det.draw

    def shrink(self, image: np.ndarray) -> np.ndarray:
        """The frame downscaled once. The result is a reusable buffer, valid until the next
        call (a fresh 0.7 MB array per frame costs page faults on every camera thread);
        copy it to keep it."""
        if self.scale == 1.0:
            return image
        w, h = max(1, round(image.shape[1] * self.scale)), max(1, round(image.shape[0] * self.scale))
        buf = self._small
        if buf is None or buf.shape[:2] != (h, w) or buf.dtype != image.dtype                 or buf.shape[2:] != image.shape[2:]:
            buf = self._small = np.empty((h, w, *image.shape[2:]), image.dtype)
        cv2.resize(image, (w, h), dst=buf, interpolation=cv2.INTER_AREA)
        return buf

    def detect(self, small: np.ndarray, frame_idx: int, t: float, cam_id: str):
        dets = self.det.detect(small, frame_idx, t, cam_id)
        s = self.scale
        if s == 1.0:
            return dets
        return [dataclasses.replace(d, u=d.u / s, v=d.v / s, radius_px=d.radius_px / s)
                for d in dets]


def _fit_width(full: np.ndarray, small: np.ndarray, width: int):
    """`full` or its already-downscaled `small` cut to at most `width` px wide (never
    upscaled), picking the cheapest source that is not narrower than the target."""
    base = small if small.shape[1] >= width else full
    bw, bh = base.shape[1], base.shape[0]
    if bw <= width:
        return base
    return cv2.resize(base, (width, max(1, round(bh * width / bw))),
                      interpolation=cv2.INTER_AREA)


def _spec_from(sc: cfgmod.SourceConfig, data_dir: Path,
               rtmp: Optional[RtmpServer] = None) -> SourceSpec:
    kind = SourceKind(sc.kind)
    target: Any = sc.target
    if kind == SourceKind.RTMP and isinstance(target, str) and "://" not in target \
            and target.strip():
        # a bare stream name ("cam0") means the bundled RTMP server's URL for that stream
        name = target.strip().strip("/")
        target = rtmp.url_for(name) if rtmp is not None else f"rtmp://127.0.0.1:1935/{name}"
    elif kind == SourceKind.FILE:
        target = str(cfgmod.resolve_path(str(sc.target), data_dir))
    elif kind == SourceKind.DEVICE and isinstance(target, str) and target.isdigit():
        target = int(target)
    return SourceSpec(cam_id=sc.cam_id, kind=kind, target=target, fps_hint=sc.fps_hint,
                      width=sc.width, height=sc.height, backend=sc.backend,
                      loop=sc.loop, realtime=sc.realtime)


class Pipeline:
    def __init__(self, config: cfgmod.AppConfig, store: Store, data_dir: Path,
                 on_event: Optional[Callable[[dict], None]] = None, save_clips: bool = True,
                 demo: bool = False):
        self._desired = config                  # latest requested config
        self._rcfg = config                     # snapshot used by workers while running
        self.store = store
        self.data_dir = Path(data_dir)
        self.on_event = on_event
        self.save_clips = save_clips
        self.demo = demo                        # bundled demo footage (reported in status)
        self.rtmp = RtmpServer(data_dir=self.data_dir)
        self._rtmp_error: Optional[str] = None
        self._running = False
        self._stopping = False
        self._life = threading.RLock()          # serialises start()/stop()
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._threads: list[threading.Thread] = []
        self._readers: dict[str, Any] = {}
        self._lock = threading.RLock()          # guards pending/history/previews/hive
        self._pending: dict[str, list[Track2D]] = {}
        self._history: dict[str, collections.deque] = {}
        self._done: dict[str, bool] = {}
        self._jpeg: dict[str, bytes] = {}
        self._last_enc: dict[str, float] = {}
        self._preview_clients: dict[str, int] = {}
        self._detectors: dict[str, ScaledDetector] = {}
        self._tags_cache: dict[str, tuple[float, list[int], dict]] = {}
        self._hive_source = "manual"
        self._manual_override = False
        self._hive_tags: dict[str, dict[int, np.ndarray]] = {}
        self._vote: Optional[tuple[str, int, float]] = None
        self._tag_last: dict[str, float] = {}
        self._activity_wall = time.monotonic()
        self._idle_ended = False
        self._idle_lock = threading.Lock()
        self._default_intr: dict[str, str] = {}
        self._cal_src: dict[str, str] = {}          # per camera: how its extrinsics came about
        self._intr_src: dict[str, str] = {}         # per camera: measured | profile | default
        self._timing: dict[str, dict[str, float]] = {}
        self._recon_ms: Optional[float] = None
        self._drops: dict[str, collections.deque] = {}
        self._ring_pool: dict[str, list[np.ndarray]] = {}
        self._timers_on = False
        self._ring_pins: dict[str, int] = {}        # clip writers reading a ring's buffers
        self._proc_times: dict[str, collections.deque] = {}
        self._ring: dict[str, collections.deque] = {}
        self._hive = HiveState(config.alliance, config.hive_up_cell)
        self._hive_hist: list[tuple[float, HiveState]] = [(float("-inf"), self._hive)]
        self._pending_tips: list[_PendingTip] = []
        self._frame_size: dict[str, tuple[int, int]] = {}
        self._stale_ext: set[str] = set()
        self._cam_wall: dict[str, float] = {}
        self._session_id: Optional[str] = None
        self._last_t = 0.0
        self._last_shot_id: Optional[int] = None
        self._calib: tuple[dict[str, CameraIntrinsics], dict[str, CameraExtrinsics]] = ({}, {})
        self._offset: Optional[float] = None
        self._offset_wall = 0.0
        self._offset_conf: Optional[float] = None
        self._unpaired = 0
        self._warned: set[str] = set()
        self._pair_stale: set[str] = set()      # solved alone after a failed pair check
        self._reset_health()
        self._chains: list[_Chain] = []
        self._closed_at: dict[int, float] = {}
        self._cam_t: dict[str, float] = {}
        self.finalize_log: list[dict] = []     # per-shot diagnostics (lag in source seconds)
        self.last_error: Optional[str] = None
        self.reload_calibration()

    # ---------------------------------------------------------------- helpers
    def _emit(self, ev: dict) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(ev)
        except Exception:  # noqa: BLE001
            log.exception("on_event failed")

    def _warn_once(self, key: str, msg: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning(msg)

    @property
    def cfg(self) -> cfgmod.AppConfig:
        return self._desired

    @cfg.setter
    def cfg(self, value: cfgmod.AppConfig) -> None:
        try:
            self.apply_config(value)
        except ConfigConflict as e:
            log.warning("config assignment ignored while running: %s", e)

    def apply_config(self, new: cfgmod.AppConfig) -> list[str]:
        """Apply a new config. While running, `sources` may not change (ConfigConflict);
        burst/settle/finalize/stitch/robot/preview_fps and the HIVE state take effect
        immediately, everything else (calibration_path, detector) at the next start.
        Returns the keys deferred to the next start."""
        deferred: list[str] = []
        with self._lock:
            if self._running and not self._stop.is_set():
                if ([s.model_dump() for s in new.sources]
                        != [s.model_dump() for s in self._rcfg.sources]):
                    raise ConfigConflict("sources cannot be changed while the pipeline is "
                                         "running; stop it first")
                self._rcfg = self._rcfg.model_copy(
                    update={k: getattr(new, k) for k in SAFE_LIVE_KEYS})
                for k in ("calibration_path", "detector"):
                    if getattr(new, k) != getattr(self._rcfg, k):
                        deferred.append(k)
            else:
                self._rcfg = new
            # a HIVE change in the config is the user's; the live state may differ from the
            # stored config because the tags updated it
            hive_changed = (new.alliance, new.hive_up_cell) != (self._desired.alliance,
                                                                 self._desired.hive_up_cell)
            self._desired = new
        if hive_changed:
            self.set_hive_state(new.alliance, new.hive_up_cell)
        return deferred

    @property
    def running(self) -> bool:
        return self._running and not self._stopping

    def is_finished(self) -> bool:
        return self._finished.is_set()

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    def set_session(self, session_id: Optional[str]) -> None:
        self._session_id = session_id
        self._activity_wall = time.monotonic()
        self._idle_ended = False
        if session_id is not None:
            self._warned.discard("unassigned")

    def set_hive_state(self, alliance: str, up_cell: str, t: Optional[float] = None,
                       source: str = "manual") -> HiveState:
        """Set the HIVE state. `t` is the source time of the change (default: the latest
        source time seen). A timestamped history is kept so shots are classified with the
        state at their launch."""
        new = HiveState(alliance, up_cell)
        with self._lock:
            old = self._hive
            self._hive = new
            self._hive_source = source
            self._manual_override = source == "manual"
            self._vote = None
            t_ev = self._last_t if t is None else float(t)
            self._hive_hist.append((t_ev, new))
            if len(self._hive_hist) > 200:
                del self._hive_hist[1:50]
            sid = self._session_id
        if self._running and old.up_cell != new.up_cell:
            sid = sid or UNASSIGNED_SESSION
            if sid == UNASSIGNED_SESSION:
                self.store.ensure_session(UNASSIGNED_SESSION, "Unassigned shots")
            tip = TipEvent(t=t_ev, session_id=sid, alliance=new.alliance,
                           new_up_cell=new.up_cell, caused_by_shot_id=None)
            tip_id = self.store.add_tip(tip)
            with self._lock:
                self._pending_tips.append(_PendingTip(tip_id, tip))
            self._emit({"type": "tip", "tip": dataclasses.asdict(tip)})
        return new

    def _state_at(self, t: float) -> HiveState:
        with self._lock:
            best = max(((ts, i) for i, (ts, _) in enumerate(self._hive_hist) if ts <= t),
                       default=None)
            return self._hive_hist[best[1]][1] if best else self._hive_hist[0][1]

    def hive_state(self) -> HiveState:
        return self._hive

    # ------------------------------------------------------------ calibration
    def calibration(self) -> tuple[dict[str, CameraIntrinsics], dict[str, CameraExtrinsics]]:
        return self._calib

    def stale_extrinsics(self) -> set[str]:
        return set(self._stale_ext)

    def calibration_mismatch(self) -> dict[str, str]:
        """{cam_id: "<calibration WxH> vs <delivered frame WxH>"} for cameras whose first
        delivered frame does not match the intrinsics' image size."""
        intr = self._calib[0]
        out = {}
        for cam, (w, h) in dict(self._frame_size).items():
            i = intr.get(cam)
            if i is not None and (i.width, i.height) != (w, h):
                out[cam] = f"{i.width}x{i.height} vs {w}x{h}"
        return out

    def _check_calib(self, cam: str) -> None:
        msg = self.calibration_mismatch().get(cam)
        if msg:
            self._warn_once(f"calib-size-{cam}-{msg}",
                            f"calibration for {cam} does not match the video frame size "
                            f"({msg}); 3D results will be wrong until recalibrated")

    def _fixture_calibration_allowed(self) -> bool:
        """The calibration embedded next to a fixture video (`*_truth.json`) is a convenience
        for the demo and the bundled fixture files only; with any real source (camera, RTMP,
        URL, or a file of the user's) it is never used."""
        if self.demo:
            return True
        fx = cfgmod.resolve_path("fixtures", self.data_dir).resolve()
        for sc in self._rcfg.sources:
            if sc.kind != "file":
                return False
            t = str(sc.target).replace("\\", "/")
            try:
                inside = cfgmod.resolve_path(t, self.data_dir).resolve().is_relative_to(fx)
            except (OSError, ValueError):
                inside = False
            if not (inside or t.startswith("fixtures/")):
                return False
        return bool(self._rcfg.sources)

    def _reset_health(self) -> None:
        """Per-run bookkeeping of processing errors, loop restarts and watchdog state."""
        self._errors: dict[str, int] = {}
        self._err_last: dict[str, str] = {}
        self._err_logged: set[tuple] = set()
        self._loop_restarts: dict[str, collections.deque] = {}
        self._restart_total: dict[str, int] = {}
        self._gen: dict[str, int] = {}
        self._recon_gen = 0
        self._recon_busy = threading.Lock()
        self._detect_mark: dict[str, tuple[float, int]] = {}   # cam -> (monotonic, frames_read)
        self._recon_wall = time.monotonic()
        self._stalls: dict[str, str] = {}
        self._shot_spans: list[tuple[float, float]] = []       # reconstructed flights (cam A time)
        self._trackers: dict[str, Any] = {}

    def _frame_error(self, cam: str, stage: str, exc: BaseException) -> None:
        """A step of the per-frame work failed: count it, log the first occurrence of each
        kind with a traceback, and let the loop go on with the next frame."""
        with self._lock:
            self._errors[cam] = self._errors.get(cam, 0) + 1
            self._err_last[cam] = f"{stage}: {exc}"
            key = (cam, stage, type(exc).__name__)
            first = key not in self._err_logged
            self._err_logged.add(key)
        if first:
            log.error("camera %s: %s failed (%s); counting further errors without a traceback",
                      cam, stage, exc, exc_info=(type(exc), exc, exc.__traceback__))
        else:
            log.debug("camera %s: %s failed again: %s", cam, stage, exc)

    def reload_calibration(self) -> None:
        intr: dict[str, CameraIntrinsics] = {}
        ext: dict[str, CameraExtrinsics] = {}
        stale: set[str] = set()
        cal_src: dict[str, str] = {}
        intr_src: dict[str, str] = {}
        self._hive_tags = {}
        path = cfgmod.resolve_path(self._rcfg.calibration_path, self.data_dir)
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._hive_tags = {
                    k: {int(i): np.asarray(c, float).reshape(4, 3) for i, c in v.items()}
                    for k, v in (data.get("hive_tags") or {}).items()}
                for d in data.get("intrinsics", []):
                    i = CameraIntrinsics(**{**d, "dist": tuple(d["dist"])})
                    intr[i.cam_id] = i
                    intr_src[i.cam_id] = str((data.get("intrinsics_source") or {}).get(
                        i.cam_id, "measured"))
                solves = data.get("solve_tags") or {}
                for d in data.get("extrinsics", []):
                    d = dict(d)
                    is_stale = bool(d.pop("stale", False))
                    e = CameraExtrinsics(**{**d, "rvec": tuple(d["rvec"]),
                                            "tvec": tuple(d["tvec"])})
                    ext[e.cam_id] = e
                    cal_src[e.cam_id] = _source_of_solve(solves.get(e.cam_id))
                    if is_stale:
                        stale.add(e.cam_id)
            elif self._fixture_calibration_allowed():
                for sc in self._rcfg.sources:  # embedded fixture calibration (demo / bundled)
                    if sc.kind != "file":
                        continue
                    truth = cfgmod.resolve_path(str(sc.target), self.data_dir)
                    tj = truth.with_name(truth.stem + "_truth.json")
                    if tj.exists():
                        d = json.loads(tj.read_text(encoding="utf-8"))
                        i = CameraIntrinsics(**{**d["intrinsics"], "cam_id": sc.cam_id,
                                                "dist": tuple(d["intrinsics"]["dist"])})
                        e = CameraExtrinsics(**{**d["extrinsics"], "cam_id": sc.cam_id,
                                                "rvec": tuple(d["extrinsics"]["rvec"]),
                                                "tvec": tuple(d["extrinsics"]["tvec"])})
                        intr[sc.cam_id], ext[sc.cam_id] = i, e
                        cal_src[sc.cam_id] = "fixture"
                        intr_src[sc.cam_id] = "measured"
        except Exception as e:  # noqa: BLE001
            self.last_error = f"calibration load failed: {e}"
            log.warning(self.last_error)
        self._default_intr = {}
        # lens intrinsics for cameras without measured ones: the active profile's measured
        # `intrinsics` slot ("profile"), else the generic default ("default": a warning that
        # stays until the camera's lens is measured)
        slot, slot_name, source = None, "", "default"
        prof = (self._rcfg.profiles or {}).get(self._rcfg.active_profile or "", {})
        if isinstance(prof, dict) and isinstance(prof.get("intrinsics"), dict):
            slot, slot_name, source = prof["intrinsics"], str(self._rcfg.active_profile), "profile"
        elif self._rcfg.default_intrinsics:
            slot_name, slot = next(iter(self._rcfg.default_intrinsics.items()))
        for sc in self._rcfg.sources:
            keep = intr_src.get(sc.cam_id)
            if sc.cam_id in intr and keep in (None, "measured", "measured_poor"):
                continue
            if slot is None:
                continue
            try:
                intr[sc.cam_id] = CameraIntrinsics(
                    cam_id=sc.cam_id, width=int(slot["width"]), height=int(slot["height"]),
                    fx=float(slot["fx"]), fy=float(slot["fy"]), cx=float(slot["cx"]),
                    cy=float(slot["cy"]), dist=tuple(float(x) for x in slot.get("dist", [0] * 5)))
                intr_src[sc.cam_id] = source
                if source == "default":
                    self._default_intr[sc.cam_id] = slot_name
            except (KeyError, TypeError, ValueError) as e:
                log.warning("intrinsics of %r unusable: %s", slot_name, e)
        self._calib = (intr, ext)
        self._cal_src, self._intr_src = cal_src, intr_src
        self._stale_ext = stale
        for c in stale:
            self._warn_once(f"stale-{c}", f"extrinsics for {c} are stale (intrinsics were "
                            "recalibrated); re-solve the extrinsics")
        for cam in list(self._frame_size):
            self._check_calib(cam)
        self._offset = None
        self._offset_wall = 0.0

    def set_pair_stale(self, cam: str, flag: bool) -> None:
        """Mark a camera whose pose may disagree with the other camera's (the pair check
        failed when the other one was solved alone) until it is re-solved."""
        if flag:
            self._pair_stale.add(cam)
        else:
            self._pair_stale.discard(cam)

    def pair_stale(self) -> set[str]:
        return set(self._pair_stale)

    def intrinsics_sources(self) -> dict[str, str]:
        """{cam_id: "measured" | "profile" | "default"} of the intrinsics in use."""
        return dict(self._intr_src)

    def calibration_sources(self) -> dict[str, str]:
        """{cam_id: provenance of its calibration} for the configured cameras: "none",
        "fixture" (embedded fixture truth), "default_intrinsics" (no extrinsics, lens
        defaults only), or how the extrinsics were solved: "kit", "hive" or "click"."""
        intr, ext = self._calib
        out = {}
        for sc in self._rcfg.sources:
            c = sc.cam_id
            if c in ext and c in intr:
                out[c] = self._cal_src.get(c, "click")
            elif c in intr and self._intr_src.get(c) == "default":
                out[c] = "default_intrinsics"
            else:
                out[c] = "none"
        return out

    def calibration_source(self) -> str:
        """Least trustworthy provenance over the cameras (none < default_intrinsics <
        fixture < click < hive < kit)."""
        srcs = list(self.calibration_sources().values())
        return min(srcs, key=_SOURCE_RANK.index) if srcs else "none"

    # --------------------------------------------------------------- lifecycle
    def start(self) -> dict:
        """Start capture + processing. Idempotent: a second call (also a concurrent one)
        returns the current status without touching the running pipeline."""
        with self._life:
            if self._running:
                return self.status()
            self._start_locked()
            return self.status()

    def _start_locked(self) -> None:
        from .detect import DetectorConfig  # noqa: F401  (fail early if missing)
        from .recon import StereoReconstructor  # noqa: F401  (fail early if missing)
        from .track2d import Tracker2D  # noqa: F401  (fail early if missing)

        with self._lock:
            self._rcfg = cfg = self._desired          # config snapshot for this run
            self._detectors = {}
            self._reset_health()
            self._tags_cache = {}
            self._hive_source = "manual"
            self._activity_wall = time.monotonic()
            self._idle_ended = False
            self._stop.clear()
            self._finished.clear()
            self._stopping = False
            self._pending = {s.cam_id: [] for s in cfg.sources}
            self._history = {s.cam_id: collections.deque(maxlen=40) for s in cfg.sources}
            self._done = {s.cam_id: False for s in cfg.sources}
            self._jpeg.clear()
            self._last_enc.clear()
            self._proc_times = {s.cam_id: collections.deque(maxlen=600) for s in cfg.sources}
            self._ring = {s.cam_id: collections.deque() for s in cfg.sources}
            self._ring_pool = {s.cam_id: [] for s in cfg.sources}
            self._ring_pins = {s.cam_id: 0 for s in cfg.sources}
            self._timing = {s.cam_id: {} for s in cfg.sources}
            self._recon_ms = None
            self._offset_conf = None
            self._unpaired = 0
            self._drops = {s.cam_id: collections.deque(maxlen=DROP_EVENTS_MAX)
                           for s in cfg.sources}
            self._offset, self._offset_wall = None, 0.0
            self._last_t = 0.0
            self._chains = []
            self._closed_at = {}
            self._cam_t = {}
            self._cam_wall = {}
            self._frame_size = {}
            self._hive_hist = [(float("-inf"), self._hive)]
            self._pending_tips = []
            self.last_error = None
        self.reload_calibration()
        if len(cfg.sources) < 2:
            self._warn_once("single", "single-camera mode: no 3D reconstruction, no shots")

        specs = [_spec_from(s, self.data_dir, self.rtmp) for s in cfg.sources]
        if any(s.kind == SourceKind.RTMP for s in specs):
            try:
                self.rtmp.start()
                self._rtmp_error = None
            except RtmpServerError as e:
                self._rtmp_error = str(e)
                log.warning("rtmp: %s", e)
        lock_specs = [s for s in specs if s.kind == SourceKind.FILE and not s.realtime]
        cap_specs = [s for s in specs if s not in lock_specs]
        self._readers = {}
        try:
            if cap_specs:
                self._readers.update(MultiCapture(cap_specs).start().threads)
            for s in lock_specs:
                self._readers[s.cam_id] = _LockstepReader(s).start()

            if self._session_id is None:
                self._session_id = self.store.create_session(
                    cfgmod.format_session_name(cfg.session_name_template))
            self._threads = []
            for r in self._readers.values():          # capture threads: same class as the camera loops
                th_cap = getattr(r, "_thread", None)
                if th_cap is not None and getattr(th_cap, "native_id", None):
                    _thread_priority(CAM_PRIORITY, th_cap.native_id)
            for cam in self._readers:
                self._threads.append(self._new_cam_thread(cam))
            self._threads.append(threading.Thread(target=self._recon_loop, args=(0,),
                                                  name="recon", daemon=True))
            self._threads.append(threading.Thread(target=self._tag_loop, name="tags",
                                                  daemon=True))
            self._threads.append(threading.Thread(target=self._watchdog_loop, name="watchdog",
                                                  daemon=True))
            self._tag_last = {}
            self._vote = None
            self._running = True
            _fine_timers(True)
            self._timers_on = True
            for th in self._threads:
                th.start()
        except Exception:
            self._stop.set()
            self._running = False
            if self._timers_on:
                self._timers_on = False
                _fine_timers(False)
            for r in self._readers.values():
                r.stop()
            self._readers = {}
            self._threads = []
            raise

    def stop(self) -> None:
        """Stop and flush. Joins every worker thread (up to STOP_JOIN_S), then runs one
        final reconstruction cycle + chain flush while no worker is running."""
        with self._life:
            if not self._running:
                return
            self._stopping = True
            self._stop.set()
            for r in self._readers.values():
                r.request_stop()
            deadline = time.monotonic() + STOP_JOIN_S
            for th in self._threads:
                th.join(max(0.0, deadline - time.monotonic()))
                if th.is_alive():
                    log.error("thread %s did not exit within %.0f s of stop", th.name,
                              STOP_JOIN_S)
            for r in self._readers.values():
                r.stop()
            try:
                self._recon_cycle(final=True)
            except Exception:  # noqa: BLE001
                log.exception("final reconstruction/flush failed")
            self._threads = []
            self._readers = {}
            self._running = False
            self._stopping = False
            if self._timers_on:
                self._timers_on = False
                _fine_timers(False)
            if self._rtmp_error is None:
                self.rtmp.stop()

    # ----------------------------------------------------------- per-camera loop
    def _new_cam_thread(self, cam: str) -> threading.Thread:
        """Fresh detector + tracker + camera-loop thread (not started) for `cam`; the
        generation number retires any older loop of the same camera."""
        from .detect import DetectorConfig
        from .track2d import Tracker2D
        cfg = self._rcfg
        det = ScaledDetector(DetectorConfig.from_dict(cfg.detector.model_dump()),
                             cfg.detector.motion_scale)
        trk = Tracker2D(cam)
        gen = self._gen.get(cam, -1) + 1
        self._gen[cam] = gen
        self._detectors[cam] = det
        self._trackers[cam] = trk
        return threading.Thread(target=self._cam_loop, args=(cam, det, trk, gen),
                                name=f"cam-{cam}", daemon=True)

    def _cam_loop(self, cam: str, det, trk, gen: int = 0) -> None:
        """Supervisor of one camera: runs the loop and restarts it (at most
        MAX_LOOP_RESTARTS times a minute) if it dies from an unexpected exception."""
        while not self._stop.is_set() and self._gen.get(cam) == gen:
            try:
                self._cam_loop_once(cam, det, trk, gen)
            except Exception as e:  # noqa: BLE001
                now = time.monotonic()
                dq = self._loop_restarts.setdefault(cam, collections.deque())
                while dq and now - dq[0] > 60.0:
                    dq.popleft()
                self._frame_error(cam, "camera loop", e)
                if len(dq) >= MAX_LOOP_RESTARTS:
                    self.last_error = (f"camera {cam}: processing loop failed {len(dq) + 1} "
                                       f"times in a minute and was stopped ({e})")
                    log.error("camera loop for %s keeps failing; giving up", cam)
                    break
                dq.append(now)
                self._restart_total[cam] = self._restart_total.get(cam, 0) + 1
                log.warning("camera loop for %s died (%s); restarting (%d/%d this minute)",
                            cam, e, len(dq), MAX_LOOP_RESTARTS)
                time.sleep(0.05)
                continue
            break
        if self._gen.get(cam) == gen:
            self._done[cam] = True

    def _cam_loop_once(self, cam: str, det, trk, gen: int) -> None:
        _thread_priority(CAM_PRIORITY)
        reader = self._readers[cam]
        prev_idx: Optional[int] = None
        prev_t = 0.0
        sized = False
        self._detect_mark[cam] = (time.monotonic(), int(getattr(reader, "frames_read", 0)))
        # preview JPEG encoding runs in a helper thread per camera (cv2 releases the GIL), off
        # the detect budget; the cheap clip-ring copy stays on this thread
        aux_q: queue.Queue = queue.Queue(maxsize=AUX_QUEUE_MAX)
        aux = threading.Thread(target=self._aux_loop, args=(cam, det, aux_q), daemon=True,
                               name=f"aux-{cam}")
        aux.start()
        try:
            while not self._stop.is_set() and self._gen.get(cam) == gen:
                fr = reader.get(timeout=0.1)
                if fr is None:
                    if reader.finished:
                        break
                    continue
                t = fr.t_source if fr.t_source is not None else fr.t_capture
                self._note_frame(cam, fr)
                if not sized and hasattr(reader, "maxsize"):
                    sized = True
                    reader.maxsize = _queue_depth(reader, fr)
                if prev_idx is not None and fr.frame_idx > prev_idx + 1:
                    # frames missing between two delivered ones: the reader dropped them
                    with self._lock:
                        self._drops[cam].append((prev_t, t, fr.frame_idx - prev_idx - 1))
                prev_idx, prev_t = fr.frame_idx, t
                t0 = time.perf_counter()
                small, dets = None, []
                try:
                    small = det.shrink(fr.image)
                    dets = det.detect(small, fr.frame_idx, t, cam)
                except Exception as e:  # noqa: BLE001  (seen: OpenCV C++ exceptions under load)
                    self._frame_error(cam, "detection", e)
                    small, dets = None, []
                if self._gen.get(cam) != gen:
                    return                    # a restart replaced this loop while it was stuck
                self._detect_mark[cam] = (time.monotonic(), getattr(reader, "frames_read", 0))
                t1 = time.perf_counter()
                closed = []
                try:
                    trk.update(dets, fr.frame_idx, t)
                    closed = trk.closed()
                except Exception as e:  # noqa: BLE001
                    self._frame_error(cam, "tracking", e)
                t2 = time.perf_counter()
                self._tick(cam, "detect_ms", (t1 - t0) * 1000.0)
                self._tick(cam, "track_ms", (t2 - t1) * 1000.0)
                with self._lock:
                    self._last_t = max(self._last_t, t)
                    self._cam_t[cam] = t
                    self._cam_wall[cam] = time.monotonic()
                    self._proc_times[cam].append(time.perf_counter())
                    if closed:
                        self._add_closed(cam, closed, t)
                try:
                    if small is not None:
                        if self.save_clips:
                            self._ring_frame(cam, fr.image, t, small)
                        if self._preview_due(cam):
                            try:
                                aux_q.put_nowait((fr, dets, small.copy()))
                            except queue.Full:
                                pass             # previews are best effort
                except Exception as e:  # noqa: BLE001
                    self._frame_error(cam, "clip ring / preview", e)
            if self._gen.get(cam) == gen:
                # end of stream or stop: flush open 2D tracks so in-flight shots are not lost
                with self._lock:
                    self._add_closed(cam, trk.finish(), self._last_t)
        finally:
            try:
                aux_q.put(None, timeout=1.0)
                aux.join(2.0)                # the clip ring is complete before 'done'
            except queue.Full:
                pass

    # ---------------------------------------------------------------- watchdog
    def _watchdog_loop(self) -> None:
        while not self._stop.wait(WATCHDOG_PERIOD_S):
            try:
                self._watchdog_tick()
            except Exception:  # noqa: BLE001
                log.exception("watchdog check failed")

    def _watchdog_tick(self) -> None:
        """Health check: a detector that stopped running while frames keep arriving, or a
        reconstruction that completes no cycle while tracks wait, is flagged in the status
        warnings ("pipeline stalled: <component>") and its thread is replaced."""
        if self._stop.is_set() or not self._running:
            return
        now = time.monotonic()
        for cam, r in list(self._readers.items()):
            if self._done.get(cam) or getattr(r, "finished", False):
                continue
            mark = self._detect_mark.get(cam)
            if mark is None:
                continue
            ran_at, frames_then = mark
            frames_now = int(getattr(r, "frames_read", 0))
            if frames_now > frames_then and now - ran_at > DETECT_STALL_S:
                name = f"detector {cam}"
                self._stalls[name] = f"pipeline stalled: {name}"
                log.error("pipeline stalled: %s (no frame processed for %.1f s while %d "
                          "arrived); restarting it", name, now - ran_at, frames_now - frames_then)
                th = self._new_cam_thread(cam)
                self._detect_mark[cam] = (now, frames_now)
                self._threads.append(th)
                th.start()
        pending = any(self._pending.values()) or bool(self._chains)
        if pending and not self._finished.is_set() and now - self._recon_wall > RECON_STALL_S:
            self._stalls["recon"] = "pipeline stalled: reconstruction"
            log.error("pipeline stalled: reconstruction (no cycle completed for %.1f s with "
                      "tracks pending); restarting it", now - self._recon_wall)
            self._recon_gen += 1
            self._recon_busy = threading.Lock()    # the stuck loop may never release its own
            self._recon_wall = now
            th = threading.Thread(target=self._recon_loop, args=(self._recon_gen,),
                                  name="recon", daemon=True)
            self._threads.append(th)
            th.start()

    def _aux_loop(self, cam: str, det, q: "queue.Queue") -> None:
        _thread_priority(-1)
        while True:
            item = q.get()
            if item is None:
                return
            try:
                fr, dets, small = item
                self._preview_frame(cam, fr, dets, det, small)
            except Exception:  # noqa: BLE001
                log.exception("preview failed for %s", cam)

    def _note_frame(self, cam: str, fr: Frame) -> None:
        size = (fr.image.shape[1], fr.image.shape[0])
        prev = self._frame_size.get(cam)
        if prev == size:
            return
        self._frame_size[cam] = size
        if prev is not None:
            self._warn_once(f"size-{cam}-{size}", f"{cam}: frame size changed "
                            f"{prev[0]}x{prev[1]} -> {size[0]}x{size[1]}")
        self._check_calib(cam)

    def _add_closed(self, cam: str, tracks: list[Track2D], t_closed: float) -> None:
        for tr in tracks:
            # real detections only (coasted predictions are kept separately by the tracker)
            clean = Track2D(cam_id=tr.cam_id, track_id=tr.track_id,
                            detections=list(tr.detections))
            self._closed_at[id(clean)] = t_closed
            self._pending[cam].append(clean)
            self._history[cam].append(clean)

    def _tick(self, cam: str, stage: str, ms: float) -> None:
        d = self._timing.setdefault(cam, {})
        prev = d.get(stage)
        d[stage] = ms if prev is None else prev + TIMING_ALPHA * (ms - prev)

    def preview_client_add(self, cam: str) -> None:
        """An MJPEG client attached: previews are only encoded while someone watches."""
        with self._lock:
            self._preview_clients[cam] = self._preview_clients.get(cam, 0) + 1
            self._last_enc.pop(cam, None)          # encode the very next frame

    def preview_client_remove(self, cam: str) -> None:
        with self._lock:
            n = max(0, self._preview_clients.get(cam, 0) - 1)
            self._preview_clients[cam] = n
            if n == 0:
                self._jpeg.pop(cam, None)          # never serve a stale frame later

    def _preview_due(self, cam: str) -> bool:
        period = 1.0 / max(self._rcfg.preview_fps, 1.0)
        return (self._preview_clients.get(cam, 0) > 0
                and time.perf_counter() - self._last_enc.get(cam, 0.0) >= period)

    def _preview_frame(self, cam: str, fr: Frame, dets, det, small) -> None:
        """Encode one MJPEG preview frame (helper thread; `small` is the helper's own copy)."""
        img_full = fr.image
        w = img_full.shape[1]
        now = time.perf_counter()
        img = _fit_width(img_full, small, PREVIEW_WIDTH)
        s = img.shape[1] / w
        sd = [dataclasses.replace(d, u=d.u * s, v=d.v * s, radius_px=d.radius_px * s)
              for d in dets]
        ok, buf = cv2.imencode(".jpg", det.draw(img, sd), [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            with self._lock:
                self._jpeg[cam] = buf.tobytes()
            self._last_enc[cam] = now
        self._tick(cam, "preview_ms", (time.perf_counter() - now) * 1000.0)

    def _ring_frame(self, cam: str, img_full: np.ndarray, t: float, small) -> None:
        """Copy the frame, 480 px wide, into the clip ring (recycled buffers). Runs on the
        camera thread right after detection: `small` is the detector's reusable buffer."""
        t0 = time.perf_counter()
        h, w = img_full.shape[:2]
        s = min(1.0, CLIP_WIDTH / w)
        ow, oh = int(w * s), int(h * s)
        src = small if small.shape[1] >= ow else img_full
        pool = self._ring_pool.setdefault(cam, [])
        dst = pool.pop() if pool and pool[-1].shape == (oh, ow, 3) else None
        if dst is None:
            dst = np.empty((oh, ow, 3), np.uint8)
        cv2.resize(src, (ow, oh), dst=dst, interpolation=cv2.INTER_LINEAR)
        with self._lock:
            ring = self._ring[cam]
            ring.append((t, dst))
            keep_s = self._ring_seconds()
            while ring and t - ring[0][0] > keep_s:
                old = ring.popleft()[1]
                if len(pool) < RING_POOL_MAX and not self._ring_pins.get(cam):
                    pool.append(old)           # recycled as the next frame's buffer
        self._tick(cam, "ring_ms", (time.perf_counter() - t0) * 1000.0)

    def _ring_seconds(self) -> float:
        """Clip ring length: long enough to still hold a shot's first frames when it is
        finalized (held for stitch_gap_s + finalize_delay_s) plus the shot's own flight."""
        c = self._rcfg
        return max(CLIP_SECONDS, c.stitch_gap_s + c.finalize_delay_s + 1.0)

    # ------------------------------------------------- AprilTags, HIVE state, detector colours
    def scan_tags(self, cam: str, image: np.ndarray, max_age_s: float = TAG_SCAN_PERIOD_S
                  ) -> list[int]:
        """Ids of the AprilTags visible in `image`, cached per camera for `max_age_s`
        (cheap: the scan runs on a TAG_SCAN_WIDTH px wide copy, ids only)."""
        now = time.monotonic()
        hit = self._tags_cache.get(cam)
        if hit is not None and now - hit[0] < max_age_s:
            return hit[1]
        from .calib import detect_apriltags
        k = min(1.0, TAG_SCAN_WIDTH / max(1, image.shape[1]))
        small = image if k >= 1.0 else cv2.resize(image, None, fx=k, fy=k,
                                                  interpolation=cv2.INTER_AREA)
        corners: dict[int, np.ndarray] = {}
        try:
            for d in detect_apriltags(small):
                corners.setdefault(int(d["id"]), np.asarray(d["corners"], float) / k)
        except Exception:  # noqa: BLE001
            log.exception("tag scan failed for %s", cam)
        ids = sorted(corners)
        self._tags_cache[cam] = (now, ids, corners)
        return ids

    def tags_seen(self) -> dict[str, list[int]]:
        """{cam_id: tag ids} from the latest frame of every running camera (at most one
        scan per second per camera)."""
        out: dict[str, list[int]] = {}
        for cam in list(self._readers):
            fr = self.latest_frame(cam)
            if fr is not None:
                out[cam] = self.scan_tags(cam, fr.image)
        return out

    def tags_roll(self) -> dict[str, dict[str, dict]]:
        """{cam_id: {cluster: {"roll_deg", "sign"}}} for the HIVE tag clusters seen in the
        latest scan. sign is +1 when the cluster reads upright (|roll| <= 90 degrees: the
        up CELL), -1 when it is flipped (the down CELL)."""
        out: dict[str, dict[str, dict]] = {}
        for cam, (_t, _ids, corners) in list(self._tags_cache.items()):
            for (al, cell), ids in APRILTAG_IDS.items():
                rolls = [tag_roll(corners[i]) for i in ids if i in corners]
                if not rolls:
                    continue
                ang = float(np.degrees(np.arctan2(np.mean(np.sin(np.radians(rolls))),
                                                  np.mean(np.cos(np.radians(rolls))))))
                out.setdefault(cam, {})[f"{al}_{cell}"] = {
                    "roll_deg": round(ang, 1), "sign": 1 if abs(ang) <= 90.0 else -1}
        return out

    @staticmethod
    def infer_up_cell(ids, alliance: str) -> Optional[str]:
        """The CELL whose bottom AprilTags (field_constants.APRILTAG_IDS) are the visible
        ones: at least two of its ids seen and more than any other cell. None if unclear."""
        seen = set(ids)
        counts = {c: len(seen & set(APRILTAG_IDS[(alliance, c)])) for c in CELLS}
        best = max(counts, key=lambda c: counts[c])
        others = [n for c, n in counts.items() if c != best]
        if counts[best] >= 2 and all(counts[best] > n for n in others):
            return best
        return None

    def _hive_from_tags(self, cam: str, image: np.ndarray, t: float) -> None:
        """Set the HIVE state from the visible CELL tags (only when the layout is marked
        verified in the config); the state source becomes "tags"."""
        ids = self.scan_tags(cam, image)
        up = self.infer_up_cell(ids, self._hive.alliance)
        if up is None:
            return
        if up != self._hive.up_cell:
            self.set_hive_state(self._hive.alliance, up, t=t, source="tags")
        else:
            self._hive_source = "tags"

    def hive_tags_ready(self) -> bool:
        """Both HIVE states of the configured alliance have been learned (>= 2 tags each)
        and both cameras are calibrated."""
        al = self._hive.alliance
        return (self.calibration_usable() and all(
            len(self._hive_tags.get(hive_state_key(al, c)) or {}) >= 2 for c in CELLS))

    def hive_tags_table(self) -> dict:
        return self._hive_tags

    def _tag_loop(self) -> None:
        """Scans the latest frames for HIVE tags off the camera threads (~2 Hz per camera)."""
        _thread_priority(-1)
        while not self._stop.wait(0.2):
            try:
                self._tag_tick()
            except Exception:  # noqa: BLE001
                log.exception("HIVE tag scan failed")

    def _tag_tick(self) -> None:
        """HIVE state from tags ~2 Hz: as soon as the cameras are calibrated (the up CELL's
        tag positions are computed; learned positions refine it); before that, and only if
        the layout is marked verified, from which tag ids are visible."""
        calibrated = self.calibration_usable()
        if not (calibrated or self._rcfg.hive_tags_verified):
            return
        now = time.monotonic()
        if now - self._tag_last.get("*", 0.0) < HIVE_TAG_PERIOD_S:
            return
        self._tag_last["*"] = now
        frames = {c: f for c in list(self._readers) if (f := self.latest_frame(c)) is not None}
        if not calibrated:
            for cam, fr in frames.items():
                self._hive_from_tags(cam, fr.image, self._last_t)
            return
        # cheap half-size id scan first: the full-resolution detection only runs when a
        # HIVE tag is actually in view
        with_tags = {c: f for c, f in frames.items()
                     if HIVE_IDS & set(self.scan_tags(c, f.image, TAG_SCAN_PERIOD_S))}
        if with_tags:
            self._hive_from_calibrated(with_tags, now)

    def _learned_by_state(self) -> dict[str, dict[int, np.ndarray]]:
        """Reference tag corners per state: learned ones, else the computed up-CELL tags."""
        al = self._hive.alliance
        out: dict[str, dict[int, np.ndarray]] = {}
        for cell in CELLS:
            key = hive_state_key(al, cell)
            learned = self._hive_tags.get(key)
            if learned:
                out[key] = learned
            else:
                comp = computed_hive_defs(al, cell)
                if comp:
                    out[key] = comp
        return out

    def _hive_from_calibrated(self, frames: dict, now: float) -> None:
        from .calib import detect_apriltags
        intr, ext = self._calib
        dets = {c: detect_apriltags(f.image) for c, f in frames.items()
                if c in intr and c in ext}
        if not dets:
            return
        table = self._learned_by_state()
        cand: Optional[str] = None
        try:
            from . import tagkit
            fn = getattr(tagkit, "infer_hive_state", None)
        except ImportError:
            fn = None
        if fn is not None and table:
            key, conf = fn(table, dets, {c: (intr[c], ext[c]) for c in dets})
            if key and conf >= HIVE_MIN_CONFIDENCE:
                cand = str(key).split("_", 1)[1]
        elif self._hive_tags:
            for cam, ds in dets.items():
                cand = infer_hive_state({int(d["id"]): d["corners"] for d in ds}, intr[cam],
                                        ext[cam], self._hive_tags, self._hive.alliance)
                if cand:
                    break
        if cand is not None:
            self._tag_vote(cand, now)

    def _tag_vote(self, cand: str, now: float) -> None:
        """Hysteresis: commit a state after HIVE_VOTES agreeing samples spanning at least
        HIVE_VOTE_MIN_S. A commit to the current state just confirms it ("tags" source)."""
        with self._lock:
            v = self._vote
            if v is None or v[0] != cand:
                self._vote = (cand, 1, now)
                return
            n, t_first = v[1] + 1, v[2]
            self._vote = (cand, n, t_first)
            if n < HIVE_VOTES or now - t_first < HIVE_VOTE_MIN_S:
                return
            self._vote = None
            alliance, same = self._hive.alliance, cand == self._hive.up_cell
            if same:
                self._hive_source = "tags"
                self._manual_override = False
        if not same:
            self.set_hive_state(alliance, cand, t=self._last_t, source="tags")

    def set_detector_colors(self, pollen_hsv, nectar_hsv) -> None:
        """Apply new HSV ranges to the running detectors immediately."""
        pol = (tuple(int(x) for x in pollen_hsv[0]), tuple(int(x) for x in pollen_hsv[1]))
        nec = (tuple(int(x) for x in nectar_hsv[0]), tuple(int(x) for x in nectar_hsv[1]))
        for det in list(self._detectors.values()):
            det.det.cfg.pollen_hsv = pol
            det.det.cfg.nectar_hsv = nec

    # ------------------------------------------------------------- idle session end
    def _check_idle(self) -> None:
        """End the session after `session_idle_end_min` without a shot and autosave its CSV."""
        mins = self._rcfg.session_idle_end_min
        if mins <= 0 or not self._running or self._session_id is None:
            return
        if time.monotonic() - self._activity_wall < mins * 60.0:
            return
        with self._idle_lock:
            sid = self._session_id
            if sid is None:
                return
            self._session_id = None
            self._idle_ended = True
        self.store.end_session(sid)
        path = self._autosave_csv(sid) if self._rcfg.autosave_csv else None
        log.info("session %s ended after %.1f idle minutes%s", sid, mins,
                 f"; CSV saved to {path}" if path else "")
        self._emit({"type": "session_ended", "session_id": sid, "reason": "idle",
                    "csv": str(path) if path else None})

    def _autosave_csv(self, sid: str) -> Optional[Path]:
        from .stats import shots_to_csv
        try:
            shots = self.store.list_shots(sid)
            if not shots:
                return None
            info = self.store.session_summary(sid) or {}
            name = "".join(c if c.isalnum() or c in "-_." else "_"
                           for c in str(info.get("name") or "session")).strip() or "session"
            path = self.data_dir / "exports" / f"{name}_{sid}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            shots_to_csv(shots, path, info.get("started_at"))
            return path
        except Exception:  # noqa: BLE001
            log.exception("CSV autosave failed for session %s", sid)
            return None

    def latest_jpeg(self, cam: str) -> Optional[bytes]:
        with self._lock:
            return self._jpeg.get(cam)

    def latest_frame(self, cam: str) -> Optional[Frame]:
        r = self._readers.get(cam)
        return None if r is None else r.latest()

    def raw_jpeg(self, cam: str) -> Optional[bytes]:
        fr = self.latest_frame(cam)
        if fr is None:
            return None
        ok, buf = cv2.imencode(".jpg", fr.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes() if ok else None

    # ---------------------------------------------------------- reconstruction
    def _clock(self) -> float:
        """Source time every running camera has reached (the slowest one). A camera that
        has delivered no frame for STALL_AFTER_S of wall time is treated as stalled and
        ignored, so one dead camera cannot freeze finalization."""
        now = time.monotonic()
        with self._lock:
            ts = [t for c, t in self._cam_t.items() if not self._done.get(c)
                  and now - self._cam_wall.get(c, now) <= STALL_AFTER_S]
            return min(ts) if ts else self._last_t

    def _recon_loop(self, gen: int = 0) -> None:
        _thread_priority(-1)
        # Cycles are paced in *source* time (RECON_PERIOD_S), so file runs faster than
        # real time behave like live ones.
        last_cycle_t = -1e9
        while not self._stop.is_set() and self._recon_gen == gen:
            self._stop.wait(0.05)
            if self._stop.is_set() or self._recon_gen != gen:
                break
            self._check_idle()
            all_done = bool(self._done) and all(self._done.values())
            now_t = self._clock()
            if not all_done and now_t - last_cycle_t < RECON_PERIOD_S:
                continue
            last_cycle_t = now_t
            busy = self._recon_busy
            if not busy.acquire(blocking=False):
                continue                       # another (replaced, still unwinding) loop is mid-cycle
            try:
                self._recon_cycle(final=all_done)
            except Exception as e:  # noqa: BLE001
                self.last_error = f"recon: {e}"
                log.exception("recon cycle failed")
            finally:
                busy.release()
            if self._recon_gen != gen:
                break                          # replaced by the watchdog while it was stuck
            self._recon_wall = time.monotonic()
            if all_done:
                self._finished.set()
                break

    def _cam_fps(self, cam: str) -> float:
        r = self._readers.get(cam)
        fps = float((r.props or {}).get("fps") or 0.0) if r is not None else 0.0
        return fps if fps > 1.0 else 30.0

    def _offset_max_lag(self) -> float:
        """Largest clock offset worth searching, from the source kinds."""
        kinds = {s.kind for s in self._rcfg.sources}
        if kinds & {"rtmp", "url"}:
            return OFFSET_LAG_NETWORK_S
        if kinds <= {"device"}:
            return OFFSET_LAG_DEVICE_S
        return OFFSET_LAG_FILE_S

    def _choose_offset(self, recon_cls, args, pa, pb, ha, hb):
        """Return the time offset to use (added to cam B times)."""
        now = time.monotonic()
        every = OFFSET_REESTIMATE_S if (self._offset_conf or 0.0) >= OFFSET_CONFIDENT \
            else OFFSET_REESTIMATE_LOW_CONF_S
        stale = self._offset is None or now - self._offset_wall > every
        if not stale:
            return self._offset
        if min(len(ha), len(hb)) < 2:
            return self._offset if self._offset is not None else 0.0
        from .recon import offset_candidates
        max_lag = self._offset_max_lag()
        # candidates: correlation peaks (prior 0 = same-PC cameras) plus "no offset"; the
        # epipolar residual of the pooled recent tracks decides, so periodic bursts whose
        # correlation aliases at the shot period cannot lock in a wrong offset
        peaks = offset_candidates(ha, hb, k=5, max_lag_s=max_lag, prior_offset_s=0.0)
        cands = sorted({0.0, *(round(o, 4) for o, _ in peaks)})
        rc = recon_cls(*args, time_offset_s=0.0)
        best_off, _cost = rc.choose_offset_by_epipolar(ha, hb, cands)
        conf = float(getattr(rc, "last_choice_confidence", 0.0))
        self._offset, self._offset_wall = best_off, now
        self._offset_conf = conf
        log.info("time offset cam B -> cam A: %.4f s (confidence %.2f, search +-%.2f s)",
                 best_off, self._offset_conf, max_lag)
        return best_off

    def _recon_cycle(self, final: bool = False) -> None:
        cams = [s.cam_id for s in self._rcfg.sources]
        if len(cams) < 2:
            with self._lock:
                for c in cams:
                    self._pending[c].clear()
            return
        from .recon import StereoReconstructor
        a, b = cams[0], cams[1]
        intr, ext = self._calib
        t_cycle = time.perf_counter()
        with self._lock:
            pa, pb = list(self._pending[a]), list(self._pending[b])
            closed_at = dict(self._closed_at)
            ha, hb = list(self._history[a]), list(self._history[b])
            t_now = self._last_t
        if not all(c in intr and c in ext for c in (a, b)):
            self._warn_once("calib", f"no calibration for {a}/{b}; cannot reconstruct")
            return
        used_a: set[int] = set()
        used_b: set[int] = set()
        if pa and pb:
            max_dt = 1.5 / min(self._cam_fps(a), self._cam_fps(b))
            args = (intr[a], ext[a], intr[b], ext[b])
            off = self._choose_offset(
                lambda *x, time_offset_s=0.0: StereoReconstructor(
                    *x, time_offset_s=time_offset_s, max_dt_s=max_dt),
                args, pa, pb, ha, hb)
            rc = StereoReconstructor(*args, time_offset_s=off, max_dt_s=max_dt)
            frags: list[tuple[Track3D, float]] = []
            for ta, tb in rc.match_tracks(pa, pb):
                tr3 = rc.reconstruct(ta, tb)
                used_a.add(id(ta))
                used_b.add(id(tb))
                if tr3.points:
                    frags.append((tr3, max(closed_at.get(id(ta), t_now),
                                           closed_at.get(id(tb), t_now))))
            for tr3, c_t in sorted(frags, key=lambda f: f[0].points[0].t):
                self._ingest_fragment(tr3, c_t)
        with self._lock:
            self._pending[a] = [t for t in self._pending[a] if id(t) not in used_a]
            self._pending[b] = [t for t in self._pending[b] if id(t) not in used_b]
            for c in (a, b):
                if final:
                    gone, keep = self._pending[c], []
                else:
                    keep = [t for t in self._pending[c] if t.detections
                            and t_now - t.detections[-1].t <= PENDING_MAX_AGE_S]
                    gone = [t for t in self._pending[c] if id(t) not in {id(k) for k in keep}]
                n_lost = 0
                for t in gone:
                    if not self._is_lost_shot(c, t, cams):
                        continue
                    n_lost += 1
                if n_lost:
                    self._unpaired += n_lost
                    log.warning("%d ball track(s) from %s found no partner in the other "
                                "camera and no shot covers their time: a shot is missing",
                                n_lost, c)
                self._pending[c] = keep
            live = {id(t) for c in (a, b) for t in self._pending[c]}
            self._closed_at = {k: v for k, v in self._closed_at.items() if k in live}
        self._release_chains(final=final)
        ms = (time.perf_counter() - t_cycle) * 1000.0
        self._recon_ms = ms if self._recon_ms is None \
            else self._recon_ms + 0.1 * (ms - self._recon_ms)

    @staticmethod
    def _ballistic(points: list[Point3D]):
        """Function t -> xyz: gravity-only extrapolation fitted to the tail of a fragment."""
        tail = points[-12:]
        t0 = tail[-1].t
        dt = np.array([p.t - t0 for p in tail])
        ks = []
        for axis in "xyz":
            v = np.array([getattr(p, axis) for p in tail])
            if axis == "z":
                v = v + 0.5 * GRAVITY_IPS2 * dt ** 2
            ks.append(np.polyfit(dt, v, 1) if len(tail) >= 2 else (0.0, v[0]))

        def at(t: float) -> np.ndarray:
            d = t - t0
            return np.array([ks[0][1] + ks[0][0] * d, ks[1][1] + ks[1][0] * d,
                             ks[2][1] + ks[2][0] * d - 0.5 * GRAVITY_IPS2 * d * d])
        return at

    @classmethod
    def _extrapolate(cls, points: list[Point3D], t: float) -> np.ndarray:
        """Ballistic (gravity only) extrapolation from the tail of a fragment."""
        return cls._ballistic(points)(t)

    def _opening_distance(self, p: Point3D, h: Optional[HiveState] = None) -> float:
        """Signed distance of p from the up-CELL opening plane (positive = outside)."""
        if h is None:
            with self._lock:
                h = self._hive
        c, n = cell_opening_plane(h.alliance, h.up_cell, HiveState(h.alliance, h.up_cell))
        return float(np.dot(np.array([p.x, p.y, p.z]) - c, n))

    def _stitch_pending(self, ch: _Chain) -> bool:
        """True if the track ended mid-air, so a continuation fragment may still arrive."""
        if self._rcfg.stitch_gap_s <= 0:
            return False
        last = ch.track.points[-1]
        if last.z <= LANDED_Z_IN:
            return False
        h = self._state_at(ch.track.points[0].t)
        return not 0.0 < self._opening_distance(last, h) <= EXTEND_PLANE_IN

    def _is_lost_shot(self, cam: str, track, cams: list) -> bool:
        """An unpaired 2D track means a lost shot only if it is a real ball track (enough hits
        over a long enough time) and no reconstructed shot covers its time span; a stray
        fragment of a flight that was reconstructed from the other pieces is just debug noise."""
        dets = track.detections
        if len(dets) < UNPAIRED_MIN_HITS:
            return False
        t0, t1 = dets[0].t, dets[-1].t
        if t1 - t0 < UNPAIRED_MIN_SPAN_S:
            log.debug("unpaired short track on %s (%.2f s, %d hits)", cam, t1 - t0, len(dets))
            return False
        off = (self._offset or 0.0) if len(cams) > 1 and cam == cams[1] else 0.0
        a, b = t0 + off - UNPAIRED_OVERLAP_S, t1 + off + UNPAIRED_OVERLAP_S
        with self._lock:
            covered = any(s0 <= b and s1 >= a for s0, s1 in self._shot_spans)
        if covered:
            log.debug("unpaired track on %s overlaps a reconstructed shot; not a lost shot", cam)
            return False
        return True

    def _ingest_fragment(self, frag: Track3D, closed_t: float) -> None:
        first = frag.points[0]
        with self._lock:
            self._shot_spans.append((first.t, frag.points[-1].t))
            del self._shot_spans[:-2000]
        gap_max = self._rcfg.stitch_gap_s
        best, best_err = None, None
        for ch in self._chains if gap_max > 0 else []:
            gap = first.t - ch.track.points[-1].t
            if gap <= 0 or gap > gap_max:
                continue
            pred = self._extrapolate(ch.track.points, first.t)
            err = float(np.linalg.norm(pred - np.array([first.x, first.y, first.z])))
            if err <= FRAG_TOL_BASE_IN + FRAG_TOL_PER_S_IN * gap and (
                    best_err is None or err < best_err):
                best, best_err = ch, err
        if best is None:
            self._chains.append(_Chain(frag, closed_t))
            return
        best.track.points.extend(frag.points)
        best.closed_t = max(best.closed_t, closed_t)
        best.fragments += 1
        if best.track.ball_type == BallType.UNKNOWN:
            best.track.ball_type = frag.ball_type

    def _release_chains(self, final: bool = False) -> None:
        t_now = self._clock()
        delay = self._rcfg.finalize_delay_s
        hold = max(delay, self._rcfg.stitch_gap_s)
        keep: list[_Chain] = []
        for ch in self._chains:
            age = t_now - ch.closed_t
            if final or age >= (hold if self._stitch_pending(ch) else delay):
                self._finalize(ch.track, ch)
            else:
                keep.append(ch)
        self._chains = keep

    def _extend_into_opening(self, tr3: Track3D, crosses, radius: float,
                             state: Optional[HiveState] = None) -> None:
        pts = tr3.points
        if len(pts) < 4:
            return
        last = pts[-1]
        if not 0.0 < self._opening_distance(last, state) <= EXTEND_PLANE_IN:
            return
        at = self._ballistic(pts)
        # step in space, not only in time: a 500 in/s ball moves 8 in per 60 fps frame, so a
        # whole-frame step lands the appended points beyond the 12 in deep CELL (and its
        # profile) and the shot would read as leaving through a wall
        speed = float(np.linalg.norm((at(last.t + 0.01) - at(last.t)) / 0.01))
        step = min(EXTEND_STEP_S, EXTEND_STEP_IN / max(speed, 1.0))
        prev = np.array([last.x, last.y, last.z])
        for k in range(1, int(EXTEND_MAX_S / step) + 1):
            t = last.t + k * step
            cur = at(t)
            if crosses(tuple(prev), tuple(cur), radius) is not None:
                nxt = at(t + step)
                tr3.points.append(Point3D(t, *map(float, cur), 0.0))
                tr3.points.append(Point3D(t + step, *map(float, nxt), 0.0))
                self._ext_note = "track extrapolated into the up-CELL opening (ball hidden)"
                return
            prev = cur

    def _finalize(self, tr3, chain: Optional[_Chain] = None) -> None:
        if len(tr3.points) < 4:
            log.debug("dropping short reconstructed track (%d pts)", len(tr3.points))
            return
        sid = self._session_id
        if sid is None and self._idle_ended:
            # the session ended after idling: the next shot starts a fresh one
            with self._idle_lock:
                if self._session_id is None:
                    self._session_id = self.store.create_session(
                        cfgmod.format_session_name(self._rcfg.session_name_template))
                    self._idle_ended = False
                sid = self._session_id
        if sid is None:
            # no active session (ended by the user): do not silently start a new one
            sid = UNASSIGNED_SESSION
            self.store.ensure_session(sid, "Unassigned shots")
            self._warn_once("unassigned", "no active session: shots are stored in the "
                            f"'{UNASSIGNED_SESSION}' session until a session is started")
        t_launch = tr3.points[0].t
        state = self._state_at(t_launch)   # HIVE state when the ball left the robot
        cc, crosses, inside = opening_classifier(
            state.alliance, state.up_cell, state, burst_gap_s=self._rcfg.burst_gap_s,
            settle_time_s=self._rcfg.settle_time_s)

        ball = tr3.ball_type
        self._ext_note = ""
        n_before = len(tr3.points)
        self._extend_into_opening(tr3, crosses, cc.radius_for(ball), state)
        t_meas = tr3.points[n_before - 1].t
        self.finalize_log.append({
            "t_last_point": t_meas, "t_now": self._clock(), "lag_s": self._clock() - t_meas,
            "since_closed_s": (self._clock() - chain.closed_t) if chain else None,
            "fragments": chain.fragments if chain else 1,
            "extended": len(tr3.points) > n_before, "n_points": n_before})
        shot = build_shot(tr3, sid, 0, (crosses, inside), ball, cc)
        extra = []
        if len(tr3.points) > n_before:
            extra.append(self._ext_note)
        n_dropped = self._dropped_between(t_launch, t_meas + SHOT_WINDOW_TAIL_S)
        if n_dropped:
            extra.append(dropped_note(n_dropped))
        if extra:
            shot = dataclasses.replace(
                shot, notes="; ".join(([shot.notes] if shot.notes else []) + extra))
        # store the shot with its burst already assigned: a reader (UI, API) must never see
        # the (0, 0) placeholder between the insert and the session-wide re-assignment below
        if not any(x.shot_id == shot.shot_id for x in self.store.list_shots(sid)):
            mine = [x for x in assign_bursts([*self.store.list_shots(sid), shot],
                                             self._rcfg.burst_gap_s)
                    if x.shot_id == shot.shot_id]
            if mine:
                shot = dataclasses.replace(shot, burst_id=mine[0].burst_id,
                                           burst_index=mine[0].burst_index, notes=mine[0].notes)
        stored = self.store.add_shot(shot)
        if shot.result == ShotResult.MADE:
            _, entry_t = classify_track(tr3, crosses, inside, cc)
            self._link_tips(stored, entry_t)
        # re-assign bursts over the whole session; persist and announce only what changed
        before = {s.shot_id: s for s in self.store.list_shots(sid)}
        changed: list[int] = []
        for s in assign_bursts(list(before.values()), self._rcfg.burst_gap_s):
            o = before[s.shot_id]
            if (o.burst_id, o.burst_index, o.notes) != (s.burst_id, s.burst_index, s.notes):
                self.store.update_burst(s.shot_id, s.burst_id, s.burst_index, s.notes)
                changed.append(s.shot_id)
        if self.save_clips:
            self._write_clips(stored)
        final = self.store.get_shot(stored.shot_id) or stored
        self._last_shot_id = final.shot_id
        self._activity_wall = time.monotonic()
        started = (self.store.session_summary(sid) or {}).get("started_at")
        self._emit({"type": "shot", "shot": summarize(final, started)})
        for sid_changed in changed:
            if sid_changed != stored.shot_id:
                upd = self.store.get_shot(sid_changed)
                if upd is not None:
                    self._emit({"type": "shot_updated", "shot": summarize(upd, started)})
        self._emit({"type": "stats", "stats": self.stats(sid)})

    def _dropped_between(self, t0: float, t1: float) -> int:
        """Frames the cameras lost (summed over cameras) in source time [t0, t1]. A loss is
        recorded as the interval between the two delivered frames around the gap; camera B
        times are moved onto camera A's clock like the shot times."""
        cams = [c.cam_id for c in self._rcfg.sources]
        off = self._offset or 0.0
        total = 0
        with self._lock:
            for cam, events in self._drops.items():
                shift = off if len(cams) > 1 and cam == cams[1] else 0.0
                for ta, tb, n in events:
                    if tb + shift > t0 and ta + shift < t1:
                        total += n
        return total

    def _link_tips(self, shot, entry_t: Optional[float]) -> None:
        """Attribute pending HIVE tips to this MADE shot: the state changed between the
        shot's launch and launch + TIP_LINK_WINDOW_S, and the ball had entered by then."""
        with self._lock:
            pend = list(self._pending_tips)
        newest = shot.t_launch
        for rec in pend:
            if rec.caused_by is not None or rec.tip.session_id != shot.session_id:
                continue
            if not shot.t_launch <= rec.tip.t <= shot.t_launch + TIP_LINK_WINDOW_S:
                continue
            if entry_t is not None and entry_t > rec.tip.t + 0.15:
                continue
            rec.caused_by = shot.shot_id
            self.store.set_tip_cause(rec.tip_id, shot.shot_id)
        with self._lock:
            self._pending_tips = [r for r in self._pending_tips if r.caused_by is None
                                  and r.tip.t >= newest - 10.0]

    def stats(self, session_id: str) -> dict:
        return stats_to_dict(compute_stats(self.store.list_shots(session_id),
                                           self.store.list_tips(session_id), session_id))

    def _write_clips(self, shot) -> None:
        if not shot.track or not shot.track.points:
            return
        clip_dir = self.data_dir / "clips"
        cams = [c.cam_id for c in self._rcfg.sources]
        off = self._offset or 0.0      # cam B time + off = cam A time (shot times are cam A)
        jobs = []
        for cam, ring in list(self._ring.items()):
            # each camera's clip window lives on that camera's own clock
            shift = -off if len(cams) > 1 and cam == cams[1] else 0.0
            t0 = shot.track.points[0].t - 0.4 + shift
            t1 = shot.track.points[-1].t + 0.4 + shift
            with self._lock:
                # references only (cheap): the pin stops the ring from recycling these
                # buffers until the clip is written, so no 100 MB copy under the lock
                frames = [f for (t, f) in ring if t0 <= t <= t1]
                if len(frames) >= 2:
                    self._ring_pins[cam] = self._ring_pins.get(cam, 0) + 1
                else:
                    continue
            jobs.append((cam, frames))
        if not jobs:
            return
        clip_dir.mkdir(parents=True, exist_ok=True)

        def write(job) -> Optional[str]:
            cam, frames = job
            try:
                return self._write_clip(shot, cam, frames, clip_dir / f"{shot.shot_id}_{cam}.mp4")
            finally:
                with self._lock:
                    self._ring_pins[cam] = max(0, self._ring_pins.get(cam, 1) - 1)

        # one writer per camera: VideoWriter.write releases the GIL, so they run in parallel
        results: list[Optional[str]] = [None] * len(jobs)
        threads = []
        for i, job in enumerate(jobs[1:], start=1):
            def run(i=i, job=job):
                _thread_priority(-1)
                results[i] = write(job)
            th = threading.Thread(target=run, daemon=True, name=f"clip-{job[0]}")
            th.start()
            threads.append(th)
        results[0] = write(jobs[0])
        for th in threads:
            th.join()
        first = next((r for r in results if r), None)
        if first:
            self.store.set_clip_path(shot.shot_id, first)

    def _write_clip(self, shot, cam: str, frames: list, path: Path) -> Optional[str]:
        shape = frames[0].shape[:2]
        kept = [f for f in frames if f.shape[:2] == shape]
        if len(kept) != len(frames):
            log.warning("clip %s_%s: dropped %d frames whose size differs from %dx%d",
                        shot.shot_id, cam, len(frames) - len(kept), shape[1], shape[0])
        vw = None
        try:
            h, w = shape
            vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                                 self._cam_fps(cam), (w, h))
            if not vw.isOpened():
                return None
            for f in kept:
                vw.write(f)
            return str(path)
        except Exception:  # noqa: BLE001
            log.exception("clip write failed")
            return None
        finally:
            if vw is not None:
                vw.release()

    # ------------------------------------------------------------------ status
    def calibration_usable(self) -> bool:
        """True when every configured camera has intrinsics and extrinsics, whatever their
        provenance (the pipeline can reconstruct)."""
        intr, ext = self._calib
        cams = [s.cam_id for s in self._rcfg.sources]
        return len(cams) >= 2 and all(c in intr and c in ext for c in cams[:2])

    def calibration_loaded(self) -> bool:
        """A calibration the operator made (or the demo's): usable, and not merely the
        fixture-embedded convenience outside demo mode. The setup wizard opens while False."""
        if not self.calibration_usable():
            return False
        if self.demo:
            return True
        return not any(v == "fixture" for v in self.calibration_sources().values())

    def warnings(self, cameras: Optional[dict] = None) -> list[str]:
        """Human-readable reasons why the pipeline may not produce (good) shots."""
        out: list[str] = []
        cams = [s.cam_id for s in self._rcfg.sources]
        if len(cams) < 2:
            out.append("single-camera mode: no 3D reconstruction, no shots")
        elif not self.calibration_usable():
            out.append("no calibration loaded: 3D reconstruction disabled")
        for cam, msg in self.calibration_mismatch().items():
            out.append(f"camera {cam} resolution mismatch ({msg})")
        intr_now = self._calib[0]
        for cam in sorted(self._default_intr):
            fx = intr_now[cam].fx if cam in intr_now else 0.0
            out.append(f"camera {cam} uses default lens intrinsics (fx {fx:.0f}): "
                       "run the Lens step")
        for cam in sorted(self._intr_src):
            src, i = self._intr_src[cam], intr_now.get(cam)
            r = float(getattr(i, "reprojection_rmse_px", 0.0) or 0.0)
            if src == "measured_poor":
                out.append(f"camera {cam}: the lens calibration is poor (RMSE {r:.1f} px): "
                           "re-run the Lens step closer, 1.5-3 ft from the camera")
            elif src == "measured" and LENS_OK_RMSE_PX <= r <= LENS_POOR_RMSE_PX:
                out.append(f"camera {cam}: the lens calibration RMSE is {r:.1f} px (under 1 px "
                           "is good): consider re-running the Lens step closer, 1.5-3 ft")
        for cam in sorted(self._pair_stale):
            out.append(f"camera {cam}: its pose was not checked against the other camera "
                       "(the pair check failed when the other one was solved alone); "
                       "re-solve both with Auto-calibrate all")
        if self._unpaired:
            out.append(f"{self._unpaired} ball track(s) could not be paired between the "
                       "cameras and were dropped: shots may be missing")
        for cam in sorted(self._stale_ext):
            out.append(f"extrinsics for {cam} are stale (intrinsics were recalibrated)")
        for cid, st in (cameras or {}).items():
            if st.get("last_error"):
                out.append(f"camera {cid}: {st['last_error']}")
            elif st.get("is_alive") and not st.get("frames_read") and self._running:
                out.append(f"camera {cid}: connected but no frames received yet")
            if st.get("dropped"):
                out.append(f"camera {cid} dropped {st['dropped']} frames (processing too slow)")
        for cid in sorted(self._errors):
            if self._errors[cid]:
                out.append(f"camera {cid}: {self._errors[cid]} frame processing error(s), "
                           f"last: {self._err_last.get(cid, '')}")
        for cid in sorted(self._restart_total):
            out.append(f"camera {cid}: processing loop restarted {self._restart_total[cid]} "
                       "time(s) after an error")
        out.extend(self._stalls.values())
        if self.last_error:
            out.append(self.last_error)
        return out

    def hive_state_source(self) -> str:
        """"tags" once the tags have decided the state (or both states were learned) and
        the user has not overridden it since; "manual" otherwise."""
        if self._manual_override:
            return "manual"
        if self.hive_tags_ready() or self._hive_source == "tags":
            return "tags"
        return "manual"

    def status(self) -> dict:
        if self._running and self._finished.is_set():
            self._check_idle()          # the recon loop has exited; keep the idle clock honest
        cams: dict[str, dict] = {}
        for s in self._rcfg.sources:
            cams[s.cam_id] = {"fps": 0.0, "dropped": 0, "frames_read": 0, "is_alive": False,
                              "ended": False, "last_error": None, "reconnects": 0, "props": {}}
        for cid, r in self._readers.items():
            st = r.stats()
            st.pop("cam_id", None)
            # a file source that hit end-of-file cleanly: not alive, but ended
            ended = (r.spec.kind == SourceKind.FILE and bool(getattr(r, "finished", False))
                     and not st.get("last_error"))
            st["ended"] = ended
            if ended:
                st["is_alive"] = False
            cams[cid] = st
        csrc, isrc = self.calibration_sources(), self._intr_src
        for cid, d in cams.items():
            d["pair_stale"] = cid in self._pair_stale
            d["errors"] = int(self._errors.get(cid, 0))
            d["loop_restarts"] = int(self._restart_total.get(cid, 0))
            d["calibration_source"] = csrc.get(cid, "none")
            d["intrinsics_source"] = isrc.get(cid, "default")
        now = time.perf_counter()
        dfps = 0.0
        for dq in list(self._proc_times.values()):
            ts = [t for t in list(dq) if now - t <= 2.0]
            if len(ts) >= 2 and ts[-1] > ts[0]:
                dfps += (len(ts) - 1) / (ts[-1] - ts[0])
        h = self._hive
        per_cam = {c: {k: round(v, 3) for k, v in list(d.items())}
                   for c, d in list(self._timing.items())}
        timing = {}
        for k in TIMING_STAGES:
            vals = [d[k] for d in per_cam.values() if k in d]
            timing[k] = round(sum(vals) / len(vals), 3) if vals else 0.0
        timing["recon_ms"] = round(self._recon_ms or 0.0, 3)
        timing["offset_s"] = None if self._offset is None else round(self._offset, 4)
        timing["offset_confidence"] = (None if self._offset_conf is None
                                       else round(self._offset_conf, 3))
        return {
            "running": self.running,
            "demo": self.demo,
            "session_id": self._session_id,
            "calibration_mismatch": self.calibration_mismatch(),
            "calibration_loaded": self.calibration_loaded(),
            "calibration_source": self.calibration_source(),
            "intrinsics_default": any(v == "default" for v in isrc.values()),
            "hive_state_source": self.hive_state_source(),
            "warnings": self.warnings(cams),
            "cameras": cams,
            "detector_fps": dfps,
            "timing": timing,
            "timing_per_camera": per_cam,
            "last_shot_id": self._last_shot_id,
            "hive_state": {"alliance": h.alliance, "up_cell": h.up_cell},
            "rtmp": {"available": self.rtmp.is_available(), "running": self.rtmp.is_running(),
                     "urls": {s.cam_id: self.rtmp.url_for(s.cam_id) for s in self._rcfg.sources}},
        }
