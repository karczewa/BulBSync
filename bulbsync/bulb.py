"""Komunikacja z jedną żarówką w osobnym wątku.

Każda żarówka ma własny wątek i własne, stałe połączenie (tinytuya nie jest bezpieczne
wątkowo). GUI i silnik ambient tylko zostawiają polecenia, a wątek je łączy i wysyła:
- polecenia ręczne są scalane (szybki ruch suwakiem = jedno wysłanie z ostatnią wartością),
- z ambient wysyłany jest zawsze tylko najnowszy kolor, stare klatki przepadają.
"""

from __future__ import annotations

import queue
import threading
import time

import tinytuya

from .color import hsv_close, music_data
from .config import BulbInfo

STATUS_POLL_SECONDS = 30  # odświeżanie stanu, gdy nie działa ambient (np. zmiany z telefonu)
AMBIENT_KEEPALIVE_SECONDS = 2.0  # wysyłaj ponownie nawet bez zmiany koloru
RETRY_DELAY_SECONDS = 2.0  # przerwa przed ponowną próbą po błędzie sieci


class BulbWorker(threading.Thread):
    def __init__(self, info: BulbInfo, events: "queue.Queue"):
        super().__init__(daemon=True, name=f"bulb-{info.name}")
        self.info = info
        self.events = events
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = False
        self._pending: dict = {}
        self._want_status = True
        self._ambient = None  # (h, s, v, gradient)
        self._ambient_started = False
        self._last_ambient_sent = None
        self._last_ambient_time = 0.0
        self._last_mode_time = 0.0
        self.ambient_sends = 0  # licznik do wyświetlania "wysłane/s"
        self._ip_changed = False
        self._dev = None
        self.online = None
        self.dps: dict = {}

    # --- API dla GUI i silnika (dowolny wątek) ---------------------------------

    def send(self, dps: dict) -> None:
        with self._lock:
            self._pending.update({str(k): v for k, v in dps.items()})
        self._wake.set()

    def request_status(self) -> None:
        with self._lock:
            self._want_status = True
        self._wake.set()

    def set_ambient(self, hsv: tuple[int, int, int], gradient: bool) -> None:
        with self._lock:
            self._ambient = (*hsv, gradient)
        self._wake.set()

    def stop_ambient(self) -> None:
        with self._lock:
            self._ambient = None
            self._ambient_started = False
            self._last_ambient_sent = None

    def set_ip(self, ip: str) -> None:
        with self._lock:
            if ip and ip != self.info.ip:
                self.info.ip = ip
                self._ip_changed = True
                self._want_status = True
        self._wake.set()

    def shutdown(self) -> None:
        self._stopping = True
        self._wake.set()

    # --- Wątek -----------------------------------------------------------------

    def _emit(self, online: bool, error: str | None = None) -> None:
        self.online = online
        self.events.put(("state", self.info.id, {"online": online, "dps": dict(self.dps), "error": error}))

    def _device(self):
        if self._dev is None or self._ip_changed:
            self._close()
            self._ip_changed = False
            dev = tinytuya.BulbDevice(
                self.info.id,
                self.info.ip,
                self.info.key,
                version=self.info.version,
                persist=True,
                connection_timeout=2,
                connection_retry_limit=1,
                connection_retry_delay=1,
            )
            dev.set_socketPersistent(True)
            dev.set_socketTimeout(2)
            dev.set_socketRetryLimit(1)
            self._dev = dev
        return self._dev

    def _close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev = None

    @staticmethod
    def _error_of(result) -> str | None:
        if isinstance(result, dict) and ("Error" in result or "Err" in result):
            return f"{result.get('Err', '')} {result.get('Error', '')}".strip()
        return None

    def _apply_result(self, result) -> None:
        if isinstance(result, dict) and isinstance(result.get("dps"), dict):
            self.dps.update(result["dps"])

    def run(self) -> None:
        last_status = 0.0
        while not self._stopping:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            if self._stopping:
                break
            with self._lock:
                pending, self._pending = self._pending, {}
                want_status, self._want_status = self._want_status, False
                ambient = self._ambient
                start_ambient = ambient is not None and not self._ambient_started
                if start_ambient:
                    self._ambient_started = True
            if ambient is None and time.monotonic() - last_status > STATUS_POLL_SECONDS:
                want_status = True
            if not self.info.ip:
                if want_status or pending:
                    self._emit(False, "brak adresu IP - użyj 'Skanuj sieć'")
                continue
            try:
                dev = self._device()
                if pending:
                    result = dev.set_multiple_values(pending)
                    err = self._error_of(result)
                    if err:
                        raise ConnectionError(err)
                    self.dps.update(pending)
                    self._apply_result(result)
                    self._emit(True)
                if want_status:
                    last_status = time.monotonic()
                    result = dev.status()
                    err = self._error_of(result)
                    if err:
                        raise ConnectionError(err)
                    self._apply_result(result)
                    self._emit(True)
                if ambient is not None:
                    self._send_ambient(dev, ambient, start_ambient)
            except Exception as e:  # sieć, timeout, zły klucz...
                self._close()
                if start_ambient:
                    with self._lock:
                        self._ambient_started = False
                if self.online is not False or pending or want_status:
                    self._emit(False, str(e) or e.__class__.__name__)
                # odczekaj chwilę przed kolejną próbą, ale nie gub poleceń
                with self._lock:
                    for k, v in pending.items():
                        self._pending.setdefault(k, v)
                time.sleep(RETRY_DELAY_SECONDS)
                self._wake.set()
        self._close()

    def _send_ambient(self, dev, ambient, start: bool) -> None:
        h, s, v, gradient = ambient
        hsv = (h, s, v)
        now = time.monotonic()
        if (
            not start
            and hsv_close(hsv, self._last_ambient_sent)
            and now - self._last_ambient_time < AMBIENT_KEEPALIVE_SECONDS
        ):
            return
        dps = {"27": music_data(h, s, v, gradient)}
        if start or now - self._last_mode_time >= AMBIENT_KEEPALIVE_SECONDS:
            # tryb "music" wystarczy przypominać co jakiś czas, a nie w każdej klatce
            dps["21"] = "music"
            self._last_mode_time = now
        if start:
            dps["20"] = True
            # pierwsze wysłanie z potwierdzeniem, żeby wykryć brak połączenia
            result = dev.set_multiple_values(dps)
            err = self._error_of(result)
            if err:
                raise ConnectionError(err)
            if self.online is not True:
                self._emit(True)
        else:
            self._drain(dev)
            dev.set_multiple_values(dps, nowait=True)
        self.ambient_sends += 1
        self._last_ambient_sent = hsv
        self._last_ambient_time = now

    @staticmethod
    def _drain(dev) -> None:
        """Odczytaj zaległe odpowiedzi żarówki bez czekania.

        Przy wysyłaniu bez czekania (nowait) żarówka i tak odpowiada na każdą wiadomość.
        Nieodczytane odpowiedzi zapychają bufor połączenia, a wtedy żarówka zaczyna się
        zacinać albo przestaje odpowiadać.
        """
        sock = getattr(dev, "socket", None)
        if sock is None:
            return
        timeout = sock.gettimeout()
        try:
            sock.setblocking(False)
            for _ in range(64):
                if not sock.recv(65536):
                    break
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            pass  # zerwane połączenie wyjdzie przy następnym wysłaniu i zostanie odnowione
        finally:
            try:
                sock.settimeout(timeout)
            except OSError:
                pass
