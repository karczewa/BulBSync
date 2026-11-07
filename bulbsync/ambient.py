"""Silnik ambient: przechwytuje ekran, liczy kolor dla każdej strefy i podaje go żarówkom."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np

from .color import Smoother, process_ambient, zone_color, zone_rect

SAMPLE_WIDTH = 192  # ekran zmniejszamy do takiej szerokości przed liczeniem kolorów


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
        try:
            with _open_mss() as sct:
                self._loop(sct)
        except ImportError:
            self.events.put(("ambient_error", "Brak biblioteki mss: python -m pip install mss"))
        except Exception as e:
            self.events.put(("ambient_error", f"Błąd przechwytywania ekranu: {e}"))
        finally:
            for _, worker, _ in self.assignments():
                worker.stop_ambient()
            self.events.put(("ambient_stopped", None))

    def _grab(self, sct) -> np.ndarray:
        cfg = self.settings["ambient"]
        mons = sct.monitors
        idx = int(cfg.get("monitor", 1))
        if not 1 <= idx < len(mons):
            idx = 1 if len(mons) > 1 else 0
        shot = sct.grab(mons[idx])
        arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        step = max(1, shot.width // SAMPLE_WIDTH)
        # BGRA -> RGB i zmniejszenie przez branie co n-tego piksela
        return arr[::step, ::step, 2::-1]

    def _loop(self, sct) -> None:
        frames = 0
        fps_t0 = time.monotonic()
        while not self._stopping.is_set():
            t0 = time.monotonic()
            cfg = self.settings["ambient"]
            img = self._grab(sct)
            h, w = img.shape[:2]
            preview = {}
            for bulb_id, worker, zone in self.assignments():
                x0, y0, x1, y1 = zone_rect(w, h, zone, cfg["edge_depth"] / 100.0)
                rgb = zone_color(img[y0:y1, x0:x1], cfg["method"])
                sm = self._smoothers.setdefault(bulb_id, Smoother())
                rgb = sm.update(rgb, cfg["smoothing"])
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
                self.events.put(("ambient_fps", frames / (now - fps_t0)))
                frames, fps_t0 = 0, now
            self.events.put(("ambient_preview", preview))
            fps = max(1.0, float(cfg["fps"]))
            delay = 1.0 / fps - (time.monotonic() - t0)
            if delay > 0:
                self._stopping.wait(delay)
