"""Wczytywanie żarówek z devices.json (z tinytuya wizard) i ustawień aplikacji z settings.json."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass

# Pliki trzymamy w folderze projektu (obok run.bat), a nie w folderze, z którego uruchomiono terminal.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICES_PATH = os.path.join(BASE_DIR, "devices.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")


@dataclass
class BulbInfo:
    id: str
    name: str
    key: str
    ip: str
    version: float


DEFAULT_SETTINGS = {
    "ip_overrides": {},  # id -> ip, uzupełniane przez "Skanuj sieć"
    "bulbs": {},  # id -> {"zone": ..., "ambient": bool}
    "ambient": {
        "fps": 10,
        "monitor": 1,
        "method": "vibrant",
        "saturation": 1.5,
        "brightness_curve": 2.2,
        "smoothing": 0.5,
        "min_brightness": 5,
        "max_brightness": 100,
        "black_threshold": 4,
        "edge_depth": 25,
        "gradient": False,
    },
    "window": {"geometry": ""},
}

DEFAULT_ZONES = ["left", "center", "right", "top", "bottom", "full"]


def load_devices(path: str = DEVICES_PATH) -> list[BulbInfo]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    bulbs = []
    for d in data:
        if not d.get("id") or not d.get("key"):
            continue
        try:
            version = float(d.get("version") or 3.3)
        except ValueError:
            version = 3.3
        bulbs.append(
            BulbInfo(
                id=d["id"],
                name=d.get("name") or d["id"],
                key=d["key"],
                ip=d.get("ip") or "",
                version=version,
            )
        )
    bulbs.sort(key=lambda b: b.name.lower())
    return bulbs


def _merge(defaults: dict, loaded: dict) -> dict:
    out = copy.deepcopy(defaults)
    for k, v in loaded.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(path: str = SETTINGS_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULT_SETTINGS, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: dict, path: str = SETTINGS_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def bulb_settings(settings: dict, bulb_id: str, index: int) -> dict:
    """Ustawienia ambient dla żarówki; tworzy domyślne przy pierwszym użyciu."""
    per = settings["bulbs"].setdefault(bulb_id, {})
    per.setdefault("zone", DEFAULT_ZONES[index % len(DEFAULT_ZONES)])
    per.setdefault("ambient", True)
    return per
