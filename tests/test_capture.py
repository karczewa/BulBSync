"""Wybór metody przechwytywania ekranu, z atrapą dxcam (prawdziwy działa tylko na Windowsie)."""

import sys
import types

import numpy as np
import pytest

from bulbsync import ambient


class FakeCam:
    def __init__(self, color):
        self.color = color
        self.frames = 0
        self.released = False

    def grab(self):
        self.frames += 1
        if self.frames == 3:
            return None  # obraz się nie zmienił
        img = np.zeros((1080, 1920, 4), dtype=np.uint8)
        img[..., 0] = 255  # B
        img[..., 2] = 10 * self.frames  # R
        img[..., 3] = 255
        return img

    def release(self):
        self.released = True


def fake_dxcam(needs_cv2_for_rgb=True):
    mod = types.ModuleType("dxcam")
    mod.calls = []

    def create(output_idx=None, output_color="RGB", **kw):
        mod.calls.append((output_idx, output_color))
        # jak dxcam 0.3.0 bez skompilowanych rozszerzeń: RGB wymaga OpenCV
        if needs_cv2_for_rgb and output_color != "BGRA":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return FakeCam(output_color)

    mod.create = create
    return mod


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(ambient.sys, "platform", "win32")
    monkeypatch.setattr(ambient, "_MssCapture", lambda m: types.SimpleNamespace(name="GDI (mss)", m=m))


def test_dxcam_used_without_opencv(monkeypatch, windows):
    mod = fake_dxcam()
    monkeypatch.setitem(sys.modules, "dxcam", mod)
    cap, reason = ambient.open_capture(2)
    assert reason is None and cap.name.startswith("DXGI")
    assert mod.calls == [(1, "BGRA")]  # monitor 2 -> output 1, surowy format
    img = cap.grab()
    assert img.shape[1] == ambient.SAMPLE_WIDTH and img.flags.c_contiguous
    assert tuple(img[0, 0]) == (20, 0, 255)  # BGRA -> RGB
    assert tuple(cap.grab()[0, 0]) == (20, 0, 255)  # brak nowej klatki = poprzedni obraz
    assert tuple(cap.grab()[0, 0]) == (40, 0, 255)
    cap.close()
    assert cap.cam.released


def test_missing_dxcam_falls_back_with_reason(monkeypatch, windows):
    monkeypatch.setitem(sys.modules, "dxcam", None)  # import dxcam -> ImportError(name="dxcam")
    cap, reason = ambient.open_capture(1)
    assert cap.name == "GDI (mss)"
    assert "brak dxcam" in reason


def test_other_import_error_is_reported_by_name(monkeypatch, windows):
    mod = fake_dxcam()

    def create(**kw):
        raise ModuleNotFoundError("No module named 'comtypes'", name="comtypes")

    mod.create = create
    monkeypatch.setitem(sys.modules, "dxcam", mod)
    cap, reason = ambient.open_capture(1)
    assert cap.name == "GDI (mss)"
    assert "comtypes" in reason and "brak dxcam" not in reason
