import queue
import time

import pytest

from bulbsync import knob
from bulbsync.color import colour_data_v2, parse_colour_data_v2
from bulbsync.knob import KnobController, KnobLink, parse_line


def test_parse_line():
    assert parse_line("+\r\n") == ("rotate", 1, False)
    assert parse_line("-") == ("rotate", -1, False)
    assert parse_line("P+") == ("rotate", 1, True)
    assert parse_line("P-\n") == ("rotate", -1, True)
    assert parse_line("CLICK") == ("click",)
    assert parse_line("HOLD") == ("hold",)
    assert parse_line("BULBSYNC-KNOB 1") == ("hello", "1")
    assert parse_line("") is None
    assert parse_line("śmieci") is None


WHITE = {"20": True, "21": "white", "22": 500, "23": 300}
COLOUR = {"20": True, "21": "colour", "24": colour_data_v2(120, 1000, 500)}
OFF = {"20": False, "21": "white", "22": 800}


def test_rotate_white_and_colour():
    c = KnobController()
    out, avg = c.rotate({"a": WHITE, "b": COLOUR}, +1, 5, now=0)
    assert out["a"] == {"22": 550}
    assert parse_colour_data_v2(out["b"]["24"]) == (120, 1000, 550)
    assert avg == 55


def test_fast_turns_do_not_lose_steps():
    """Żarówka jeszcze nie potwierdziła zmiany, a kolejne ząbki już przychodzą."""
    c = KnobController()
    for i in range(4):
        out, _ = c.rotate({"a": WHITE}, +1, 5, now=0.05 * i)  # cały czas ten sam, stary stan żarówki
    assert out["a"] == {"22": 700}


def test_cache_expires_and_rereads_bulb():
    c = KnobController()
    c.rotate({"a": WHITE}, +1, 5, now=0)
    out, _ = c.rotate({"a": {**WHITE, "22": 200}}, +1, 5, now=10)  # zmieniono z telefonu
    assert out["a"] == {"22": 250}


def test_rotate_clamps_and_turns_on():
    c = KnobController()
    out, _ = c.rotate({"a": {**WHITE, "22": 990}}, +3, 5, now=0)
    assert out["a"] == {"22": 1000}
    out, _ = c.rotate({"b": {**WHITE, "22": 30}}, -5, 5, now=0)
    assert out["b"] == {"22": 10}
    out, _ = c.rotate({"c": OFF}, -1, 5, now=0)
    assert out == {}  # kręcenie w dół nie włącza
    out, avg = c.rotate({"c": OFF}, +1, 5, now=0.1)
    assert out["c"] == {"20": True} and avg == 80  # włącza z poprzednią jasnością


def test_shift_hue_and_temperature():
    c = KnobController()
    out, label = c.shift({"a": {**COLOUR, "24": colour_data_v2(354, 1000, 500)}}, +1, now=0)
    assert parse_colour_data_v2(out["a"]["24"])[0] == 6  # zawija się przez 360
    out, label = c.shift({"b": WHITE}, -2, now=0)
    assert out["b"] == {"23": 200} and "Barwa" in label


def test_toggle():
    c = KnobController()
    out, on = c.toggle({"a": WHITE, "b": OFF}, now=0)
    assert on is False and out == {"a": {"20": False}, "b": {"20": False}}
    out, on = c.toggle({"a": WHITE, "b": OFF}, now=0.2)  # pamięta, że właśnie wyłączył
    assert on is True and out["a"] == {"20": True}


class FakeSerial:
    def __init__(self, lines, fail_after=None):
        self.lines = list(lines)
        self.written = b""
        self.closed = False
        self.fail_after = fail_after

    def write(self, data):
        self.written += data

    def readline(self):
        if self.fail_after is not None and not self.lines:
            raise OSError("odłączono")
        if self.lines:
            return (self.lines.pop(0) + "\r\n").encode()
        time.sleep(0.01)
        return b""

    def close(self):
        self.closed = True


def collect(events, n, timeout=3.0):
    out = []
    end = time.monotonic() + timeout
    while len(out) < n and time.monotonic() < end:
        try:
            out.append(events.get(timeout=0.05))
        except queue.Empty:
            pass
    return out


def test_link_finds_knob_and_forwards_events():
    events = queue.Queue()
    other = FakeSerial(["jakieś inne urządzenie"])
    knob_port = FakeSerial(["BULBSYNC-KNOB 1", "+", "P-", "CLICK", "BULBSYNC-KNOB 1", "HOLD"], fail_after=True)
    ports = {"COM3": other, "COM7": knob_port}
    link = KnobLink(events, lister=lambda: [("COM1", 0x1234), ("COM3", knob.RPI_VID), ("COM7", knob.RPI_VID)],
                    opener=lambda dev: ports[dev], retry_delay=0.05)
    knob.PROBE_SECONDS, old = 0.2, knob.PROBE_SECONDS
    try:
        link.start()
        got = collect(events, 6)
    finally:
        link.stop()
        link.join(timeout=2)
        knob.PROBE_SECONDS = old
    assert got[0] == ("knob_status", "COM7")
    assert got[1:5] == [("knob", ("rotate", 1, False)), ("knob", ("rotate", -1, True)),
                        ("knob", ("click",)), ("knob", ("hold",))]
    assert got[5] == ("knob_status", None)  # odłączenie wykryte
    assert other.closed and knob_port.closed
    assert knob_port.written.startswith(b"?")


def test_link_respects_manual_port():
    events = queue.Queue()
    opened = []

    def opener(dev):
        opened.append(dev)
        raise OSError("brak")

    link = KnobLink(events, port="COM9", lister=lambda: [("COM3", knob.RPI_VID)], opener=opener, retry_delay=0.02)
    link.start()
    time.sleep(0.1)
    link.stop()
    link.join(timeout=2)
    assert opened and set(opened) == {"COM9"}


@pytest.mark.parametrize("line", ["+", "-", "P+", "P-", "CLICK", "HOLD"])
def test_firmware_messages_match_parser(line):
    """Komunikaty w programie płytki muszą być rozumiane przez aplikację."""
    import pathlib

    src = (pathlib.Path(__file__).parents[1] / "firmware" / "bulbsync_knob" / "bulbsync_knob.ino").read_text()
    assert f'"{line}"' in src
    assert parse_line(line) is not None
    assert '"BULBSYNC-KNOB 1"' in src
