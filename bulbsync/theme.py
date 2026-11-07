"""Kolory i czcionki interfejsu (ciemny motyw)."""

BG = "#111318"  # tło okna
SIDEBAR = "#0b0d11"
SURFACE = "#1a1d24"  # karty
SURFACE_2 = "#242832"  # pola, przyciski drugorzędne
SURFACE_3 = "#2f3440"  # hover
BORDER = "#2a2f3a"
TEXT = "#eceef3"
MUTED = "#8a90a0"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#6948f0"
OK = "#3ecf8e"
ERR = "#ff5c6c"
ERR_HOVER = "#e84a5a"
AMBIENT = "#b48cff"
OFF_DOT = "#3a3f4b"

FONT = "Segoe UI"  # na Windowsie; gdzie indziej Tk podstawi zamiennik

# Barwy bieli żarówki: ciepła (temp 0) -> zimna (temp 1000)
WARM_WHITE = (255, 166, 87)
NEUTRAL_WHITE = (255, 238, 222)
COLD_WHITE = (200, 223, 255)


def white_rgb(temp: float) -> tuple[int, int, int]:
    """Przybliżony kolor bieli dla temperatury Tuya 0-1000."""
    t = max(0.0, min(1.0, temp / 1000.0))
    a, b, f = (WARM_WHITE, NEUTRAL_WHITE, t * 2) if t < 0.5 else (NEUTRAL_WHITE, COLD_WHITE, (t - 0.5) * 2)
    return tuple(int(round(x + (y - x) * f)) for x, y in zip(a, b))


def hex_of(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)
