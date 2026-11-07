"""Okno aplikacji (customtkinter, ciemny motyw): Sterowanie i Ambient."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import __version__, theme
from .ambient import MAX_FPS, AmbientEngine, list_monitors
from .bulb import BulbWorker
from .color import ZONES, colour_data_v2, parse_colour_data_v2, rgb_to_tuya_hsv, tuya_hsv_to_rgb
from .config import DEVICES_PATH, bulb_settings, load_devices, load_settings, save_settings
from .theme import hex_of, white_rgb
from .widgets import ColorWheel, GradientSlider, ScreenPreview

QUICK_COLOURS = ["#ff2a2a", "#ff7a00", "#ffd200", "#3dff4a", "#00e5c8", "#2a6bff", "#8a2aff", "#ff2ab4"]
WHITE_PRESETS = [("Ciepłe", 100, 0), ("Neutralne", 100, 500), ("Zimne", 100, 1000), ("Nocne", 8, 0)]
ZONE_KEYS = list(ZONES.keys())
ZONE_NAMES = list(ZONES.values())
METHODS = {"vibrant": "Wyraziste kolory", "average": "Średnia z ekranu"}
ALL = "__all__"
USER_EDIT_GRACE = 3.0  # przez tyle sekund po ruchu nie nadpisujemy kontrolek stanem z żarówki


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=theme.FONT, size=size, weight=weight)


def label(master, text, size=13, weight="normal", color=theme.TEXT, **kw):
    return ctk.CTkLabel(master, text=text, font=font(size, weight), text_color=color, **kw)


def card(master, **kw):
    kw.setdefault("fg_color", theme.SURFACE)
    kw.setdefault("corner_radius", 16)
    return ctk.CTkFrame(master, **kw)


def dps_color(dps: dict) -> str | None:
    """Kolor, którym aktualnie świeci żarówka (do kropki na karcie)."""
    if not dps or dps.get("20") is False:
        return theme.OFF_DOT
    mode = dps.get("21")
    if mode == "colour":
        hsv = parse_colour_data_v2(dps.get("24", ""))
        if hsv:
            return hex_of(tuya_hsv_to_rgb(hsv[0], hsv[1], 1000))
    if mode == "white":
        return hex_of(white_rgb(dps.get("23", 500)))
    return None


# =============================================================================
# Karta żarówki (wybór celu sterowania + szybkie włącz/wyłącz)
# =============================================================================
class BulbTile(ctk.CTkFrame):
    def __init__(self, master, app: "App", target: str, name: str, subtitle: str):
        super().__init__(master, fg_color=theme.SURFACE, corner_radius=14, border_width=2,
                         border_color=theme.SURFACE, cursor="hand2")
        self.app, self.target = app, target
        self.grid_columnconfigure(1, weight=1)
        self.dot = ctk.CTkFrame(self, width=16, height=16, corner_radius=8, fg_color=theme.OFF_DOT)
        self.dot.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=14)
        self.name = label(self, name, 14, "bold", anchor="w")
        self.name.grid(row=0, column=1, sticky="sw", pady=(12, 0))
        self.status = label(self, subtitle, 12, color=theme.MUTED, anchor="w")
        self.status.grid(row=1, column=1, sticky="nw", pady=(0, 12))
        self.power = ctk.CTkSwitch(self, text="", width=46, progress_color=theme.ACCENT,
                                   button_color=theme.TEXT, fg_color=theme.SURFACE_3,
                                   command=lambda: app.power(target, bool(self.power.get())))
        self.power.grid(row=0, column=2, rowspan=2, padx=(6, 8))
        for w in (self, self.name, self.status, self.dot):
            w.bind("<Button-1>", lambda e: app.control.select(target))

    def set_selected(self, sel: bool):
        self.configure(border_color=theme.ACCENT if sel else theme.SURFACE)

    def show(self, online, error, dps, in_ambient, ambient_color=None):
        if in_ambient:
            self.status.configure(text="ambient", text_color=theme.AMBIENT)
            if ambient_color:
                self.dot.configure(fg_color=ambient_color)
        elif online:
            on = dps.get("20")
            self.status.configure(text="włączona" if on else "wyłączona" if on is False else "połączona",
                                  text_color=theme.OK if on else theme.MUTED)
        elif online is False:
            self.status.configure(text="brak połączenia", text_color=theme.ERR)
            self.dot.configure(fg_color=theme.OFF_DOT)
        if not in_ambient and online:
            col = dps_color(dps)
            if col:
                self.dot.configure(fg_color=col)
            if isinstance(dps.get("20"), bool):
                self.power.select() if dps["20"] else self.power.deselect()


# =============================================================================
# Strona: Sterowanie
# =============================================================================
class ControlPage(ctk.CTkFrame):
    def __init__(self, master, app: "App", scale: float):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.target = ALL
        self._syncing = False
        self._last_edit = 0.0
        self.h, self.s, self.v = 0, 1000, 1000  # kolor
        self.wb, self.wt = 1000, 300  # biały: jasność, barwa
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        label(head, "Sterowanie", 26, "bold").pack(side="left")
        label(head, "  kliknij kartę, żeby wybrać żarówkę", 13, color=theme.MUTED).pack(side="left", pady=(8, 0))

        # --- karty żarówek
        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.tiles: dict[str, BulbTile] = {}
        items = [(ALL, "Wszystkie", f"{len(app.bulbs)} żarówki")] + [(b.id, b.name, b.ip or "brak IP") for b in app.bulbs]
        cols = min(4, len(items))
        for i, (tid, name, sub) in enumerate(items):
            t = BulbTile(tiles, app, tid, name, sub)
            t.grid(row=i // cols, column=i % cols, sticky="ew", padx=(0 if i % cols == 0 else 10, 0), pady=(0, 10))
            self.tiles[tid] = t
        for c in range(cols):
            tiles.grid_columnconfigure(c, weight=1, uniform="tiles")
        self.tiles[ALL].dot.configure(fg_color=theme.ACCENT)

        # --- panel sterowania
        panel = card(self)
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        ph = ctk.CTkFrame(panel, fg_color="transparent")
        ph.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        self.title = label(ph, "Wszystkie żarówki", 18, "bold")
        self.title.pack(side="left")
        self.mode = ctk.CTkSegmentedButton(
            ph, values=["Kolor", "Biały"], command=self._mode_clicked, font=font(13, "bold"),
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.SURFACE_2, unselected_hover_color=theme.SURFACE_3, fg_color=theme.SURFACE_2,
            height=34, width=200,
        )
        self.mode.set("Kolor")
        self.mode.pack(side="right")

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(6, 22))
        panel.grid_rowconfigure(1, weight=1)
        sw = int(320 * scale)  # szerokość suwaków w pikselach

        # kolor
        self.colour_view = ctk.CTkFrame(body, fg_color="transparent")
        self.wheel = ColorWheel(self.colour_view, int(300 * scale), command=self._wheel_moved)
        self.wheel.grid(row=0, column=0, rowspan=6, padx=(0, 32), pady=4)
        right = ctk.CTkFrame(self.colour_view, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nw", pady=(10, 0))
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x")
        self.swatch = ctk.CTkFrame(row, width=44, height=44, corner_radius=12, fg_color="#ff0000")
        self.swatch.pack(side="left")
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", padx=12)
        label(txt, "Aktualny kolor", 12, color=theme.MUTED).pack(anchor="w")
        self.hex_lbl = label(txt, "#FF0000", 15, "bold")
        self.hex_lbl.pack(anchor="w")

        self.c_bright_lbl = self._slider_label(right, "Jasność", pady=(22, 2))
        self.c_bright = GradientSlider(right, sw, 10, 1000, 1000, [(20, 20, 20), (255, 0, 0)],
                                       command=self._colour_bright_moved)
        self.c_bright.pack(anchor="w")

        label(right, "Szybkie kolory", 13, color=theme.MUTED).pack(anchor="w", pady=(20, 6))
        qrow = ctk.CTkFrame(right, fg_color="transparent")
        qrow.pack(anchor="w")
        for hx in QUICK_COLOURS:
            ctk.CTkButton(qrow, text="", width=32, height=32, corner_radius=16, fg_color=hx, hover_color=hx,
                          border_width=2, border_color=theme.SURFACE_2,
                          command=lambda hx=hx: self._quick(hx)).pack(side="left", padx=(0, 8))

        # biały
        self.white_view = ctk.CTkFrame(body, fg_color="transparent")
        self.w_temp_lbl = self._slider_label(self.white_view, "Barwa światła", pady=(10, 2))
        self.w_temp = GradientSlider(self.white_view, int(460 * scale), 0, 1000, 300,
                                     [theme.WARM_WHITE, theme.NEUTRAL_WHITE, theme.COLD_WHITE],
                                     command=self._white_moved)
        self.w_temp.pack(anchor="w")
        self.w_bright_lbl = self._slider_label(self.white_view, "Jasność", pady=(22, 2))
        self.w_bright = GradientSlider(self.white_view, int(460 * scale), 10, 1000, 1000,
                                       [(20, 20, 20), white_rgb(300)], command=self._white_moved)
        self.w_bright.pack(anchor="w")
        label(self.white_view, "Presety", 13, color=theme.MUTED).pack(anchor="w", pady=(24, 6))
        prow = ctk.CTkFrame(self.white_view, fg_color="transparent")
        prow.pack(anchor="w")
        for name, b, t in WHITE_PRESETS:
            ctk.CTkButton(prow, text=name, width=96, height=34, corner_radius=10, font=font(13),
                          fg_color=theme.SURFACE_2, hover_color=theme.SURFACE_3, text_color=theme.TEXT,
                          command=lambda b=b, t=t: self._white_preset(b, t)).pack(side="left", padx=(0, 8))

        self._show_mode("colour")
        self._refresh_labels()
        self.select(ALL)

    def _slider_label(self, master, text, pady):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=pady)
        label(row, text, 13, color=theme.MUTED).pack(side="left")
        val = label(row, "", 13, "bold")
        val.pack(side="right")
        return val

    # --- wybór celu
    def select(self, target: str):
        self.target = target
        for tid, t in self.tiles.items():
            t.set_selected(tid == target)
        if target == ALL:
            self.title.configure(text="Wszystkie żarówki")
        else:
            b = self.app.bulb_by_id[target]
            self.title.configure(text=b.name)
            self.sync_from(self.app.workers[target].dps, force=True)

    def targets(self) -> list[str]:
        return [b.id for b in self.app.bulbs] if self.target == ALL else [self.target]

    # --- tryb
    def _show_mode(self, mode):
        if mode == "white":
            self.colour_view.pack_forget()
            self.white_view.pack(anchor="nw", fill="x")
            self.mode.set("Biały")
        else:
            self.white_view.pack_forget()
            self.colour_view.pack(anchor="nw", fill="x")
            self.mode.set("Kolor")

    def _mode_clicked(self, value):
        if value == "Biały":
            self._show_mode("white")
            self._send_white()
        else:
            self._show_mode("colour")
            self._send_colour()

    # --- zmiany użytkownika
    def _wheel_moved(self, h, s):
        self.h, self.s = h, s
        self._send_colour()

    def _colour_bright_moved(self, v):
        self.v = int(v)
        self._send_colour()

    def _quick(self, hx):
        h, s, _ = rgb_to_tuya_hsv(*(int(hx[i: i + 2], 16) for i in (1, 3, 5)))
        self.h, self.s = h, s
        self.wheel.set(h, s)
        self._send_colour()

    def _white_moved(self, _v):
        self.wt, self.wb = int(self.w_temp.get()), int(self.w_bright.get())
        self._send_white()

    def _white_preset(self, b, t):
        self.wb, self.wt = max(10, b * 10), t
        self.w_bright.set(self.wb)
        self.w_temp.set(self.wt)
        self._send_white()

    def _send_colour(self):
        self._refresh_labels()
        self._send({"20": True, "21": "colour", "24": colour_data_v2(self.h, self.s, max(10, self.v))})

    def _send_white(self):
        self._refresh_labels()
        self._send({"20": True, "21": "white", "22": max(10, self.wb), "23": self.wt})

    def _send(self, dps):
        if not self._syncing and self.app.send(self.targets(), dps):
            self._last_edit = time.monotonic()

    def _refresh_labels(self):
        full = tuya_hsv_to_rgb(self.h, self.s, 1000)
        hx = hex_of(full)
        self.swatch.configure(fg_color=hex_of(tuya_hsv_to_rgb(self.h, self.s, max(250, self.v))))
        self.hex_lbl.configure(text=hx.upper())
        self.c_bright.set_stops([(20, 20, 20), full])
        self.c_bright_lbl.configure(text=f"{round(self.v / 10)}%")
        self.w_bright.set_stops([(20, 20, 20), white_rgb(self.wt)])
        self.w_bright_lbl.configure(text=f"{round(self.wb / 10)}%")
        self.w_temp_lbl.configure(
            text="ciepła" if self.wt < 330 else "neutralna" if self.wt < 670 else "zimna"
        )

    # --- stan z żarówki
    def sync_from(self, dps: dict, force=False):
        if not dps or (not force and time.monotonic() - self._last_edit < USER_EDIT_GRACE):
            return
        self._syncing = True
        try:
            if isinstance(dps.get("22"), int):
                self.wb = dps["22"]
                self.w_bright.set(self.wb)
            if isinstance(dps.get("23"), int):
                self.wt = dps["23"]
                self.w_temp.set(self.wt)
            hsv = parse_colour_data_v2(dps.get("24", ""))
            if hsv:
                self.h, self.s, self.v = hsv
                self.wheel.set(self.h, self.s)
                self.c_bright.set(self.v)
            if dps.get("21") in ("white", "colour"):
                self._show_mode(dps["21"])
            self._refresh_labels()
        finally:
            self._syncing = False


# =============================================================================
# Strona: Ambient
# =============================================================================
class AmbientPage(ctk.CTkFrame):
    def __init__(self, master, app: "App", scale: float):
        super().__init__(master, fg_color="transparent")
        self.app = app
        cfg = app.settings["ambient"]
        self.grid_columnconfigure(0, weight=3, uniform="amb")
        self.grid_columnconfigure(1, weight=2, uniform="amb")
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        label(left, "Ambient", 26, "bold").pack(anchor="w")
        self.status = label(left, "Zatrzymany", 13, color=theme.MUTED)
        self.status.pack(anchor="w")
        self.substatus = label(left, "", 12, color=theme.MUTED)
        self.substatus.pack(anchor="w")
        self.btn = ctk.CTkButton(head, text="▶  Start", width=150, height=44, corner_radius=12, font=font(15, "bold"),
                                 fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, command=app.toggle_ambient)
        self.btn.pack(side="right")

        # --- strefy
        zc = card(self)
        zc.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        label(zc, "Strefy ekranu", 16, "bold").pack(anchor="w", padx=20, pady=(18, 10))
        self.preview = ScreenPreview(zc, int(400 * scale))
        self.preview.pack(padx=20)
        rows = ctk.CTkFrame(zc, fg_color="transparent")
        rows.pack(fill="x", padx=20, pady=(14, 18))
        rows.grid_columnconfigure(1, weight=1)
        self.dots: dict[str, ctk.CTkFrame] = {}
        self.rates: dict[str, ctk.CTkLabel] = {}
        self.checks: dict[str, ctk.BooleanVar] = {}
        self.zone_menus: dict[str, ctk.CTkOptionMenu] = {}
        for i, b in enumerate(app.bulbs):
            per = bulb_settings(app.settings, b.id, i)
            dot = ctk.CTkFrame(rows, width=14, height=14, corner_radius=7, fg_color=theme.OFF_DOT)
            dot.grid(row=i, column=0, padx=(0, 10), pady=6)
            var = ctk.BooleanVar(value=per["ambient"])
            ctk.CTkCheckBox(rows, text=f"{i + 1}. {b.name}", variable=var, font=font(13), text_color=theme.TEXT,
                            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, border_color=theme.MUTED,
                            corner_radius=6, command=lambda b=b, v=var: app.bulb_toggle(b.id, v.get())
                            ).grid(row=i, column=1, sticky="w")
            menu = ctk.CTkOptionMenu(rows, values=ZONE_NAMES, width=170, font=font(13), dropdown_font=font(13),
                                     fg_color=theme.SURFACE_2, button_color=theme.SURFACE_3,
                                     button_hover_color=theme.ACCENT, dropdown_fg_color=theme.SURFACE_2,
                                     dropdown_hover_color=theme.SURFACE_3, text_color=theme.TEXT,
                                     command=lambda v, b=b: app.zone_changed(b.id, v))
            menu.set(ZONES.get(per["zone"], ZONE_NAMES[0]))
            menu.grid(row=i, column=2, padx=10)
            rate = label(rows, "", 12, color=theme.MUTED, width=56, anchor="e")
            rate.grid(row=i, column=3)
            self.dots[b.id], self.rates[b.id], self.checks[b.id], self.zone_menus[b.id] = dot, rate, var, menu

        # --- ustawienia
        sc = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=16,
                                    scrollbar_button_color=theme.SURFACE_2,
                                    scrollbar_button_hover_color=theme.SURFACE_3)
        sc.grid(row=1, column=1, sticky="nsew")
        label(sc, "Ustawienia", 16, "bold").pack(anchor="w", padx=12, pady=(10, 4))

        def slider(text, key, lo, hi, steps, fmt, hint, factor=1.0, is_int=True):
            box = ctk.CTkFrame(sc, fg_color="transparent")
            box.pack(fill="x", padx=12, pady=(10, 0))
            top = ctk.CTkFrame(box, fg_color="transparent")
            top.pack(fill="x")
            label(top, text, 13).pack(side="left")
            val = label(top, "", 13, "bold")
            val.pack(side="right")

            def changed(v, key=key):
                real = v / factor
                cfg[key] = int(round(real)) if is_int else round(real, 3)
                val.configure(text=fmt(v))
                app.schedule_save()
                if key == "edge_depth":
                    app.refresh_preview_layout()

            s = ctk.CTkSlider(box, from_=lo, to=hi, number_of_steps=steps, command=changed,
                              progress_color=theme.ACCENT, button_color=theme.TEXT,
                              button_hover_color="#ffffff", fg_color=theme.SURFACE_3, height=18)
            s.set(cfg[key] * factor)
            s.pack(fill="x", pady=(4, 0))
            val.configure(text=fmt(cfg[key] * factor))
            label(box, hint, 11, color=theme.MUTED, anchor="w", justify="left", wraplength=int(300 * scale)).pack(
                fill="x")

        slider("Odświeżanie", "fps", 1, MAX_FPS, MAX_FPS - 1, lambda v: f"{v:.0f} / s",
               "Ile razy na sekundę liczyć kolor. Żarówka i tak dostaje tylko faktyczne zmiany.")
        slider("Wygładzanie", "smoothing", 0, 95, 95, lambda v: f"{v:.0f}%",
               "Więcej = spokojniej, mniej = szybsza reakcja na błyski.", factor=100.0, is_int=False)
        slider("Nasycenie", "saturation", 1.0, 3.0, 20, lambda v: f"×{v:.1f}",
               "Podbija blade kolory z ekranu.", is_int=False)
        slider("Jasność minimalna", "min_brightness", 1, 100, 99, lambda v: f"{v:.0f}%", "Przy ciemnych scenach.")
        slider("Jasność maksymalna", "max_brightness", 1, 100, 99, lambda v: f"{v:.0f}%", "Przy jasnych scenach.")
        slider("Próg czerni", "black_threshold", 0, 30, 30, lambda v: f"{v:.0f}%",
               "Ciemniejszy obraz daje jasność minimalną.")
        slider("Szerokość krawędzi", "edge_depth", 5, 50, 45, lambda v: f"{v:.0f}%",
               "Jaka część ekranu należy do strefy krawędzi.")

        def option(text, values, current, cmd):
            box = ctk.CTkFrame(sc, fg_color="transparent")
            box.pack(fill="x", padx=12, pady=(14, 0))
            label(box, text, 13).pack(anchor="w")
            m = ctk.CTkOptionMenu(box, values=values, font=font(13), dropdown_font=font(13),
                                  fg_color=theme.SURFACE_2, button_color=theme.SURFACE_3,
                                  button_hover_color=theme.ACCENT, dropdown_fg_color=theme.SURFACE_2,
                                  dropdown_hover_color=theme.SURFACE_3, text_color=theme.TEXT, command=cmd)
            m.set(current)
            m.pack(fill="x", pady=(4, 0))

        def set_method(v):
            cfg["method"] = next(k for k, name in METHODS.items() if name == v)
            app.schedule_save()

        option("Sposób liczenia koloru", list(METHODS.values()), METHODS.get(cfg["method"], METHODS["vibrant"]),
               set_method)
        mons = list_monitors()

        def set_monitor(v):
            cfg["monitor"] = int(v.split(":")[0])
            app.schedule_save()

        option("Monitor", mons, mons[min(max(int(cfg["monitor"]) - 1, 0), len(mons) - 1)], set_monitor)

        grad = ctk.CTkSwitch(sc, text="Płynne przejścia w żarówce", font=font(13), text_color=theme.TEXT,
                             progress_color=theme.ACCENT, fg_color=theme.SURFACE_3, button_color=theme.TEXT,
                             command=lambda: (cfg.__setitem__("gradient", bool(grad.get())), app.schedule_save()))
        if cfg["gradient"]:
            grad.select()
        grad.pack(anchor="w", padx=12, pady=(16, 0))
        label(sc, "Gry: ustaw tryb okna bez ramek (borderless). Pełny ekran na wyłączność może blokować "
                  "przechwytywanie.", 11, color=theme.MUTED, justify="left", wraplength=int(300 * scale),
              anchor="w").pack(fill="x", padx=12, pady=(16, 10))

    def set_running(self, running: bool, stopping: bool = False):
        if stopping:
            self.btn.configure(text="Zatrzymywanie…", state="disabled")
        elif running:
            self.btn.configure(text="■  Stop", state="normal", fg_color=theme.ERR, hover_color=theme.ERR_HOVER)
        else:
            self.btn.configure(text="▶  Start", state="normal", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER)
            self.status.configure(text="Zatrzymany", text_color=theme.MUTED)
            self.substatus.configure(text="")
            for bid in self.rates:
                self.rates[bid].configure(text="")
                self.dots[bid].configure(fg_color=theme.OFF_DOT)


# =============================================================================
# Aplikacja
# =============================================================================
class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        root.title("BulBSync")
        root.configure(fg_color=theme.BG)
        self.events: queue.Queue = queue.Queue()
        self.settings = load_settings()
        self._save_job = None
        self.engine: AmbientEngine | None = None
        self.backend = ""
        self.restore: dict[str, dict] = {}
        self.in_ambient: set[str] = set()
        self.ambient_colors: dict[str, str] = {}

        try:
            self.bulbs = load_devices()
        except FileNotFoundError:
            messagebox.showerror("Brak devices.json", f"Nie znaleziono pliku:\n{DEVICES_PATH}\n\n"
                                 "Skopiuj tu devices.json z folderu, w którym uruchamiałeś "
                                 "'python -m tinytuya wizard'.")
            raise SystemExit(1)
        except ValueError as e:
            messagebox.showerror("Błędny devices.json", str(e))
            raise SystemExit(1)
        if not self.bulbs:
            messagebox.showerror("Brak żarówek", "devices.json nie zawiera żadnej żarówki z kluczem.")
            raise SystemExit(1)
        self.bulb_by_id = {b.id: b for b in self.bulbs}
        for b in self.bulbs:
            b.ip = self.settings["ip_overrides"].get(b.id) or b.ip
        self.workers = {b.id: BulbWorker(b, self.events) for b in self.bulbs}
        for w in self.workers.values():
            w.start()

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        content = ctk.CTkFrame(root, fg_color=theme.BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        scale = ctk.ScalingTracker.get_window_scaling(root)
        self.control = ControlPage(content, self, scale)
        self.ambient = AmbientPage(content, self, scale)
        for page in (self.control, self.ambient):
            page.grid(row=0, column=0, sticky="nsew")
        self.refresh_preview_layout()
        self.show_page("control")

        try:
            root.geometry(self.settings["window"].get("geometry") or "1180x780")
        except tk.TclError:
            root.geometry("1180x780")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(50, self._poll)

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self.root, fg_color=theme.SIDEBAR, corner_radius=0, width=210)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)
        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(26, 30))
        ctk.CTkFrame(logo, width=26, height=26, corner_radius=13, fg_color=theme.ACCENT).pack(side="left")
        label(logo, "BulBSync", 20, "bold").pack(side="left", padx=10)

        self.nav: dict[str, ctk.CTkButton] = {}
        for key, text in (("control", "Sterowanie"), ("ambient", "Ambient")):
            b = ctk.CTkButton(sb, text=text, anchor="w", height=42, corner_radius=10, font=font(14, "bold"),
                              fg_color="transparent", hover_color=theme.SURFACE_2, text_color=theme.MUTED,
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=12, pady=3)
            self.nav[key] = b

        bottom = ctk.CTkFrame(sb, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=18)
        style = dict(height=34, corner_radius=10, font=font(13), fg_color=theme.SURFACE_2,
                     hover_color=theme.SURFACE_3, text_color=theme.TEXT)
        ctk.CTkButton(bottom, text="Odśwież stan", command=self.refresh_all, **style).pack(fill="x", pady=3)
        self.scan_btn = ctk.CTkButton(bottom, text="Skanuj sieć", command=self.scan_network, **style)
        self.scan_btn.pack(fill="x", pady=3)
        label(bottom, f"v{__version__}", 11, color=theme.MUTED).pack(pady=(10, 0))

    def show_page(self, key):
        (self.control if key == "control" else self.ambient).tkraise()
        for k, b in self.nav.items():
            b.configure(fg_color=theme.SURFACE_2 if k == key else "transparent",
                        text_color=theme.TEXT if k == key else theme.MUTED)

    # --- polecenia
    def send(self, bulb_ids, dps, force: bool = False) -> bool:
        """Wysyła tylko to, co różni się od znanego stanu żarówki. Zwraca True, jeśli coś poszło."""
        sent = False
        for bid in bulb_ids:
            if bid in self.in_ambient:
                continue  # ambient ma pierwszeństwo
            w = self.workers[bid]
            todo = dps if force else {k: v for k, v in dps.items() if w.dps.get(k) != v}
            if todo:
                w.send(todo)
                sent = True
        return sent

    def power(self, target, on: bool):
        ids = [b.id for b in self.bulbs] if target == ALL else [target]
        self.send(ids, {"20": on}, force=True)
        if target == ALL:
            for bid in ids:
                t = self.control.tiles[bid].power
                t.select() if on else t.deselect()

    def refresh_all(self):
        for w in self.workers.values():
            w.request_status()

    def scan_network(self):
        self.scan_btn.configure(state="disabled", text="Skanowanie… ~20 s")

        def work():
            try:
                import tinytuya

                found = tinytuya.deviceScan(False, 20, False, False)
                result = {}
                for ip, d in (found or {}).items():
                    dev_id = d.get("gwId") or d.get("id")
                    if dev_id:
                        result[dev_id] = d.get("ip") or ip
                self.events.put(("scan", result))
            except Exception as e:
                self.events.put(("scan_error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, result: dict):
        self.scan_btn.configure(state="normal", text="Skanuj sieć")
        lines = []
        for b in self.bulbs:
            ip = result.get(b.id)
            if not ip:
                lines.append(f"✗ {b.name}: nie znaleziono")
            elif ip != b.ip:
                lines.append(f"✓ {b.name}: {b.ip or '?'} → {ip}")
                self.settings["ip_overrides"][b.id] = ip
                self.workers[b.id].set_ip(ip)
            else:
                lines.append(f"✓ {b.name}: {ip}")
        self.schedule_save()
        messagebox.showinfo("Wynik skanowania", "\n".join(lines) or "Nic nie znaleziono.")

    # --- ambient
    def refresh_preview_layout(self):
        zones = [
            (b.id, self.settings["bulbs"][b.id]["zone"], str(i + 1))
            for i, b in enumerate(self.bulbs)
            if self.settings["bulbs"][b.id]["ambient"]
        ]
        self.ambient.preview.set_layout(zones, self.settings["ambient"]["edge_depth"] / 100.0)
        self.ambient.preview.set_colors(self.ambient_colors)

    def bulb_toggle(self, bulb_id, on: bool):
        self.settings["bulbs"][bulb_id]["ambient"] = on
        self.schedule_save()
        self.refresh_preview_layout()
        if self.engine and not on and bulb_id in self.in_ambient:
            self.in_ambient.discard(bulb_id)
            self.workers[bulb_id].stop_ambient()
            self._restore_bulb(bulb_id)
        elif self.engine and on:
            self._enter_ambient(bulb_id)

    def zone_changed(self, bulb_id, zone_name):
        self.settings["bulbs"][bulb_id]["zone"] = ZONE_KEYS[ZONE_NAMES.index(zone_name)]
        self.schedule_save()
        self.refresh_preview_layout()

    def _assignments(self):
        return [(bid, self.workers[bid], self.settings["bulbs"][bid]["zone"]) for bid in list(self.in_ambient)]

    def _enter_ambient(self, bulb_id):
        w = self.workers[bulb_id]
        self.restore[bulb_id] = {k: w.dps[k] for k in ("20", "21", "22", "23", "24") if k in w.dps}
        self.in_ambient.add(bulb_id)
        self.control.tiles[bulb_id].show(w.online, None, w.dps, True)

    def _restore_bulb(self, bulb_id):
        snap = self.restore.pop(bulb_id, None) or {}
        if snap.get("21") not in ("white", "colour"):
            snap["21"] = "colour"
        w = self.workers[bulb_id]
        w.send(snap)
        self.ambient_colors.pop(bulb_id, None)
        self.ambient.dots[bulb_id].configure(fg_color=theme.OFF_DOT)
        self.control.tiles[bulb_id].show(w.online, None, {**w.dps, **snap}, False)

    def toggle_ambient(self):
        if self.engine:
            self.engine.stop()
            self.ambient.set_running(False, stopping=True)
            return
        chosen = [b.id for b in self.bulbs if self.settings["bulbs"][b.id]["ambient"]]
        if not chosen:
            messagebox.showinfo("Ambient", "Zaznacz co najmniej jedną żarówkę.")
            return
        for bid in chosen:
            self._enter_ambient(bid)
        self.engine = AmbientEngine(self.settings, self._assignments, self.events)
        self.engine.start()
        self.ambient.set_running(True)
        self.ambient.status.configure(text="Uruchamianie…", text_color=theme.MUTED)

    def _ambient_stopped(self):
        self.engine = None
        for bid in list(self.in_ambient):
            self.in_ambient.discard(bid)
            self._restore_bulb(bid)
        self.ambient.set_running(False)
        self.ambient.preview.set_colors({bid: theme.SURFACE_2 for bid in self.workers})

    # --- pętla zdarzeń
    def _poll(self):
        preview = None
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "state":
                    _, bid, st = ev
                    amb = bid in self.in_ambient
                    self.control.tiles[bid].show(st["online"], st["error"], st["dps"], amb,
                                                 self.ambient_colors.get(bid))
                    if not amb and self.control.target == bid:
                        self.control.sync_from(st["dps"])
                    any_on = any(w.dps.get("20") for w in self.workers.values())
                    group = self.control.tiles[ALL].power
                    group.select() if any_on else group.deselect()
                elif kind == "ambient_preview":
                    preview = ev[1]
                elif kind == "ambient_backend":
                    self.backend, reason = ev[1]
                    self.ambient.substatus.configure(
                        text=f"Szybsze przechwytywanie DXGI niedostępne: {reason}" if reason else "")
                elif kind == "ambient_fps":
                    fps, rates, cap_ms = ev[1]
                    self.ambient.status.configure(
                        text=f"Działa  ·  analiza ekranu {fps:.0f}/s  ·  zrzut ekranu {cap_ms:.0f} ms "
                             f"({self.backend})  ·  liczniki przy żarówkach = co do nich idzie",
                        text_color=theme.OK)
                    for bid, r in rates.items():
                        if bid in self.ambient.rates:
                            self.ambient.rates[bid].configure(text=f"{r:.0f}/s")
                elif kind == "ambient_error":
                    messagebox.showerror("Ambient", ev[1])
                elif kind == "ambient_stopped":
                    self._ambient_stopped()
                elif kind == "scan":
                    self._scan_done(ev[1])
                elif kind == "scan_error":
                    self.scan_btn.configure(state="normal", text="Skanuj sieć")
                    messagebox.showerror("Skanowanie", ev[1])
        except queue.Empty:
            pass
        if preview and self.engine:
            for bid, hsv in preview.items():
                hx = hex_of(tuya_hsv_to_rgb(*hsv))
                if self.ambient_colors.get(bid) != hx:
                    self.ambient_colors[bid] = hx
                    self.ambient.dots[bid].configure(fg_color=hx)
                    self.control.tiles[bid].dot.configure(fg_color=hx)
            self.ambient.preview.set_colors(self.ambient_colors)
        self.root.after(33, self._poll)

    # --- zapis
    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(800, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            save_settings(self.settings)
        except OSError as e:
            print(f"Nie udało się zapisać ustawień: {e}", file=sys.stderr)

    def on_close(self):
        if self.engine:
            self.engine.stop()
            self.engine.join(timeout=2)
            for bid in list(self.in_ambient):
                self._restore_bulb(bid)
            time.sleep(0.5)  # daj wątkom chwilę na wysłanie przywrócenia
        self.settings["window"]["geometry"] = self.root.geometry()
        self._save_now()
        for w in self.workers.values():
            w.shutdown()
        self.root.destroy()


def main():
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    App(root)
    root.minsize(1040, 700)
    root.mainloop()
