"""Silnik ambient: przechwytuje ekran, liczy kolor dla każdej strefy i podaje go żarówkom."""

from __future__ import annotations

import queue
import sys
import threading
import time

import numpy as np

from .color import Smoother, process_ambient, zone_color, zone_rect

SAMPLE_WIDTH = 192  # ekran zmniejszamy do takiej szerokości przed liczeniem kolorów
MAX_FPS = 60


def _open_mss():
    import mss

    # mss 10.2+ ma klasę MSS, a starsze wersje tylko funkcję mss.mss()
    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()


def list_monitors() -> list[str]:
    """Opisy monitorów dla listy wyboru; indeks 1 = pierwszy monitor (0 w mss = wszystkie razem)."""
    try:
        with _open_mss() as sct:
            mons = sct.monitors
    except Exception:
        return ["1: monitor główny"]
    return [f"{i}: {m['width']}x{m['height']}" for i, m in enumerate(mons) if i > 0] or ["1: monitor główny"]


def _downsample(rgb: np.ndarray) -> np.ndarray:
    step = max(1, rgb.shape[1] // SAMPLE_WIDTH)
    return rgb[::step, ::step]


class _MssCapture:
    name = "GDI (mss)"

    def __init__(self, monitor: int):
        self.sct = _open_mss()
        mons = self.sct.monitors
        self.mon = mons[monitor] if 1 <= monitor < len(mons) else mons[1 if len(mons) > 1 else 0]

    def grab(self) -> np.ndarray:
        shot = self.sct.grab(self.mon)
        arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        step = max(1, shot.width // SAMPLE_WIDTH)
        return arr[::step, ::step, 2::-1]  # BGRA -> RGB

    def close(self):
        try:
            self.sct.close()
        except Exception:
            pass


class _DxcamCapture:
    """Windows Desktop Duplication (DXGI): kilka razy szybsze niż GDI, mniej obciąża procesor."""

    name = "DXGI (dxcam)"

    def __init__(self, monitor: int):
        import dxcam  # opcjonalne: python -m pip install dxcam

        self.cam = dxcam.create(output_idx=max(0, monitor - 1), output_color="RGB")
        if self.cam is None:
            raise RuntimeError("dxcam nie utworzył kamery")
        self.last = None
        frame = None
        for _ in range(20):  # pierwsza klatka bywa pusta
            frame = self.cam.grab()
            if frame is not None:
                break
            time.sleep(0.02)
        if frame is None:
            raise RuntimeError("dxcam nie zwrócił obrazu")
        self.last = _downsample(frame).copy()

    def grab(self) -> np.ndarray:
        frame = self.cam.grab()
        if frame is not None:  # None = obraz się nie zmienił od ostatniej klatki
            self.last = _downsample(frame).copy()
        return self.last

    def close(self):
        try:
            release = getattr(self.cam, "release", None)
            if release:
                release()
        except Exception:
            pass


def open_capture(monitor: int):
    """Najszybsza dostępna metoda. Zwraca (capture, powód, dla którego DXGI nie działa, albo None)."""
    reason = None
    if sys.platform == "win32":
        try:
            return _DxcamCapture(monitor), None
        except ImportError:
            reason = "brak dxcam (python -m pip install dxcam)"
        except Exception as e:  # dxcam jest, ale nie działa na tym sprzęcie/monitorze
            reason = f"dxcam: {e}"[:120]
    return _MssCapture(monitor), reason


class _HighResTimer:
    """Na Windowsie domyślny zegar ma krok ~15,6 ms, więc krótkie czekanie trwa za długo
    i 60 kl/s zamienia się w ~40. timeBeginPeriod(1) zmniejsza krok do 1 ms na czas działania ambientu."""

    def __enter__(self):
        self.on = False
        if sys.platform == "win32":
            try:
                import ctypes

                self.on = ctypes.windll.winmm.timeBeginPeriod(1) == 0
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        if self.on:
            try:
                import ctypes

                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


class AmbientEngine(threading.Thread):
    """`settings` to wspólny słownik ustawień, czytany na bieżąco, więc zmiany suwaków działają od razu.

    `assignments()` zwraca listę (bulb_id, worker, zone) żarówek biorących udział.
    """

    def __init__(self, settings: dict, assignments, events: "queue.Queue"):
        super().__init__(daemon=True, name="ambient")
        self.settings = settings
        self.assignments = assignments
        self.events = events
        self._stopping = threading.Event()
        self._smoothers: dict[str, Smoother] = {}

    def stop(self) -> None:
        self._stopping.set()

    def run(self) -> None:
        cap = None
        try:
            cap, reason = open_capture(int(self.settings["ambient"].get("monitor", 1)))
            self.events.put(("ambient_backend", (cap.name, reason)))
            with _HighResTimer():
                self._loop(cap)
        except ImportError:
            self.events.put(("ambient_error", "Brak biblioteki mss: python -m pip install mss"))
        except Exception as e:
            self.events.put(("ambient_error", f"Błąd przechwytywania ekranu: {e}"))
        finally:
            if cap:
                cap.close()
            for _, worker, _ in self.assignments():
                worker.stop_ambient()
            self.events.put(("ambient_stopped", None))

    def _loop(self, cap) -> None:
        frames = 0
        fps_t0 = last_t = next_t = time.monotonic()
        cap_ms = 0.0
        monitor = self.settings["ambient"].get("monitor", 1)
        sends0 = {bid: w.ambient_sends for bid, w, _ in self.assignments()}
        while not self._stopping.is_set():
            t0 = time.monotonic()
            dt, last_t = t0 - last_t, t0
            cfg = self.settings["ambient"]
            if cfg.get("monitor", 1) != monitor:  # zmieniono monitor w trakcie
                cap.close()
                monitor = cfg.get("monitor", 1)
                cap, reason = open_capture(int(monitor))
                self.events.put(("ambient_backend", (cap.name, reason)))
            g0 = time.perf_counter()
            img = cap.grab()
            cap_ms = cap_ms * 0.9 + (time.perf_counter() - g0) * 1000 * 0.1
            h, w = img.shape[:2]
            preview = {}
            for bulb_id, worker, zone in self.assignments():
                x0, y0, x1, y1 = zone_rect(w, h, zone, cfg["edge_depth"] / 100.0)
                rgb = zone_color(img[y0:y1, x0:x1], cfg["method"])
                sm = self._smoothers.setdefault(bulb_id, Smoother())
                rgb = sm.update(rgb, cfg["smoothing"], dt)
                hsv = process_ambient(
                    rgb,
                    saturation=cfg["saturation"],
                    min_brightness=cfg["min_brightness"],
                    max_brightness=cfg["max_brightness"],
                    black_threshold=cfg["black_threshold"],
                )
                worker.set_ambient(hsv, bool(cfg["gradient"]))
                preview[bulb_id] = hsv
            frames += 1
            now = time.monotonic()
            if now - fps_t0 >= 1.0:
                span = now - fps_t0
                rates = {}
                for bid, wk, _ in self.assignments():
                    rates[bid] = (wk.ambient_sends - sends0.get(bid, wk.ambient_sends)) / span
                    sends0[bid] = wk.ambient_sends
                self.events.put(("ambient_fps", (frames / span, rates, cap_ms)))
                frames, fps_t0 = 0, now
            self.events.put(("ambient_preview", preview))
            # stałe tempo: kolejna klatka o wyznaczonym czasie, a nie "teraz + przerwa"
            period = 1.0 / min(MAX_FPS, max(1.0, float(cfg["fps"])))
            next_t += period
            now = time.monotonic()
            if next_t < now - period:  # nie nadążamy: nie próbuj nadrabiać zaległych klatek
                next_t = now
            while not self._stopping.is_set():
                left = next_t - time.monotonic()
                if left <= 0:
                    break
                time.sleep(min(left, 0.02))
