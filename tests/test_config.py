import json

from bulbsync.config import bulb_settings, load_devices, load_settings, save_settings


def test_load_devices_from_wizard_format(tmp_path):
    p = tmp_path / "devices.json"
    p.write_text(
        json.dumps(
            [
                {"name": "B", "id": "id2", "key": "k2", "ip": "192.168.1.2", "version": "3.5", "mapping": {}},
                {"name": "A", "id": "id1", "key": "k1", "ip": "", "version": ""},
                {"name": "bez klucza", "id": "id3", "key": ""},
            ]
        ),
        encoding="utf-8",
    )
    bulbs = load_devices(str(p))
    assert [b.name for b in bulbs] == ["A", "B"]
    assert bulbs[1].version == 3.5 and bulbs[1].ip == "192.168.1.2"
    assert bulbs[0].version == 3.3


def test_settings_roundtrip_and_defaults(tmp_path):
    p = str(tmp_path / "settings.json")
    s = load_settings(p)
    assert s["ambient"]["fps"] == 10
    s["ambient"]["fps"] = 15
    per = bulb_settings(s, "x", 1)
    assert per == {"zone": "center", "ambient": True}
    save_settings(s, p)
    s2 = load_settings(p)
    assert s2["ambient"]["fps"] == 15
    assert s2["ambient"]["saturation"] == 1.5  # brakujące klucze uzupełnione domyślnymi
    assert s2["bulbs"]["x"]["zone"] == "center"
