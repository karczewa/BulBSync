"""Okno aplikacji: zakładki Sterowanie i Ambient."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from . import __version__
from .ambient import AmbientEngine, list_monitors
from .bulb import BulbWorker
from .color import (
    ZONES,
    colour_data_v2,
    parse_colour_data_v2,
    rgb_to_tuya_hsv,
    tuya_hsv_to_rgb,
)
from .config import DEVICES_PATH, bulb_settings, load_devices, load_settings, save_settings

QUICK_COLOURS = [
    ("#ff0000", "Czerwony"),
    ("#ff6a00", "Pomarańczowy"),
    ("#ffd000", "Żółty"),
    ("#00ff00", "Zielony"),
    ("#00ffd5", "Turkusowy"),
    ("#0040ff", "Niebieski"),
    ("#8000ff", "Fioletowy"),
    ("#ff00b0", "Różowy"),
]

WHITE_PRESETS = [
    ("Ciepłe", 100, 0),
    ("Neutralne", 100, 50),
    ("Zimne", 100, 100),
    ("Nocne", 10, 0),
]

ZONE_KEYS = list(ZONES.keys())
ZONE_NAMES = list(ZONES.values())
METHODS = {"vibrant": "Wyraziste kolory", "average": "Średnia z ekranu"}

USER_EDIT_GRACE = 3.0  # przez tyle sekund po ruchu suwaka nie nadpisujemy go stanem z żarówki


def hex_of(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


class BulbCard(ttk.LabelFrame):
    """Panel sterowania jedną żarówką albo wszystkimi naraz."""

    def __init__(self, master, app: "App", title: str, bulb_ids: list[str], is_group: bool = False):
        super().__init__(master, text=title, padding=8)
        self.app = app
        self.bulb_ids = bulb_ids
        self.is_group = is_group
        self._syncing = False
        self._last_user_edit = 0.0
        self.hs = (0, 1000)  # odcień i nasycenie wybranego koloru

        # --- wiersz 1: status i włącz/wyłącz
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.status = tk.Label(top, text="● łączenie…", fg="#888888", anchor="w")
        self.status.pack(side="left")
        ttk.Button(top, text="Wyłącz", width=8, command=lambda: self.power(False)).pack(side="right")
        ttk.Button(top, text="Włącz", width=8, command=lambda: self.power(True)).pack(side="right", padx=(0, 4))

        # --- tryb
        self.mode = tk.StringVar(value="colour")
        modes = ttk.Frame(self)
        modes.pack(fill="x", pady=(6, 2))
        ttk.Radiobutton(modes, text="Biały", value="white", variable=self.mode, command=self._mode_changed).pack(
            side="left"
        )
        ttk.Radiobutton(modes, text="Kolor", value="colour", variable=self.mode, command=self._mode_changed).pack(
            side="left", padx=8
        )

        # --- sekcja białego
        self.white_frame = ttk.Frame(self)
        self.white_bright = self._scale(self.white_frame, "Jasność %", 1, 100, 100, self._white_changed)
        self.white_temp = self._scale(self.white_frame, "Barwa: ciepła → zimna", 0, 100, 30, self._white_changed)
        presets = ttk.Frame(self.white_frame)
        presets.pack(fill="x", pady=(4, 0))
        for name, b, t in WHITE_PRESETS:
            ttk.Button(presets, text=name, width=9, command=lambda b=b, t=t: self._white_preset(b, t)).pack(
                side="left", padx=(0, 4)
            )

        # --- sekcja koloru
        self.colour_frame = ttk.Frame(self)
        row = ttk.Frame(self.colour_frame)
        row.pack(fill="x")
        self.swatch = tk.Label(row, text="", width=6, bg="#ff0000", relief="ridge", cursor="hand2")
        self.swatch.pack(side="left", ipady=6)
        self.swatch.bind("<Button-1>", lambda e: self._pick_colour())
        ttk.Button(row, text="Wybierz kolor…", command=self._pick_colour).pack(side="left", padx=6)
        quick = ttk.Frame(self.colour_frame)
        quick.pack(fill="x", pady=4)
        for hx, name in QUICK_COLOURS:
            lbl = tk.Label(quick, bg=hx, width=3, relief="raised", cursor="hand2")
            lbl.pack(side="left", padx=1, ipady=4)
            lbl.bind("<Button-1>", lambda e, hx=hx: self._quick_colour(hx))
        self.colour_bright = self._scale(self.colour_frame, "Jasność %", 1, 100, 100, self._colour_changed)

        self._mode_changed(send=False)

    # --- budowanie
    def _scale(self, parent, label, lo, hi, init, cmd):
        f = ttk.Frame(parent)
        f.pack(fill="x")
        ttk.Label(f, text=label, width=20).pack(side="left")
        var = tk.IntVar(value=init)
        s = tk.Scale(
            f, from_=lo, to=hi, orient="horizontal", variable=var, showvalue=True, length=220, command=lambda _v: cmd()
        )
        s.pack(side="left", fill="x", expand=True)
        return var

    # --- wysyłanie
    def _send(self, dps: dict):
        if not self._syncing and self.app.send(self.bulb_ids, dps):
            self._last_user_edit = time.monotonic()

    def power(self, on: bool):
        self.app.send(self.bulb_ids, {"20": on}, force=True)

    def _mode_changed(self, send: bool = True):
        if self.mode.get() == "white":
            self.colour_frame.pack_forget()
            self.white_frame.pack(fill="x")
            if send:
                self._white_changed()
        else:
            self.white_frame.pack_forget()
            self.colour_frame.pack(fill="x")
            if send:
                self._colour_changed()

    def _white_changed(self):
        b = max(10, self.white_bright.get() * 10)
        t = self.white_temp.get() * 10
        self._send({"20": True, "21": "white", "22": b, "23": t})

    def _white_preset(self, b, t):
        self.white_bright.set(b)
        self.white_temp.set(t)
        self._white_changed()

    def _colour_changed(self):
        h, s = self.hs
        v = max(10, self.colour_bright.get() * 10)
        self.swatch.configure(bg=hex_of(tuya_hsv_to_rgb(h, s, 1000)))
        self._send({"20": True, "21": "colour", "24": colour_data_v2(h, s, v)})

    def _set_colour_rgb(self, rgb):
        h, s, _ = rgb_to_tuya_hsv(*rgb)
        self.hs = (h, s)
        self.mode.set("colour")
        self._mode_changed(send=False)
        self._colour_changed()

    def _pick_colour(self):
        init = hex_of(tuya_hsv_to_rgb(*self.hs, 1000))
        res = colorchooser.askcolor(color=init, title="Wybierz kolor", parent=self)
        if res and res[0]:
            self._set_colour_rgb(res[0])

    def _quick_colour(self, hx):
        self._set_colour_rgb(tuple(int(hx[i : i + 2], 16) for i in (1, 3, 5)))

    # --- aktualizacja ze stanu żarówki
    def show_state(self, online, error, dps, in_ambient=False):
        if in_ambient:
            self.status.configure(text="● ambient", fg="#7b3fe4")
        elif online:
            on = dps.get("20")
            self.status.configure(
                text="● połączona – " + ("włączona" if on else "wyłączona" if on is False else "?"),
                fg="#1a9c3a",
            )
        elif online is False:
            msg = "● brak połączenia"
            if error:
                msg += f" ({error[:60]})"
            self.status.configure(text=msg, fg="#d03030")
        if self.is_group or not dps or time.monotonic() - self._last_user_edit < USER_EDIT_GRACE:
            return
        self._syncing = True
        try:
            mode = dps.get("21")
            if mode in ("white", "colour"):
                self.mode.set(mode)
                self._mode_changed(send=False)
            if isinstance(dps.get("22"), int):
                self.white_bright.set(max(1, round(dps["22"] / 10)))
            if isinstance(dps.get("23"), int):
                self.white_temp.set(round(dps["23"] / 10))
            hsv = parse_colour_data_v2(dps.get("24", ""))
            if hsv:
                self.hs = (hsv[0], hsv[1])
                self.colour_bright.set(max(1, round(hsv[2] / 10)))
                self.swatch.configure(bg=hex_of(tuya_hsv_to_rgb(hsv[0], hsv[1], 1000)))
        finally:
            self._syncing = False


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"BulBSync {__version__}")
        self.events: queue.Queue = queue.Queue()
        self.settings = load_settings()
        self._save_job = None
        self.engine: AmbientEngine | None = None
        self.restore: dict[str, dict] = {}
        self.in_ambient: set[str] = set()

        try:
            self.bulbs = load_devices()
        except FileNotFoundError:
            messagebox.showerror(
                "Brak devices.json",
                f"Nie znaleziono pliku:\n{DEVICES_PATH}\n\n"
                "Skopiuj tu devices.json z folderu, w którym uruchamiałeś 'python -m tinytuya wizard'.",
            )
            raise SystemExit(1)
        except ValueError as e:
            messagebox.showerror("Błędny devices.json", str(e))
            raise SystemExit(1)
        if not self.bulbs:
            messagebox.showerror("Brak żarówek", "devices.json nie zawiera żadnej żarówki z kluczem.")
            raise SystemExit(1)

        for b in self.bulbs:
            override = self.settings["ip_overrides"].get(b.id)
            if override:
                b.ip = override
        self.workers = {b.id: BulbWorker(b, self.events) for b in self.bulbs}
        for w in self.workers.values():
            w.start()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_control_tab(nb)
        self._build_ambient_tab(nb)

        try:
            root.geometry(self.settings["window"].get("geometry") or "720x820")
        except tk.TclError:
            root.geometry("720x820")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(50, self._poll)

    # ======================================================================
    # Sterowanie
    # ======================================================================
    def _build_control_tab(self, nb):
        outer = ttk.Frame(nb)
        nb.add(outer, text="  Sterowanie  ")
        bar = ttk.Frame(outer, padding=(4, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Odśwież stan", command=self.refresh_all).pack(side="left")
        self.scan_btn = ttk.Button(bar, text="Skanuj sieć (aktualizuj IP)", command=self.scan_network)
        self.scan_btn.pack(side="left", padx=6)
        self.ambient_banner = ttk.Label(bar, text="", foreground="#7b3fe4")
        self.ambient_banner.pack(side="right")

        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units") if self._is_control_visible(nb, outer) else None,
        )

        self.cards: dict[str, BulbCard] = {}
        all_ids = [b.id for b in self.bulbs]
        self.group_card = BulbCard(inner, self, "Wszystkie żarówki", all_ids, is_group=True)
        self.group_card.pack(fill="x", padx=4, pady=4)
        self.group_card.status.configure(text=f"{len(all_ids)} żarówki", fg="#555555")
        for b in self.bulbs:
            card = BulbCard(inner, self, f"{b.name}   ({b.ip or 'brak IP'})", [b.id])
            card.pack(fill="x", padx=4, pady=4)
            self.cards[b.id] = card

    @staticmethod
    def _is_control_visible(nb, frame):
        try:
            return nb.select() == str(frame)
        except tk.TclError:
            return False

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

    def refresh_all(self):
        for w in self.workers.values():
            w.request_status()

    def scan_network(self):
        self.scan_btn.configure(state="disabled", text="Skanowanie… (ok. 20 s)")

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
        self.scan_btn.configure(state="normal", text="Skanuj sieć (aktualizuj IP)")
        lines = []
        for b in self.bulbs:
            ip = result.get(b.id)
            if not ip:
                lines.append(f"✗ {b.name}: nie znaleziono")
                continue
            if ip != b.ip:
                lines.append(f"✓ {b.name}: {b.ip or '?'} → {ip}")
                self.settings["ip_overrides"][b.id] = ip
                self.workers[b.id].set_ip(ip)
                self.cards[b.id].configure(text=f"{b.name}   ({ip})")
            else:
                lines.append(f"✓ {b.name}: {ip} (bez zmian)")
        self.schedule_save()
        messagebox.showinfo("Wynik skanowania", "\n".join(lines) or "Nic nie znaleziono.")

    # ======================================================================
    # Ambient
    # ======================================================================
    def _build_ambient_tab(self, nb):
        tab = ttk.Frame(nb, padding=8)
        nb.add(tab, text="  Ambient  ")
        cfg = self.settings["ambient"]

        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.amb_btn = ttk.Button(top, text="▶  Start ambient", command=self.toggle_ambient)
        self.amb_btn.pack(side="left", ipadx=10, ipady=4)
        self.amb_status = ttk.Label(top, text="Zatrzymany")
        self.amb_status.pack(side="left", padx=12)

        # --- żarówki i strefy
        bf = ttk.LabelFrame(tab, text="Żarówki i strefy ekranu", padding=8)
        bf.pack(fill="x", pady=8)
        self.previews: dict[str, tk.Label] = {}
        for i, b in enumerate(self.bulbs):
            per = bulb_settings(self.settings, b.id, i)
            row = ttk.Frame(bf)
            row.pack(fill="x", pady=2)
            on_var = tk.BooleanVar(value=per["ambient"])
            ttk.Checkbutton(
                row, text=b.name, width=22, variable=on_var, command=lambda b=b, v=on_var: self._bulb_toggle(b.id, v)
            ).pack(side="left")
            zone_var = tk.StringVar(value=ZONES.get(per["zone"], ZONE_NAMES[0]))
            cb = ttk.Combobox(row, values=ZONE_NAMES, textvariable=zone_var, state="readonly", width=18)
            cb.pack(side="left", padx=6)
            cb.bind("<<ComboboxSelected>>", lambda e, b=b, v=zone_var: self._zone_changed(b.id, v))
            pv = tk.Label(row, width=8, bg="#202020", relief="sunken")
            pv.pack(side="left", padx=6, ipady=3)
            self.previews[b.id] = pv

        # --- ustawienia
        sf = ttk.LabelFrame(tab, text="Ustawienia", padding=8)
        sf.pack(fill="x")
        sf.columnconfigure(1, weight=1, minsize=200)
        r = 0

        def add_scale(label, key, lo, hi, res=1, factor=1.0, hint=""):
            nonlocal r
            ttk.Label(sf, text=label).grid(row=r, column=0, sticky="w")
            var = tk.DoubleVar(value=cfg[key] * factor)

            def changed(_v, key=key, var=var, factor=factor, res=res):
                val = var.get() / factor
                cfg[key] = int(round(val)) if res >= 1 and factor == 1.0 else round(val, 3)
                self.schedule_save()

            tk.Scale(sf, from_=lo, to=hi, resolution=res, orient="horizontal", variable=var, command=changed).grid(
                row=r, column=1, sticky="ew"
            )
            if hint:
                ttk.Label(sf, text=hint, foreground="#777777", wraplength=170).grid(row=r, column=2, sticky="w", padx=6)
            r += 1

        add_scale("Odświeżanie (na sekundę)", "fps", 1, 30, hint="więcej = szybciej, ale żarówki mogą nie nadążyć")
        add_scale("Wygładzanie %", "smoothing", 0, 95, factor=100.0, hint="więcej = płynniej, ale wolniej")
        add_scale("Nasycenie ×", "saturation", 1.0, 3.0, res=0.1, hint="podbija blade kolory z ekranu")
        add_scale("Jasność min %", "min_brightness", 1, 100, hint="w ciemnych scenach")
        add_scale("Jasność max %", "max_brightness", 1, 100, hint="w jasnych scenach")
        add_scale("Próg czerni %", "black_threshold", 0, 30, hint="ciemniejszy obraz = jasność min")
        add_scale("Szerokość krawędzi %", "edge_depth", 5, 50, hint="jaka część ekranu to strefa krawędzi")

        ttk.Label(sf, text="Sposób liczenia koloru").grid(row=r, column=0, sticky="w", pady=(6, 0))
        meth_var = tk.StringVar(value=METHODS.get(cfg["method"], METHODS["vibrant"]))
        mcb = ttk.Combobox(sf, values=list(METHODS.values()), textvariable=meth_var, state="readonly", width=24)
        mcb.grid(row=r, column=1, columnspan=2, sticky="w", pady=(6, 0))

        def meth_changed(_e):
            cfg["method"] = next(k for k, v in METHODS.items() if v == meth_var.get())
            self.schedule_save()

        mcb.bind("<<ComboboxSelected>>", meth_changed)
        r += 1

        ttk.Label(sf, text="Monitor").grid(row=r, column=0, sticky="w", pady=(6, 0))
        mons = list_monitors()
        mon_var = tk.StringVar(value=mons[min(max(int(cfg["monitor"]) - 1, 0), len(mons) - 1)])
        moncb = ttk.Combobox(sf, values=mons, textvariable=mon_var, state="readonly", width=24)
        moncb.grid(row=r, column=1, columnspan=2, sticky="w", pady=(6, 0))

        def mon_changed(_e):
            cfg["monitor"] = int(mon_var.get().split(":")[0])
            self.schedule_save()

        moncb.bind("<<ComboboxSelected>>", mon_changed)
        r += 1

        grad_var = tk.BooleanVar(value=bool(cfg["gradient"]))

        def grad_changed():
            cfg["gradient"] = grad_var.get()
            self.schedule_save()

        ttk.Checkbutton(
            sf, text="Płynne przejścia w żarówce (gradient)", variable=grad_var, command=grad_changed
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 0))
        r += 1

        ttk.Label(
            tab,
            text="Wskazówka: gry w trybie pełnoekranowym na wyłączność mogą blokować przechwytywanie ekranu. "
            "Ustaw w grze tryb okna bez ramek (borderless).",
            foreground="#777777",
            wraplength=520,
        ).pack(fill="x", pady=(8, 0))

    def _bulb_toggle(self, bulb_id, var):
        self.settings["bulbs"][bulb_id]["ambient"] = var.get()
        self.schedule_save()
        if self.engine and not var.get() and bulb_id in self.in_ambient:
            self.in_ambient.discard(bulb_id)
            self.workers[bulb_id].stop_ambient()
            self._restore_bulb(bulb_id)
        elif self.engine and var.get():
            self._enter_ambient(bulb_id)

    def _zone_changed(self, bulb_id, var):
        self.settings["bulbs"][bulb_id]["zone"] = ZONE_KEYS[ZONE_NAMES.index(var.get())]
        self.schedule_save()

    def _assignments(self):
        return [
            (bid, self.workers[bid], self.settings["bulbs"][bid]["zone"])
            for bid in list(self.in_ambient)
            if bid in self.workers
        ]

    def _enter_ambient(self, bulb_id):
        w = self.workers[bulb_id]
        snap = {k: w.dps[k] for k in ("20", "21", "22", "23", "24") if k in w.dps}
        self.restore[bulb_id] = snap
        self.in_ambient.add(bulb_id)
        self.cards[bulb_id].show_state(w.online, None, w.dps, in_ambient=True)

    def _restore_bulb(self, bulb_id):
        snap = self.restore.pop(bulb_id, None)
        w = self.workers[bulb_id]
        if snap:
            if snap.get("21") not in ("white", "colour"):
                snap["21"] = "colour"
            w.send(snap)
        else:
            w.send({"21": "colour"})
        self.previews[bulb_id].configure(bg="#202020")
        self.cards[bulb_id].show_state(w.online, None, w.dps)

    def toggle_ambient(self):
        if self.engine:
            self.engine.stop()
            self.amb_btn.configure(state="disabled", text="Zatrzymywanie…")
            return
        chosen = [b.id for b in self.bulbs if self.settings["bulbs"][b.id]["ambient"]]
        if not chosen:
            messagebox.showinfo("Ambient", "Zaznacz co najmniej jedną żarówkę.")
            return
        for bid in chosen:
            self._enter_ambient(bid)
        self.engine = AmbientEngine(self.settings, self._assignments, self.events)
        self.engine.start()
        self.amb_btn.configure(text="■  Stop ambient")
        self.amb_status.configure(text="Uruchamianie…")
        self.ambient_banner.configure(text="Ambient działa – sterowanie ręczne żarówek w ambient jest wstrzymane")

    def _ambient_stopped(self):
        self.engine = None
        for bid in list(self.in_ambient):
            self.in_ambient.discard(bid)
            self._restore_bulb(bid)
        self.amb_btn.configure(state="normal", text="▶  Start ambient")
        self.amb_status.configure(text="Zatrzymany")
        self.ambient_banner.configure(text="")

    # ======================================================================
    # Pętla zdarzeń i zapisywanie
    # ======================================================================
    def _poll(self):
        preview = None
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "state":
                    _, bid, st = ev
                    self.cards[bid].show_state(st["online"], st["error"], st["dps"], in_ambient=bid in self.in_ambient)
                elif kind == "ambient_preview":
                    preview = ev[1]
                elif kind == "ambient_fps":
                    self.amb_status.configure(text=f"Działa – {ev[1]:.1f} klatek/s")
                elif kind == "ambient_error":
                    messagebox.showerror("Ambient", ev[1])
                elif kind == "ambient_stopped":
                    self._ambient_stopped()
                elif kind == "scan":
                    self._scan_done(ev[1])
                elif kind == "scan_error":
                    self.scan_btn.configure(state="normal", text="Skanuj sieć (aktualizuj IP)")
                    messagebox.showerror("Skanowanie", ev[1])
        except queue.Empty:
            pass
        if preview and self.engine:
            for bid, hsv in preview.items():
                if bid in self.previews:
                    self.previews[bid].configure(bg=hex_of(tuya_hsv_to_rgb(*hsv)))
        self.root.after(50, self._poll)

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
    if sys.platform == "win32":
        try:  # ostre okno na ekranach ze skalowaniem
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.minsize(560, 480)
    root.mainloop()
