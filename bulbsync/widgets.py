"""Własne kontrolki rysowane przez Pillow: koło kolorów, suwak z gradientem, podgląd ekranu."""

from __future__ import annotations

import math
import tkinter as tk

import numpy as np
from PIL import Image, ImageDraw, ImageTk

from . import theme
from .color import tuya_hsv_to_rgb, zone_rect

SS = 4  # nadpróbkowanie przy rysowaniu kształtów, żeby krawędzie były gładkie


def hsv_to_rgb_np(h, s, v):
    """Wektorowe HSV (0-1) -> RGB (0-1)."""
    i = np.floor(h * 6.0).astype(int) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return r, g, b


def knob_image(diameter: int, fill, ring=(255, 255, 255), ring_w: float = 3.0) -> Image.Image:
    """Okrągły uchwyt: biały pierścień z cieniem i kolorowym środkiem."""
    d = diameter * SS
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse((SS, 2 * SS, d - SS, d - 1), fill=(0, 0, 0, 90))  # cień
    dr.ellipse((SS, SS, d - 2 * SS, d - 2 * SS), fill=tuple(ring) + (255,))
    w = ring_w * SS
    dr.ellipse((SS + w, SS + w, d - 2 * SS - w, d - 2 * SS - w), fill=tuple(int(c) for c in fill) + (255,))
    return img.resize((diameter, diameter), Image.LANCZOS)


