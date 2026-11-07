import numpy as np
import pytest

from bulbsync.color import (
    Smoother,
    colour_data_v2,
    hsv_close,
    music_data,
    parse_colour_data_v2,
    process_ambient,
    rgb_to_tuya_hsv,
    tuya_hsv_to_rgb,
    zone_color,
    zone_rect,
)


def test_colour_data_v2_format_and_roundtrip():
    assert colour_data_v2(0, 1000, 1000) == "000003e803e8"
    assert colour_data_v2(360, 0, 10) == "01680000000a"
    assert parse_colour_data_v2(colour_data_v2(123, 456, 789)) == (123, 456, 789)
    assert parse_colour_data_v2("bad") is None
    assert parse_colour_data_v2(None) is None


def test_colour_data_clamps():
    assert colour_data_v2(999, 5000, -3) == colour_data_v2(360, 1000, 0)


def test_music_data_matches_screensync_format():
    # ScreenSync wysyła: "0" + H + S + V + "00000000" i to działa na tych żarówkach
    assert music_data(240, 1000, 500) == "000f003e801f400000000"
    assert music_data(240, 1000, 500, gradient=True).startswith("1")
    assert len(music_data(0, 0, 0)) == 21


@pytest.mark.parametrize("rgb", [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 128, 0), (40, 40, 40)])
def test_hsv_roundtrip(rgb):
    back = tuya_hsv_to_rgb(*rgb_to_tuya_hsv(*rgb))
    assert all(abs(a - b) <= 2 for a, b in zip(rgb, back))


def test_zone_rects():
    assert zone_rect(100, 50, "left", 0.25) == (0, 0, 25, 50)
    assert zone_rect(100, 50, "right", 0.25) == (75, 0, 100, 50)
    assert zone_rect(100, 50, "top", 0.2) == (0, 0, 100, 10)
    assert zone_rect(100, 50, "bottom", 0.2) == (0, 40, 100, 50)
    assert zone_rect(100, 50, "full", 0.2) == (0, 0, 100, 50)
    x0, y0, x1, y1 = zone_rect(100, 50, "center", 0.2)
    assert (x1 - x0, y1 - y0) == (50, 25)


def test_zone_color_average_and_vibrant():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:, :2] = (255, 0, 0)  # 20% czerwieni na czarnym tle
    avg = zone_color(img, "average")
    assert avg[0] == pytest.approx(51, abs=1)
    vib = zone_color(img, "vibrant")
    h, s, _ = rgb_to_tuya_hsv(*vib)
    assert h == 0 and s > 950  # wyraźnie czerwony, nie szary


def test_zone_color_empty():
    assert zone_color(np.zeros((0, 0, 3), dtype=np.uint8)) == (0.0, 0.0, 0.0)


def test_process_ambient_brightness_mapping():
    # czarny ekran -> jasność minimalna
    assert process_ambient((0, 0, 0), min_brightness=5, max_brightness=100)[2] == 50
    # pełna biel -> jasność maksymalna, zero nasycenia
    h, s, v = process_ambient((255, 255, 255), min_brightness=5, max_brightness=80)
    assert (s, v) == (0, 800)
    # nasycenie podbite i przycięte do 1000
    assert process_ambient((255, 128, 128), saturation=3.0)[1] == 1000
    # nigdy poniżej V_MIN
    assert process_ambient((0, 0, 0), min_brightness=0)[2] >= 10


def test_smoother():
    sm = Smoother()
    assert sm.update((100, 0, 0), 0.5) == (100, 0, 0)
    assert sm.update((0, 0, 0), 0.5) == (50, 0, 0)
    assert sm.update((0, 0, 0), 0) == (0, 0, 0)


def test_hsv_close():
    assert hsv_close((359, 500, 500), (1, 505, 495))
    assert not hsv_close((0, 500, 500), (20, 500, 500))
    assert not hsv_close(None, (0, 0, 0))


def test_smoother_is_time_based():
    """To samo ustawienie po 1 s daje ten sam efekt przy 10 i 60 klatkach/s."""
    results = []
    for fps in (10, 60):
        sm = Smoother()
        sm.update((0, 0, 0), 0.5, 1 / fps)
        for _ in range(fps):
            out = sm.update((255, 0, 0), 0.5, 1 / fps)
        results.append(out[0])
    assert results[0] == pytest.approx(results[1], abs=0.5)
    assert 250 < results[0] < 255


def test_white_rgb_and_wheel_colors():
    from bulbsync.theme import COLD_WHITE, WARM_WHITE, white_rgb
    from bulbsync.widgets import hsv_to_rgb_np

    assert white_rgb(0) == WARM_WHITE and white_rgb(1000) == COLD_WHITE
    h = np.array([0.0, 1 / 3, 2 / 3])
    r, g, b = hsv_to_rgb_np(h, np.ones(3), np.ones(3))
    assert np.allclose(np.stack([r, g, b], 1), np.eye(3))


def _bulb_pct(img, curve=2.2, method="vibrant"):
    from bulbsync.color import zone_luminance

    hsv = process_ambient(zone_color(img, method), min_brightness=1, max_brightness=100,
                          luminance=zone_luminance(img), curve=curve)
    return hsv[2] / 10


def test_luminance_is_gamma_correct():
    from bulbsync.color import zone_luminance

    assert zone_luminance(np.zeros((4, 4, 3), np.uint8)) == 0
    assert zone_luminance(np.full((4, 4, 3), 255, np.uint8)) == pytest.approx(1.0)
    # szarość 50% na ekranie to tylko ~21% światła
    assert zone_luminance(np.full((4, 4, 3), 128, np.uint8)) == pytest.approx(0.216, abs=0.005)
    # pełny kolor = pełna intensywność, niezależnie od barwy
    assert zone_luminance(np.full((1, 1, 3), (0, 0, 255), np.uint8)) == pytest.approx(1.0)
    assert zone_luminance(np.full((1, 1, 3), (255, 0, 0), np.uint8)) == pytest.approx(1.0)


def test_dark_scenes_dim_the_bulb():
    dark_grey = np.full((20, 20, 3), 50, np.uint8)  # ciemna scena, np. noc w grze
    assert _bulb_pct(dark_grey) < 6  # wcześniej ok. 20%
    dark_blue = np.zeros((20, 20, 3), np.uint8)
    dark_blue[..., 2] = 60
    assert _bulb_pct(dark_blue) < 6  # wcześniej ok. 25%
    blue = np.zeros((20, 20, 3), np.uint8)
    blue[..., 2] = 255
    assert _bulb_pct(blue) == 100  # pełny niebieski = pełna moc
    neon = np.zeros((20, 20, 3), np.uint8)
    neon[:2, :] = (255, 0, 200)  # 10% neonu na czerni
    h, s, _ = rgb_to_tuya_hsv(*zone_color(neon, "vibrant"))
    assert s > 950  # kolor nadal wyrazisty...
    assert _bulb_pct(neon) < 16  # ...ale żarówka przygaszona (wcześniej ok. 20%)
    assert _bulb_pct(np.full((20, 20, 3), 255, np.uint8)) == 100


def test_brightness_curve_is_monotonic():
    img = np.full((10, 10, 3), 90, np.uint8)
    p1, p22, p3 = (_bulb_pct(img, c) for c in (1.0, 2.2, 3.0))
    assert p1 > p22 > p3
