"""Czyste funkcje kolorów: konwersje do formatu Tuya, strefy ekranu, przetwarzanie ambient.

Nic tu nie dotyka sieci ani ekranu, więc wszystko da się przetestować.
"""

from __future__ import annotations

import colorsys

import numpy as np

# --- Format Tuya -----------------------------------------------------------------

# colour_data_v2 (DP 24) i music_data (DP 27): H 0-360, S 0-1000, V 0-1000, każde jako 4 znaki hex.
V_MIN = 10  # poniżej żarówki gasną albo zachowują się dziwnie


def rgb_to_tuya_hsv(r: float, g: float, b: float) -> tuple[int, int, int]:
    """RGB 0-255 -> (H 0-360, S 0-1000, V 0-1000)."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return int(round(h * 360)) % 360, int(round(s * 1000)), int(round(v * 1000))


def tuya_hsv_to_rgb(h: int, s: int, v: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s / 1000.0, v / 1000.0)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def colour_data_v2(h: int, s: int, v: int) -> str:
    """Wartość dla DP 24 (colour_data_v2): 'hhhhssssvvvv'."""
    return f"{_clamp(int(h), 0, 360):04x}{_clamp(int(s), 0, 1000):04x}{_clamp(int(v), 0, 1000):04x}"


def parse_colour_data_v2(value: str) -> tuple[int, int, int] | None:
    try:
        if len(value) != 12:
            return None
        return int(value[0:4], 16), int(value[4:8], 16), int(value[8:12], 16)
    except (TypeError, ValueError):
        return None


def music_data(h: int, s: int, v: int, gradient: bool = False) -> str:
    """Wartość dla DP 27 (music_data), ten sam kanał co synchronizacja z muzyką w aplikacji.

    Format: 1 znak trybu (0 = skok, 1 = płynne przejście), H, S, V po 4 hex,
    potem jasność i temperatura bieli (nieużywane w trybie koloru).
    """
    return ("1" if gradient else "0") + colour_data_v2(h, s, v) + "00000000"


# --- Strefy ekranu ---------------------------------------------------------------

ZONES = {
    "full": "Cały ekran",
    "left": "Lewa krawędź",
    "right": "Prawa krawędź",
    "top": "Górna krawędź",
    "bottom": "Dolna krawędź",
    "center": "Środek",
    "top-left": "Lewy górny róg",
    "top-right": "Prawy górny róg",
    "bottom-left": "Lewy dolny róg",
    "bottom-right": "Prawy dolny róg",
}


def zone_rect(width: int, height: int, zone: str, depth: float) -> tuple[int, int, int, int]:
    """Prostokąt (x0, y0, x1, y1) strefy. `depth` (0-1) to grubość pasa krawędzi."""
    depth = _clamp(depth, 0.05, 1.0)
    dw = max(1, int(round(width * depth)))
    dh = max(1, int(round(height * depth)))
    if zone == "left":
        return 0, 0, dw, height
    if zone == "right":
        return width - dw, 0, width, height
    if zone == "top":
        return 0, 0, width, dh
    if zone == "bottom":
        return 0, height - dh, width, height
    if zone == "center":
        cw, ch = max(1, int(width * 0.5)), max(1, int(height * 0.5))
        x0, y0 = (width - cw) // 2, (height - ch) // 2
        return x0, y0, x0 + cw, y0 + ch
    if zone == "top-left":
        return 0, 0, dw, dh
    if zone == "top-right":
        return width - dw, 0, width, dh
    if zone == "bottom-left":
        return 0, height - dh, dw, height
    if zone == "bottom-right":
        return width - dw, height - dh, width, height
    return 0, 0, width, height


def zone_color(pixels: np.ndarray, method: str = "vibrant") -> tuple[float, float, float]:
    """Kolor strefy z tablicy pikseli (H, W, 3) RGB uint8.

    - "average": zwykła średnia, wychodzi szarawo, ale wiernie.
    - "vibrant": średnia ważona nasyceniem i jasnością, więc wyraziste kolory
      wygrywają z szarym/czarnym tłem. Zwykle lepiej wygląda w grach.
    """
    px = pixels.reshape(-1, 3).astype(np.float32)
    if px.size == 0:
        return 0.0, 0.0, 0.0
    if method == "average":
        m = px.mean(axis=0)
        return float(m[0]), float(m[1]), float(m[2])
    mx = px.max(axis=1)
    mn = px.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    val = mx / 255.0
    w = (sat * val) ** 2 + 0.02
    m = (px * w[:, None]).sum(axis=0) / w.sum()
    # Ważenie przesuwa jasność w górę; przywracamy jasność zgodną ze średnią sceny.
    scene_v = float(val.mean())
    m_v = float(m.max()) / 255.0
    if m_v > 1e-6:
        m = m * min(1.0, scene_v / m_v * 1.5)
    return float(m[0]), float(m[1]), float(m[2])


# --- Przetwarzanie ambient ---------------------------------------------------------


SMOOTHING_REFERENCE_DT = 0.1  # suwak wygładzania jest skalibrowany dla 10 klatek/s


class Smoother:
    """Wygładzanie wykładnicze, żeby światło nie migało przy każdej zmianie klatki.

    Liczone względem czasu, a nie klatek, więc to samo ustawienie daje tę samą
    płynność przy 10 i przy 60 klatkach/s (przy 60 po prostu z drobniejszymi krokami).
    """

    def __init__(self):
        self.value: np.ndarray | None = None

    def update(self, rgb, factor: float, dt: float = SMOOTHING_REFERENCE_DT) -> tuple[float, float, float]:
        new = np.asarray(rgb, dtype=np.float32)
        if self.value is None or factor <= 0:
            self.value = new
        else:
            f = _clamp(factor, 0.0, 0.98) ** (max(dt, 0.0) / SMOOTHING_REFERENCE_DT)
            self.value = self.value * f + new * (1.0 - f)
        return tuple(float(x) for x in self.value)

    def reset(self):
        self.value = None


def process_ambient(
    rgb,
    saturation: float = 1.5,
    min_brightness: float = 5.0,
    max_brightness: float = 100.0,
    black_threshold: float = 4.0,
) -> tuple[int, int, int]:
    """Kolor z ekranu -> (H, S, V) Tuya, z podbiciem nasycenia i mapowaniem jasności.

    Jasności w procentach. Ekran ciemniejszy niż `black_threshold` % daje jasność minimalną.
    """
    r, g, b = (_clamp(c, 0, 255) / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = _clamp(s * saturation, 0.0, 1.0)
    lo = _clamp(min_brightness, 1, 100) / 100.0
    hi = _clamp(max_brightness, 1, 100) / 100.0
    if hi < lo:
        lo, hi = hi, lo
    if v * 100 < black_threshold:
        out_v = lo
    else:
        out_v = lo + (hi - lo) * v
    return (
        int(round(h * 360)) % 360,
        int(round(s * 1000)),
        max(V_MIN, int(round(out_v * 1000))),
    )


def hsv_close(a, b, tol_h: int = 3, tol_sv: int = 15) -> bool:
    """Czy dwa kolory Tuya są na tyle podobne, że nie warto wysyłać zmiany."""
    if a is None or b is None:
        return False
    dh = abs(a[0] - b[0]) % 360
    dh = min(dh, 360 - dh)
    return dh <= tol_h and abs(a[1] - b[1]) <= tol_sv and abs(a[2] - b[2]) <= tol_sv