class ColorWheel(tk.Canvas):
    """Koło kolorów: kąt = odcień, odległość od środka = nasycenie. `command(h 0-360, s 0-1000)`."""

    def __init__(self, master, size: int, command=None, bg: str = theme.SURFACE):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.size = size
        self.knob_d = max(18, size // 11)
        self.radius = size / 2 - self.knob_d / 2 - 2
        self.command = command
        self.h, self.s = 0, 1000
        self._wheel = ImageTk.PhotoImage(self._render())
        self.create_image(size / 2, size / 2, image=self._wheel)
        self._knob_img = None
        self._knob = self.create_image(0, 0)
        self.bind("<Button-1>", self._on_mouse)
        self.bind("<B1-Motion>", self._on_mouse)
        self.configure(cursor="hand2")
        self._draw_knob()

    def _render(self) -> Image.Image:
        n = self.size
        c = (n - 1) / 2
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        dx, dy = xx - c, c - yy
        dist = np.hypot(dx, dy)
        hue = (np.arctan2(dy, dx) / (2 * math.pi)) % 1.0
        sat = np.clip(dist / self.radius, 0, 1)
        r, g, b = hsv_to_rgb_np(hue, sat, np.ones_like(sat))
        alpha = np.clip(self.radius - dist + 0.5, 0, 1)  # gładka krawędź bez nadpróbkowania
        rgba = np.dstack([r, g, b, alpha]) * 255
        return Image.fromarray(rgba.astype(np.uint8), "RGBA")

    def _pos(self):
        ang = math.radians(self.h)
        rr = self.radius * self.s / 1000
        c = self.size / 2
        return c + rr * math.cos(ang), c - rr * math.sin(ang)

    def _draw_knob(self):
        self._knob_img = ImageTk.PhotoImage(knob_image(self.knob_d, tuya_hsv_to_rgb(self.h, self.s, 1000)))
        x, y = self._pos()
        self.itemconfigure(self._knob, image=self._knob_img)
        self.coords(self._knob, x, y)

    def _on_mouse(self, e):
        c = self.size / 2
        dx, dy = e.x - c, c - e.y
        self.h = int(round(math.degrees(math.atan2(dy, dx)))) % 360
        self.s = int(round(min(1.0, math.hypot(dx, dy) / self.radius) * 1000))
        self._draw_knob()
        if self.command:
            self.command(self.h, self.s)

    def set(self, h: int, s: int):
        self.h, self.s = int(h) % 360, max(0, min(1000, int(s)))
        self._draw_knob()


class GradientSlider(tk.Canvas):
    """Suwak z kolorowym paskiem (np. jasność albo barwa bieli). `command(value)`."""

    def __init__(self, master, width: int, from_: float, to: float, value: float, stops, command=None,
                 height: int = 30, bg: str = theme.SURFACE):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.w, self.h = width, height
        self.from_, self.to = from_, to
        self.value = value
        self.command = command
        self.knob_d = height - 2
        self.pad = self.knob_d / 2
        self._track_img = None
        self._knob_img = None
        self._track = self.create_image(width / 2, height / 2)
        self._knob = self.create_image(0, height / 2)
        self.stops = stops
        self.set_stops(stops)
        self.bind("<Button-1>", self._on_mouse)
        self.bind("<B1-Motion>", self._on_mouse)
        self.configure(cursor="hand2")

    def set_stops(self, stops):
        """`stops`: lista kolorów RGB rozłożonych równo na pasku."""
        self.stops = [tuple(s) for s in stops]
        tw = int(self.w - 2 * self.pad + self.knob_d * 0.6)
        th = max(8, int(self.h * 0.42))
        xs = np.linspace(0, 1, tw)
        pos = np.linspace(0, 1, len(self.stops))
        cols = np.array(self.stops, dtype=np.float32)
        row = np.stack([np.interp(xs, pos, cols[:, k]) for k in range(3)], axis=1)
        grad = np.repeat(row[None, :, :], th, axis=0).astype(np.uint8)
        img = Image.fromarray(grad, "RGB").convert("RGBA")
        mask = Image.new("L", (tw * SS, th * SS), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw * SS - 1, th * SS - 1), radius=th * SS // 2, fill=255)
        img.putalpha(mask.resize((tw, th), Image.LANCZOS))
        self._track_img = ImageTk.PhotoImage(img)
        self.itemconfigure(self._track, image=self._track_img)
        self._draw_knob()

    def _color_at(self, f: float):
        pos = np.linspace(0, 1, len(self.stops))
        return tuple(float(np.interp(f, pos, [s[k] for s in self.stops])) for k in range(3))

    def _frac(self):
        span = self.to - self.from_
        return 0.0 if span == 0 else (self.value - self.from_) / span

    def _draw_knob(self):
        f = max(0.0, min(1.0, self._frac()))
        self._knob_img = ImageTk.PhotoImage(knob_image(self.knob_d, self._color_at(f)))
        self.itemconfigure(self._knob, image=self._knob_img)
        self.coords(self._knob, self.pad + f * (self.w - 2 * self.pad), self.h / 2)

    def _on_mouse(self, e):
        f = max(0.0, min(1.0, (e.x - self.pad) / (self.w - 2 * self.pad)))
        self.value = round(self.from_ + f * (self.to - self.from_))
        self._draw_knob()
        if self.command:
            self.command(self.value)

    def set(self, value: float):
        self.value = max(min(self.from_, self.to), min(max(self.from_, self.to), value))
        self._draw_knob()

    def get(self) -> float:
        return self.value


class ScreenPreview(tk.Canvas):
    """Miniatura ekranu ze strefami żarówek wypełnionymi ich aktualnym kolorem."""

    def __init__(self, master, width: int, bg: str = theme.SURFACE):
        self.w = width
        self.h = int(width * 9 / 16)
        super().__init__(master, width=self.w, height=self.h + 6, bg=bg, highlightthickness=0, bd=0)
        self._items: dict[str, tuple[int, int]] = {}

    def set_layout(self, zones: list[tuple[str, str, str]], depth: float):
        """`zones`: lista (bulb_id, strefa, etykieta)."""
        self.delete("all")
        self._items.clear()
        self.create_rectangle(1, 1, self.w - 2, self.h - 2, fill="#0d0f13", outline=theme.BORDER, width=2)
        for bid, zone, label in zones:
            x0, y0, x1, y1 = zone_rect(self.w - 8, self.h - 8, zone, depth)
            rect = self.create_rectangle(
                x0 + 4, y0 + 4, x1 + 4, y1 + 4, fill=theme.SURFACE_2, outline=theme.MUTED, width=1
            )
            txt = self.create_text(
                (x0 + x1) / 2 + 4, (y0 + y1) / 2 + 4, text=label, fill=theme.TEXT, font=(theme.FONT, 10, "bold")
            )
            self._items[bid] = (rect, txt)
        if not zones:
            self.create_text(self.w / 2, self.h / 2, text="Brak żarówek w ambient", fill=theme.MUTED)

    def set_colors(self, colors: dict[str, str]):
        for bid, hx in colors.items():
            if bid in self._items:
                rect, txt = self._items[bid]
                self.itemconfigure(rect, fill=hx)
                r, g, b = (int(hx[i: i + 2], 16) for i in (1, 3, 5))
                self.itemconfigure(txt, fill="#111111" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff")

