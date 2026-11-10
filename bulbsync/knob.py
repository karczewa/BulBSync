"""Pokrętło USB (Raspberry Pi Pico + enkoder KY-040): połączenie przez port szeregowy i logika sterowania.

Płytka wysyła linie tekstu (patrz firmware/bulbsync_knob/bulbsync_knob.ino):
"+"/"-" obrót, "P+"/"P-" obrót przy wciśniętej gałce, "CLICK", "HOLD", "BULBSYNC-KNOB 1".
"""

from __future__ import annotations

import queue
import threading
import time

from .color import colour_data_v2, parse_colour_data_v2

HELLO = "BULBSYNC-KNOB"
RPI_VID = 0x2E8A  # Raspberry Pi (Pico) - tylko takie porty sprawdzamy automatycznie
BAUD = 115200
PROBE_SECONDS = 2.5
SILENCE_TIMEOUT = 5.0  # płytka przedstawia się co sekundę; dłuższa cisza = rozłączona


def parse_line(line: str):
    """Linia z płytki -> zdarzenie albo None.

    ("rotate", +1/-1, wciśnięta?) | ("click",) | ("hold",) | ("hello", wersja)
    """
    s = line.strip()
    if s in ("+", "-"):
        return ("rotate", 1 if s == "+" else -1, False)
    if s in ("P+", "P-"):
        return ("rotate", 1 if s == "P+" else -1, True)
    if s == "CLICK":
        return ("click",)
    if s == "HOLD":
        return ("hold",)
    if s.startswith(HELLO):
        parts = s.split()
        return ("hello", parts[1] if len(parts) > 1 else "")
    return None


# =============================================================================
# Połączenie z płytką
# =============================================================================
def _list_ports():
    from serial.tools import list_ports

    return [(p.device, p.vid) for p in list_ports.comports()]


def _open_port(device: str):
    import serial

    return serial.Serial(device, BAUD, timeout=0.2, write_timeout=0.5)


class KnobLink(threading.Thread):
    """Wyszukuje pokrętło, utrzymuje połączenie i wrzuca zdarzenia do kolejki GUI.

    Zdarzenia: ("knob_status", nazwa_portu | None | "brak pyserial"), ("knob", zdarzenie z parse_line).
    """

    def __init__(self, events: "queue.Queue", port: str = "", lister=None, opener=None, retry_delay: float = 2.0):
        super().__init__(daemon=True, name="knob")
        self.events = events
        self.port = port.strip()
        self._lister = lister or _list_ports
        self._opener = opener or _open_port
        self.retry_delay = retry_delay
        self._stopping = threading.Event()
        self.connected: str | None = None

    def stop(self):
        self._stopping.set()

    def _candidates(self) -> list[str]:
        if self.port:
            return [self.port]
        return [dev for dev, vid in self._lister() if vid == RPI_VID]

    def _probe(self, device: str):
        """Otwiera port i czeka, aż płytka się przedstawi. Zwraca otwarty port albo None."""
        try:
            ser = self._opener(device)
        except Exception:
            return None
        try:
            ser.write(b"?\n")
            end = time.monotonic() + PROBE_SECONDS
            while time.monotonic() < end and not self._stopping.is_set():
                ev = parse_line(ser.readline().decode("ascii", "ignore"))
                if ev and ev[0] == "hello":
                    return ser
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass
        return None

    def run(self):
        import importlib.util

        if self._lister is _list_ports and importlib.util.find_spec("serial") is None:
            self.events.put(("knob_status", "brak pyserial"))
            return
        while not self._stopping.is_set():
            ser = None
            try:
                for dev in self._candidates():
                    ser = self._probe(dev)
                    if ser:
                        self.connected = dev
                        break
            except Exception:
                ser = None
            if ser is None:
                self._stopping.wait(self.retry_delay)
                continue
            self.events.put(("knob_status", self.connected))
            self._session(ser)
            self.connected = None
            self.events.put(("knob_status", None))
            self._stopping.wait(self.retry_delay / 2)

    def _session(self, ser):
        last = time.monotonic()
        try:
            while not self._stopping.is_set():
                raw = ser.readline()
                now = time.monotonic()
                if raw:
                    last = now
                    ev = parse_line(raw.decode("ascii", "ignore"))
                    if ev and ev[0] != "hello":
                        self.events.put(("knob", ev))
                elif now - last > SILENCE_TIMEOUT:
                    break
        except Exception:
            pass  # odłączony kabel itp. - wracamy do wyszukiwania
        finally:
            try:
                ser.close()
            except Exception:
                pass


