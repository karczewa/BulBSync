"""Testy wątku żarówki na atrapie tinytuya (bez sieci)."""

import queue
import threading
import time

import pytest

from bulbsync import bulb as bulb_mod
from bulbsync.config import BulbInfo


class FakeDevice:
    instances = []
    fail_next = 0

    def __init__(self, dev_id, address, key, **kw):
        self.calls = []
        self.lock = threading.Lock()
        self.state = {"20": True, "21": "white", "22": 500, "23": 0}
        self.version = kw.get("version")
        FakeDevice.instances.append(self)

    def set_socketPersistent(self, v): ...
    def set_socketTimeout(self, v): ...
    def set_socketRetryLimit(self, v): ...
    def close(self): ...

    def _maybe_fail(self):
        if FakeDevice.fail_next:
            FakeDevice.fail_next -= 1
            return {"Error": "Network Error: Device Unreachable", "Err": "905"}
        return None

    def status(self):
        err = self._maybe_fail()
        if err:
            return err
        with self.lock:
            self.calls.append(("status",))
        return {"dps": dict(self.state)}

    def set_multiple_values(self, dps, nowait=False):
        err = self._maybe_fail()
        if err:
            return err
        with self.lock:
            self.calls.append(("set", dict(dps), nowait))
            self.state.update(dps)
        time.sleep(0.05)  # udajemy opóźnienie sieci
        return None if nowait else {"dps": dict(dps)}


@pytest.fixture
def worker(monkeypatch):
    FakeDevice.instances = []
    FakeDevice.fail_next = 0
    monkeypatch.setattr(bulb_mod.tinytuya, "BulbDevice", FakeDevice)
    monkeypatch.setattr(bulb_mod, "RETRY_DELAY_SECONDS", 0.05)
    events = queue.Queue()
    w = bulb_mod.BulbWorker(BulbInfo("id1", "Test", "key", "192.168.1.5", 3.5), events)
    w.start()
    yield w, events
    w.shutdown()
    w.join(timeout=2)


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_initial_status_and_version(worker):
    w, events = worker
    assert wait_for(lambda: w.online is True)
    assert FakeDevice.instances[0].version == 3.5
    kind, bid, st = events.get(timeout=1)
    assert (kind, bid, st["online"], st["dps"]["21"]) == ("state", "id1", True, "white")


def test_rapid_slider_moves_are_coalesced(worker):
    w, _ = worker
    assert wait_for(lambda: w.online is True)
    dev = FakeDevice.instances[0]
    for b in range(100, 1000, 10):  # 90 szybkich ruchów suwakiem
        w.send({"22": b})
    assert wait_for(lambda: dev.state.get("22") == 990)
    sets = [c for c in dev.calls if c[0] == "set"]
    assert len(sets) < 10  # scalone, a nie 90 osobnych wysłań
    assert wait_for(lambda: w.dps.get("22") == 990)


def test_recovers_after_network_error(worker):
    w, events = worker
    assert wait_for(lambda: w.online is True)
    FakeDevice.fail_next = 1
    w.send({"20": False})
    assert wait_for(lambda: w.online is False)
    # polecenie nie przepadło - zostało wysłane po ponownym połączeniu
    assert wait_for(lambda: w.online is True and FakeDevice.instances[-1].state.get("20") is False)


def test_ambient_sends_music_dp_latest_only(worker):
    w, _ = worker
    assert wait_for(lambda: w.online is True)
    for i in range(20):
        w.set_ambient((i * 10, 1000, 500), False)
    dev = FakeDevice.instances[-1]
    assert wait_for(lambda: any(c[0] == "set" and "27" in c[1] for c in dev.calls))
    time.sleep(0.3)
    amb = [c for c in dev.calls if c[0] == "set" and "27" in c[1]]
    assert amb[0][1]["20"] is True and amb[0][1]["21"] == "music" and amb[0][2] is False
    assert all(c[2] is True for c in amb[1:])  # kolejne bez czekania na odpowiedź
    assert len(amb) < 20  # stare klatki pominięte
    assert amb[-1][1]["27"][1:5] == "00be"  # ostatni kolor (H=190) dotarł
    w.stop_ambient()
    n = len(amb)
    time.sleep(0.3)
    assert len([c for c in dev.calls if c[0] == "set" and "27" in c[1]]) == n


def test_drain_reads_pending_replies_without_blocking():
    import socket

    a, b = socket.socketpair()
    a.settimeout(2.0)
    b.sendall(b"x" * 200_000)  # zaległe odpowiedzi żarówki

    class Dev:
        socket = a

    t0 = time.monotonic()
    bulb_mod.BulbWorker._drain(Dev)
    assert time.monotonic() - t0 < 0.5
    assert a.gettimeout() == 2.0  # przywrócony timeout
    a.setblocking(False)
    with pytest.raises(BlockingIOError):
        a.recv(1)  # wszystko przeczytane
    a.close()
    b.close()
