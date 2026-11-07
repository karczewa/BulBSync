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