# =============================================================================
# Logika: co robi obrót / kliknięcie
# =============================================================================
STATE_TTL = 2.0  # przez tyle sekund po ostatnim ruchu liczymy od własnego stanu, nie od (opóźnionego) stanu żarówki


class KnobController:
    """Zamienia ruchy pokrętła na polecenia dla żarówek (słowniki DP Tuya).

    Trzyma własną kopię stanu z ostatnich chwil: przy szybkim kręceniu żarówka jeszcze nie
    potwierdziła poprzedniej zmiany, a liczenie od jej starego stanu gubiłoby kroki.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def _state(self, bid: str, dps: dict, now: float) -> dict:
        c = self._cache.get(bid)
        if c and now - c["t"] < STATE_TTL:
            return c
        hsv = parse_colour_data_v2(dps.get("24", "")) or (0, 1000, 1000)
        mode = dps.get("21")
        if mode not in ("white", "colour"):
            mode = "colour" if dps.get("24") else "white"
        st = {
            "on": bool(dps.get("20", True)),
            "mode": mode,
            "bright": int(dps.get("22", 1000)) if isinstance(dps.get("22"), int) else 1000,
            "temp": int(dps.get("23", 500)) if isinstance(dps.get("23"), int) else 500,
            "h": hsv[0], "s": hsv[1], "v": hsv[2],
            "t": now,
        }
        self._cache[bid] = st
        return st

    @staticmethod
    def level(st: dict) -> int:
        """Jasność 10-1000 niezależnie od trybu."""
        return st["bright"] if st["mode"] == "white" else st["v"]

    def rotate(self, states: dict[str, dict], steps: int, step_pct: float, now: float | None = None):
        """Obrót: zmiana jasności. Zwraca ({bid: dps}, średnia jasność w % albo None)."""
        now = time.monotonic() if now is None else now
        out, levels = {}, []
        for bid, dps in states.items():
            st = self._state(bid, dps, now)
            st["t"] = now
            if not st["on"]:
                if steps > 0:  # kręcenie w górę włącza wyłączone światło
                    st["on"] = True
                    out[bid] = {"20": True}
                    levels.append(self.level(st))
                continue
            new = max(10, min(1000, self.level(st) + round(steps * step_pct * 10)))
            if st["mode"] == "white":
                st["bright"] = new
                out[bid] = {"22": new}
            else:
                st["v"] = new
                out[bid] = {"24": colour_data_v2(st["h"], st["s"], new)}
            levels.append(new)
        avg = round(sum(levels) / len(levels) / 10) if levels else None
        return out, avg

    def shift(self, states: dict[str, dict], steps: int, now: float | None = None):
        """Obrót z wciśniętą gałką: kolor -> odcień, biały -> barwa (ciepła/zimna).

        Zwraca ({bid: dps}, opis do wyświetlenia albo None).
        """
        now = time.monotonic() if now is None else now
        out, label = {}, None
        for bid, dps in states.items():
            st = self._state(bid, dps, now)
            st["t"] = now
            if not st["on"]:
                continue
            if st["mode"] == "white":
                st["temp"] = max(0, min(1000, st["temp"] + steps * 50))
                out[bid] = {"23": st["temp"]}
                label = f"Barwa {round(st['temp'] / 10)}% (ciepła → zimna)"
            else:
                st["h"] = (st["h"] + steps * 12) % 360
                out[bid] = {"24": colour_data_v2(st["h"], st["s"], st["v"])}
                label = f"Odcień {st['h']}°"
        return out, label

    def toggle(self, states: dict[str, dict], now: float | None = None):
        """Kliknięcie: jeśli coś świeci - wyłącz wszystko, inaczej włącz. Zwraca ({bid: dps}, czy włączono)."""
        now = time.monotonic() if now is None else now
        sts = {bid: self._state(bid, dps, now) for bid, dps in states.items()}
        turn_on = not any(st["on"] for st in sts.values())
        for st in sts.values():
            st["on"] = turn_on
            st["t"] = now
        return {bid: {"20": turn_on} for bid in sts}, turn_on

    def forget(self, bid: str | None = None):
        """Zapomnij własny stan (np. gdy żarówką sterowano z aplikacji lub telefonu)."""
        if bid is None:
            self._cache.clear()
        else:
            self._cache.pop(bid, None)
