"""Video ingest: sources, threaded capture with bounded drop-oldest queue,
multi-camera container and device probing."""

from __future__ import annotations

import collections
import itertools
import logging
import math
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from hiveshot.models import SourceKind

log = logging.getLogger("hiveshot.ingest")

_BACKENDS = {
    "msmf": cv2.CAP_MSMF,
    "dshow": cv2.CAP_DSHOW,
    "ffmpeg": cv2.CAP_FFMPEG,
}

# Reported fps outside (0, _FPS_MAX] (or NaN) is replaced by the measured fps
# once this many seconds of reads exist; fps_hint or 30 until then.
_FPS_MAX = 240.0
_FPS_MEASURE_AFTER_S = 2.0
_LATENCY_WINDOW = 60


@dataclass
class SourceSpec:
    cam_id: str
    kind: SourceKind
    target: str | int
    fps_hint: float | None = None
    width: int | None = None
    height: int | None = None
    backend: str = "auto"      # "auto" | "msmf" | "dshow" | "ffmpeg"
    loop: bool = False
    realtime: bool = False     # FILE only: pace delivery at the file's fps


@dataclass
class Frame:
    cam_id: str
    frame_idx: int
    t_capture: float           # time.perf_counter() right after read returned
    t_source: float | None  # source clock seconds (files), else None
    image: np.ndarray          # BGR


def _resolve_backend(spec: SourceSpec) -> tuple[int, str]:
    b = spec.backend.lower()
    if b != "auto":
        if b not in _BACKENDS:
            raise ValueError(f"unknown backend {spec.backend!r}")
        return _BACKENDS[b], b
    if spec.kind == SourceKind.DEVICE:
        if sys.platform == "win32":
            return cv2.CAP_MSMF, "msmf"
        return cv2.CAP_ANY, "any"
    return cv2.CAP_FFMPEG, "ffmpeg"


class VideoSource:
    """Thin wrapper over cv2.VideoCapture producing Frame objects."""

    def __init__(self, spec: SourceSpec):
        self.spec = spec
        self._cap: cv2.VideoCapture | None = None
        self._api, self._backend_name = _resolve_backend(spec)
        self._idx = 0
        self._loop_offset_s = 0.0
        self._last_src_s = 0.0
        self._last_pos_msec = 0.0
        self._t_first: float | None = None
        self._t_last = 0.0
        self._n_read = 0
        self._open()

    def _open(self) -> None:
        spec = self.spec
        target: Any = spec.target
        if spec.kind == SourceKind.DEVICE:
            if isinstance(target, str) and not target.isdigit():
                target = f"video={target}"
                if self._backend_name == "msmf":
                    # MSMF has no name addressing; DirectShow does.
                    self._api, self._backend_name = cv2.CAP_DSHOW, "dshow"
            else:
                target = int(target)
        cap = cv2.VideoCapture(target, self._api)
        if not cap.isOpened():
            cap.release()
            raise OSError(
                f"cannot open {spec.kind.value} source {spec.target!r} "
                f"for cam {spec.cam_id!r} (backend {self._backend_name})"
            )
        if spec.kind == SourceKind.DEVICE:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            if spec.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, spec.width)
            if spec.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, spec.height)
            if spec.fps_hint:
                cap.set(cv2.CAP_PROP_FPS, spec.fps_hint)
        self._cap = cap
        log.info("opened %s: %s", spec.cam_id, self.props())

    def props(self) -> dict:
        cap = self._cap
        if cap is None:
            return {"width": 0, "height": 0, "fps": 0.0, "fps_reported": 0.0,
                    "backend": self._backend_name}
        raw = float(cap.get(cv2.CAP_PROP_FPS))
        fps = raw
        if not (math.isfinite(raw) and 0.0 < raw <= _FPS_MAX):
            fps = self._fallback_fps()
        return {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": fps,
            "fps_reported": raw,
            "backend": self._backend_name,
        }

    def _fallback_fps(self) -> float:
        """Measured fps once enough reads span _FPS_MEASURE_AFTER_S, else
        fps_hint or 30."""
        if (self._t_first is not None and self._n_read >= 2
                and self._t_last - self._t_first >= _FPS_MEASURE_AFTER_S):
            m = (self._n_read - 1) / (self._t_last - self._t_first)
            if math.isfinite(m) and 0.0 < m <= _FPS_MAX:
                return m
        return self.spec.fps_hint or 30.0

    def read(self) -> Frame | None:
        cap = self._cap
        if cap is None:
            return None
        ok, img = cap.read()
        if (not ok or img is None) and self.spec.kind == SourceKind.FILE \
                and self.spec.loop:
            fps = cap.get(cv2.CAP_PROP_FPS) or self.spec.fps_hint or 30.0
            self._loop_offset_s = self._last_src_s + 1.0 / fps + self._loop_offset_s
            self._last_src_s = 0.0
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = cap.read()
            if not ok or img is None:  # reopen as a fallback
                cap.release()
                self._open()
                cap = self._cap
                ok, img = cap.read()  # type: ignore[union-attr]
        t_cap = time.perf_counter()
        if not ok or img is None:
            return None
        if self._t_first is None:
            self._t_first = t_cap
        self._t_last = t_cap
        self._n_read += 1
        t_src: float | None = None
        if self.spec.kind == SourceKind.DEVICE:
            # Backend-provided timestamp, only if non-zero and increasing.
            pos = cap.get(cv2.CAP_PROP_POS_MSEC)
            if pos and math.isfinite(pos) and pos > self._last_pos_msec:
                self._last_pos_msec = pos
                t_src = pos / 1000.0
        elif self.spec.kind == SourceKind.FILE:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            cur = cap.get(cv2.CAP_PROP_POS_FRAMES)
            if fps > 0 and cur >= 1:
                src_s = (cur - 1) / fps
            else:
                src_s = max(cap.get(cv2.CAP_PROP_POS_MSEC), 0.0) / 1000.0
            self._last_src_s = src_s
            t_src = self._loop_offset_s + src_s
        fr = Frame(self.spec.cam_id, self._idx, t_cap, t_src, img)
        self._idx += 1
        return fr

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class CaptureThread:
    """Runs a VideoSource in a daemon thread feeding a drop-oldest queue."""

    def __init__(self, spec: SourceSpec, maxsize: int = 8,
                 backoff_min: float = 0.5, backoff_max: float = 5.0):
        self.spec = spec
        self.maxsize = maxsize
        self.backoff_min = backoff_min
        self.backoff_max = backoff_max
        self._dq: collections.deque[Frame] = collections.deque()
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._source: VideoSource | None = None
        self._latest: Frame | None = None
        self._times: collections.deque[float] = collections.deque(maxlen=2000)
        self.dropped = 0
        self.frames_read = 0
        self.reconnects = 0
        self.last_error: str | None = None
        self.props: dict = {}
        # File source reached EOF, failed to open, or hit a permanent read
        # error (no reconnect). Always paired with last_error on failure.
        self.finished = False

    def start(self) -> CaptureThread:
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._run, name=f"capture-{self.spec.cam_id}", daemon=True)
        self._thread.start()
        return self

    def _push(self, fr: Frame) -> None:
        with self._cv:
            if len(self._dq) >= self.maxsize:
                self._dq.popleft()
                self.dropped += 1
            self._dq.append(fr)
            self._latest = fr
            self.frames_read += 1
            self._times.append(fr.t_capture)
            self._cv.notify_all()

    def _pace(self, frame_idx: int, t_start: float) -> None:
        """Sleep until frame_idx/fps after t_start (max 0.25 s); never skips."""
        fps = (self.props.get("fps") or 0.0) or self.spec.fps_hint or 30.0
        wait = t_start + frame_idx / fps - time.perf_counter()
        if wait > 0:
            self._stop.wait(min(wait, 0.25))

    def _run(self) -> None:
        try:
            self._run_inner()
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            log.exception("%s: capture thread crashed", self.spec.cam_id)
        finally:
            if self.spec.kind == SourceKind.FILE and not self._stop.is_set():
                self.finished = True
            with self._cv:
                self._cv.notify_all()

    def _run_inner(self) -> None:
        reconnectable = self.spec.kind != SourceKind.FILE
        backoff = self.backoff_min
        first = True
        t_start = time.perf_counter()
        while not self._stop.is_set():
            try:
                self._source = VideoSource(self.spec)
                self.props = self._source.props()
                self.last_error = None
                if not first:
                    self.reconnects += 1
                first = False
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
                log.warning("%s: open failed: %s", self.spec.cam_id, e)
                if not reconnectable:
                    self.finished = True
                    break
                if self._stop.wait(backoff):
                    break
                backoff = min(backoff * 2, self.backoff_max)
                continue
            got_any = False
            while not self._stop.is_set():
                try:
                    fr = self._source.read()
                except Exception as e:  # noqa: BLE001
                    self.last_error = str(e)
                    fr = None
                if fr is None:
                    break
                got_any = True
                backoff = self.backoff_min
                if self.spec.realtime and self.spec.kind == SourceKind.FILE:
                    self._pace(fr.frame_idx, t_start)
                    fr.t_capture = time.perf_counter()
                self._push(fr)
                if fr.frame_idx % 30 == 29:
                    self.props = self._source.props()  # refresh measured fps
            self._source.close()
            if self._stop.is_set():
                break
            if not reconnectable:
                self.finished = True
                break
            if not got_any:
                self.last_error = self.last_error or "no frames received"
            log.warning("%s: stream lost, reconnecting in %.1fs",
                        self.spec.cam_id, backoff)
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, self.backoff_max)

    def latest(self) -> Frame | None:
        with self._cv:
            return self._latest

    def get(self, timeout: float | None = None) -> Frame | None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            while not self._dq:
                if self._stop.is_set() or self.finished:
                    return None
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._cv.wait(0.05 if remaining is None else min(remaining, 0.05))
            return self._dq.popleft()

    def stats(self) -> dict:
        with self._cv:
            now = time.perf_counter()
            ts = [t for t in self._times if now - t <= 2.0]
            fps = 0.0
            if len(ts) >= 2 and ts[-1] > ts[0]:
                fps = (len(ts) - 1) / (ts[-1] - ts[0])
            # Diagnostic only: crude buffering indicator. Median over the last
            # 60 frame intervals of (inter-arrival - 1/nominal fps), >= 0.
            lat = 0.0
            tl = list(self._times)[-(_LATENCY_WINDOW + 1):]
            if len(tl) >= 3:
                nominal = (self.props.get("fps") or 0.0) or self.spec.fps_hint or 30.0
                lat = max(0.0, statistics.median(
                    (b - a) - 1.0 / nominal for a, b in itertools.pairwise(tl)))
            return {
                "cam_id": self.spec.cam_id,
                "fps": fps,
                "latency_estimate_s": lat,
                "finished": self.finished,
                "dropped": self.dropped,
                "frames_read": self.frames_read,
                "is_alive": bool(self._thread and self._thread.is_alive()),
                "last_error": self.last_error,
                "reconnects": self.reconnects,
                "props": dict(self.props),
            }

    def request_stop(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()

    def stop(self, timeout: float = 2.0) -> None:
        self.request_stop()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("%s: capture thread did not stop in %.1fs",
                            self.spec.cam_id, timeout)


class MultiCapture:
    def __init__(self, specs: list[SourceSpec], maxsize: int = 8):
        self.threads: dict[str, CaptureThread] = {
            s.cam_id: CaptureThread(s, maxsize=maxsize) for s in specs}

    def start(self) -> MultiCapture:
        for t in self.threads.values():
            t.start()
        return self

    def latest_all(self) -> dict[str, Frame]:
        out = {}
        for cid, t in self.threads.items():
            fr = t.latest()
            if fr is not None:
                out[cid] = fr
        return out

    def stats_all(self) -> dict[str, dict]:
        return {cid: t.stats() for cid, t in self.threads.items()}

    def stop_all(self) -> None:
        for t in self.threads.values():
            t.request_stop()
        for t in self.threads.values():
            t.stop()


def _probe_one(index: int, out: dict) -> None:
    cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
    try:
        if cap.isOpened():
            ok, _ = cap.read()
            out["info"] = {
                "index": index,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(cap.get(cv2.CAP_PROP_FPS)),
                "read_ok": bool(ok),
            }
    finally:
        cap.release()


_DEVICE_CACHE_TTL_S = 30.0
_device_cache: tuple[float, int, list[dict]] | None = None


def list_devices(max_index: int = 10, per_index_timeout: float = 1.0,
                 first_index_timeout: float = 2.5,
                 use_cache: bool = True) -> list[dict]:
    """Probe device indices 0..max_index-1 with MSMF; skip any that hang.

    Index 0 gets first_index_timeout (cold MSMF init is slow), the rest
    per_index_timeout. The last non-empty result is cached for 30 s.
    """
    global _device_cache
    c = _device_cache
    if (use_cache and c is not None and c[1] == max_index
            and time.monotonic() - c[0] < _DEVICE_CACHE_TTL_S):
        return [dict(d) for d in c[2]]
    found = []
    # Quiet OpenCV's per-index MSMF warnings during the probe, then restore.
    logging_api = getattr(getattr(cv2, "utils", None), "logging", None)
    old_level = None
    if logging_api is not None:
        old_level = logging_api.getLogLevel()
        logging_api.setLogLevel(logging_api.LOG_LEVEL_ERROR)
    try:
        _probe_all(max_index, per_index_timeout, found, first_index_timeout)
    finally:
        if logging_api is not None:
            logging_api.setLogLevel(old_level)
    if found:
        _device_cache = (time.monotonic(), max_index, [dict(d) for d in found])
    return found


def _probe_all(max_index: int, per_index_timeout: float, found: list,
               first_index_timeout: float | None = None) -> None:
    for i in range(max_index):
        out: dict = {}
        th = threading.Thread(target=_probe_one, args=(i, out), daemon=True)
        th.start()
        th.join(first_index_timeout
                if i == 0 and first_index_timeout is not None
                else per_index_timeout)
        if th.is_alive():
            log.warning("device probe %d timed out", i)
            continue
        if "info" in out:
            found.append(out["info"])
