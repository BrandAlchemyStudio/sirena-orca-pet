"""Sirena: a floating desktop pet that reacts to Claude Code.

Plays Sirena's Codex spritesheet (8 cols x 11 rows of 192x208 cells) in a
borderless, always-on-top, per-pixel-transparent window (Windows layered
window). Claude Code hooks (sirena_hook.py) write one state file per session
into states/; this window reads them twice a second and picks what she does.

What she does and when (timings live in config.json):
  Claude is working ............ Working at the Coral Desk
  a tool or turn fails ......... Sad Sigh
  Claude waits for you ......... lies on her belly blowing bubbles, with a bubble
                                 naming the project (finished / needs your OK)
  ...no answer for a while ..... climbs into the Scallop-Shell Bed and sleeps, breathing
  nothing going on ............. Idle with Fish, eyes follow your mouse,
                                 sometimes swims (dolphin right / mantas left)
  ...idle for a while .......... sleeps in the shell bed
  you hover over her ........... Octopus Review + what every session is doing
  you drag her right / left .... Dolphin Ride / Manta Glide
Right-click: size / swim around / hide 1 hour / quit.
"""
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import random
import socket
import sys
import time
import tkinter as tk
import traceback

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(HERE, "spritesheet.webp")
STATES_DIR = os.path.join(HERE, "states")
CONFIG = os.path.join(HERE, "config.json")
LOG = os.path.join(HERE, "sirena.log")

CELL_W, CELL_H = 192, 208
TICK_MS = 33

# clip name -> (row, per-frame ms) — timings from her installed Codex GIFs
ROWS = {
    "idle": (0, [280, 110, 110, 140, 140, 320]),  # Idle with Fish
    "swim_right": (1, [120] * 7 + [220]),  # Dolphin Ride
    "swim_left": (2, [120] * 7 + [220]),  # Manta Glide
    "hello": (3, [140, 140, 140, 280]),  # Bubble Hello (session start)
    "hover": (4, [140, 140, 140, 140, 280]),  # Octopus Review
    "sigh": (5, [140] * 7 + [240]),  # Sad Sigh
    "working": (7, [120] * 5 + [220]),  # Working at the Coral Desk
    "call": (8, [150] * 5 + [280]),  # on her belly, blowing bubbles
}
BED = 6  # Scallop-Shell Bed: frames 0-2 climbing in, 3-5 asleep with growing Zz
SLEEP_INTRO = [(BED, 0, 260), (BED, 1, 260), (BED, 2, 300), (BED, 3, 500)]
SLEEP_LOOP = [(BED, 3, 900), (BED, 4, 900), (BED, 5, 900)]
WAKE = [(BED, 2, 110), (BED, 1, 110), (BED, 0, 140)]
LOOK_ROWS = (9, 10)  # 16 look poses, clockwise from "up"
BREATH_STEPS, BREATH_SECONDS = 10, 4.2

SIZES = {"small": 0.45, "medium": 0.6, "large": 0.8}
DEFAULTS = {"x": None, "y": None, "size": "medium", "wander": True,
            "wait_to_sleep_seconds": 120,  # waiting for you this long -> she falls asleep
            "idle_to_sleep_seconds": 300,  # nothing going on this long -> she falls asleep
            "working_timeout_minutes": 15}  # no news from a working session -> treat as asleep

# phase -> priority when several sessions are open (the most urgent one wins)
PRIORITY = {"call": 5, "sigh": 4, "working": 3, "hello": 2, "asleep": 1}

# ---------------------------------------------------------------- Win32 bits
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
                                       wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = wt.HWND(-1)
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE


def dpi_scale():
    try:
        return user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def work_area():
    rect = wt.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def virtual_screen():
    x, y = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    return x, y, x + user32.GetSystemMetrics(78), y + user32.GetSystemMetrics(79)


class LayeredSurface:
    """Pushes a premultiplied BGRA buffer to a layered window."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.size = None
        self.bits = ctypes.c_void_p()
        self.bitmap = None
        self.blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA

    def _ensure(self, w, h):
        if self.size == (w, h):
            return
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth, bmi.biHeight = w, -h  # top-down
        bmi.biPlanes, bmi.biBitCount = 1, 32
        self.bitmap = gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.mem_dc, self.bitmap)
        self.size = (w, h)

    def show(self, bgra_bytes, w, h):
        self._ensure(w, h)
        ctypes.memmove(self.bits, bgra_bytes, len(bgra_bytes))
        size = wt.SIZE(w, h)
        src = wt.POINT(0, 0)
        user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, None, ctypes.byref(size), self.mem_dc,
                                   ctypes.byref(src), 0, ctypes.byref(self.blend), 2)  # ULW_ALPHA


def to_premultiplied_bgra(img):
    a = np.asarray(img, dtype=np.uint16)
    out = np.empty(a.shape, dtype=np.uint8)
    alpha = a[..., 3]
    out[..., 0] = (a[..., 2] * alpha // 255)
    out[..., 1] = (a[..., 1] * alpha // 255)
    out[..., 2] = (a[..., 0] * alpha // 255)
    out[..., 3] = alpha
    return out.tobytes()


def load_font(px):
    for name in ("seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def log_error():
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- sessions
def session_phase(state, age, cfg):
    """What one Claude session means for Sirena right now (None = nothing to show)."""
    wait = cfg["wait_to_sleep_seconds"]
    work_limit = cfg["working_timeout_minutes"] * 60
    if state == "working":
        return "working" if age < work_limit else "asleep"
    if state == "oops":  # one tool call failed: a short sigh, then back to work
        if age < 1.4:
            return "sigh"
        return "working" if age < work_limit else "asleep"
    if state == "failed":  # the whole turn failed: sigh, then wait for you
        if age < 5:
            return "sigh"
        return "call" if age - 5 < wait else "asleep"
    if state in ("waiting", "needs_you", "done", "napping"):
        return "call" if age < wait else "asleep"
    if state == "hello":
        return "hello" if age < 3 else None
    return None


def read_sessions(now, cfg):
    sessions = []
    try:
        names = os.listdir(STATES_DIR)
    except OSError:
        return sessions
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(STATES_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        age = now - float(rec.get("ts", 0))
        if age > 24 * 3600:
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        phase = session_phase(rec.get("state"), age, cfg)
        if phase:
            sessions.append({"phase": phase, "kind": rec.get("state"), "project": rec.get("project", "Claude"),
                             "ts": float(rec.get("ts", 0))})
    return sessions


def session_label(s):
    if s["phase"] == "call":
        return {"needs_you": "needs your OK", "failed": "hit an error"}.get(s["kind"], "waiting for you")
    return {"working": "working", "sigh": "oops", "hello": "just started", "asleep": "asleep, waiting for you"}[s["phase"]]


# ---------------------------------------------------------------- the pet
class Sirena:
    def __init__(self):
        self.cfg = self._load_config()
        self.dpi = dpi_scale()
        self.sheet = Image.open(SHEET).convert("RGBA")

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self._build_frames()
        if self.cfg.get("x") is None:
            l, t, r, b = work_area()
            self.cfg["x"], self.cfg["y"] = r - self.canvas_w - int(24 * self.dpi), b - self.canvas_h
        self.x, self.y = int(self.cfg["x"]), int(self.cfg["y"])
        self._clamp_position()
        self.root.geometry(f"{self.canvas_w}x{self.canvas_h}+{self.x}+{self.y}")
        self.root.deiconify()
        self.root.update_idletasks()

        self.hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        self.surface = LayeredSurface(self.hwnd)

        now = time.time()
        self.clip, self.after_wake = None, None
        self._play("hello", now)
        self.greeting_until = now + 3
        self.last_activity = now
        self.mood = "idle"
        self.hovering = False
        self.drag = None
        self.drag_dir, self.drag_moved_at, self.drag_anchor_x = 1, 0.0, 0
        self.sessions = []
        self.next_state_read = 0
        self.next_wander = now + random.uniform(40, 90)
        self.glide = None
        self.last_mouse = (0, 0)
        self.last_mouse_move = 0
        self.next_topmost = 0
        self.hidden_until = 0
        self.cache = {}
        self.last_key = None

        self.font = load_font(int(13 * self.dpi))
        self.menu = self._build_menu()
        self.root.bind("<Enter>", lambda e: self._set_hover(True))
        self.root.bind("<Leave>", lambda e: self._set_hover(False))
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<ButtonRelease-1>", self._drag_end)
        self.root.bind("<Button-3>", self._popup)
        self.root.after(10, self._tick)

    # -- config
    def _load_config(self):
        cfg = dict(DEFAULTS)
        try:
            with open(CONFIG, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
        return cfg

    def _save_config(self):
        self.cfg.update(x=self.x, y=self.y)
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception:
            log_error()

    # -- frames
    def _build_frames(self):
        s = SIZES.get(self.cfg.get("size"), 0.6) * self.dpi
        self.sprite_w, self.sprite_h = int(CELL_W * s), int(CELL_H * s)
        self.bubble_h = int(44 * self.dpi)
        self.canvas_w = max(self.sprite_w + 8, int(280 * self.dpi))
        self.canvas_h = self.sprite_h + self.bubble_h + 8

        def cell(row, col, sx=1.0, sy=1.0):
            box = (col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H)
            size = (int(round(self.sprite_w * sx)), int(round(self.sprite_h * sy)))
            return self.sheet.crop(box).resize(size, Image.LANCZOS)

        self.cells = {}
        for row, durations in ROWS.values():
            for col in range(len(durations)):
                self.cells[(row, col)] = cell(row, col)
        for col in range(6):
            self.cells[(BED, col)] = cell(BED, col)
        # sleeping breath: the chest rises and falls (tiny stretch, anchored at the bottom)
        self.breath = {}
        for col in (3, 4, 5):
            for k in range(BREATH_STEPS):
                wave = math.sin(2 * math.pi * k / BREATH_STEPS)
                self.breath[(col, k)] = cell(BED, col, 1 + 0.008 * wave, 1 + 0.02 * wave)
        self.look = [cell(LOOK_ROWS[i // 8], i % 8) for i in range(16)]
        self.cache = {}
        self.last_key = None

    def _compose(self, key, sprite, bubble):
        if key in self.cache:
            return self.cache[key]
        img = Image.new("RGBA", (self.canvas_w, self.canvas_h), (0, 0, 0, 0))
        img.alpha_composite(sprite, ((self.canvas_w - sprite.width) // 2, self.canvas_h - sprite.height))
        if bubble:
            self._draw_bubble(img, bubble)
        data = to_premultiplied_bgra(img)
        if len(self.cache) > 400:
            self.cache.clear()
        self.cache[key] = data
        return data

    def _draw_bubble(self, img, text):
        d = ImageDraw.Draw(img)
        max_w = self.canvas_w - int(12 * self.dpi)
        while d.textlength(text, font=self.font) > max_w - int(20 * self.dpi) and len(text) > 4:
            text = text[:-2].rstrip() + "…" if not text.endswith("…") else text[:-3].rstrip() + "…"
        tw = int(d.textlength(text, font=self.font))
        pad = int(10 * self.dpi)
        h = int(28 * self.dpi)
        x0 = (self.canvas_w - tw) // 2 - pad
        y0 = int(4 * self.dpi)
        d.rounded_rectangle((x0, y0, x0 + tw + 2 * pad, y0 + h), radius=int(12 * self.dpi),
                            fill=(255, 255, 255, 240), outline=(90, 169, 214, 255), width=max(1, int(2 * self.dpi)))
        cx = self.canvas_w // 2
        t = int(7 * self.dpi)
        d.polygon([(cx - t, y0 + h - 1), (cx + t, y0 + h - 1), (cx, y0 + h + t)], fill=(255, 255, 255, 240))
        d.text((x0 + pad, y0 + h / 2), text, font=self.font, fill=(22, 52, 92, 255), anchor="lm")

    # -- clips (a clip = intro frames played once, then loop frames repeated)
    def _play(self, name, now):
        if name == "sleep":
            intro, loop = SLEEP_INTRO, SLEEP_LOOP
        elif name == "wake":
            intro, loop = WAKE, None
        else:
            row, durations = ROWS[name]
            intro, loop = [], [(row, i, d) for i, d in enumerate(durations)]
        self.clip, self.intro, self.loop = name, intro, loop
        self.in_intro = bool(intro)
        self.pos, self.frame_started = 0, now

    def _advance(self, now):
        while True:
            seq = self.intro if self.in_intro else self.loop
            row, col, ms = seq[self.pos]
            if (now - self.frame_started) * 1000 < ms:
                return row, col
            self.frame_started += ms / 1000
            if now - self.frame_started > 2:  # after a stall, don't spin through frames
                self.frame_started = now
            self.pos += 1
            if self.pos >= len(seq):
                self.pos = 0
                if self.in_intro and self.loop:
                    self.in_intro = False
                elif self.loop is None:  # wake-up finished
                    self._play(self.after_wake or "idle", now)

    # -- what to show
    def _summary(self):
        if not self.sessions:
            return "No Claude sessions right now"
        ordered = sorted(self.sessions, key=lambda s: -PRIORITY[s["phase"]])
        return " · ".join(f"{s['project']}: {session_label(s)}" for s in ordered)

    def _desired(self, now):
        """Returns (clip name or ('look', i), bubble text). Also sets self.mood."""
        if self.glide:
            self.mood = "idle"
            return ("swim_right" if self.glide["dx"] > 0 else "swim_left"), None
        if self.drag:
            self.last_activity = now
            if now - self.drag_moved_at < 0.35:  # you're pulling her: right = dolphin, left = mantas
                return ("swim_right" if self.drag_dir > 0 else "swim_left"), None
        if self.hovering and not self.drag:
            self.last_activity = now
            return "hover", self._summary()

        top = max(self.sessions, key=lambda s: (PRIORITY[s["phase"]], s["ts"]), default=None)
        phase = top["phase"] if top else None
        if phase and phase != "asleep":
            self.last_activity = now
        self.mood = phase or "idle"

        if phase == "call":
            calling = [s for s in self.sessions if s["phase"] == "call"]
            needs_ok = sorted({s["project"] for s in calling if s["kind"] == "needs_you"})
            if needs_ok:
                return "call", ", ".join(needs_ok) + " needs your OK"
            failed = [s["project"] for s in calling if s["kind"] == "failed"]
            if failed:
                return "call", f"{failed[0]} hit an error"
            return "call", ", ".join(sorted({s["project"] for s in calling})) + " is waiting for you"
        if phase == "sigh":
            return "sigh", (f"{top['project']} hit an error" if top["kind"] == "failed" else None)
        if phase in ("working", "hello"):
            return phase, None
        if phase == "asleep":
            return "sleep", None

        # no Claude activity
        if now < self.greeting_until:
            return "hello", None
        if now - self.last_activity > self.cfg["idle_to_sleep_seconds"]:
            self.mood = "asleep"
            return "sleep", None
        look = self._look_index(now)
        if look is not None:
            return ("look", look), None
        return "idle", None

    def _look_index(self, now):
        mx, my = self.root.winfo_pointerxy()
        if (mx, my) != self.last_mouse:
            self.last_mouse, self.last_mouse_move = (mx, my), now
        if now - self.last_mouse_move > 2.5:
            return None
        cx = self.x + self.canvas_w / 2
        cy = self.y + self.canvas_h - self.sprite_h * 0.7
        dx, dy = mx - cx, my - cy
        if math.hypot(dx, dy) > 520 * self.dpi or math.hypot(dx, dy) < 30 * self.dpi:
            return None
        angle = (math.degrees(math.atan2(dx, -dy)) + 360) % 360  # 0 = up, clockwise
        return int(round(angle / 22.5)) % 16

    # -- loop
    def _tick(self):
        try:
            self._step()
        except Exception:
            log_error()
        self.root.after(TICK_MS, self._tick)

    def _step(self):
        now = time.time()
        if now < self.hidden_until:
            return
        if now >= self.next_state_read:
            self.sessions = read_sessions(now, self.cfg)
            self.next_state_read = now + 0.5
        if now >= self.next_topmost:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
            self.next_topmost = now + 5

        self._maybe_wander(now)
        want, bubble = self._desired(now)

        if isinstance(want, tuple):  # looking at your mouse
            self.clip = "look"
            key, sprite = ("look", want[1], bubble), self.look[want[1]]
        else:
            if self.clip == "wake":
                self.after_wake = want
            elif want != self.clip:
                user_action = want in ("hover", "swim_left", "swim_right")
                if self.clip == "sleep" and not user_action:
                    self.after_wake = want
                    self._play("wake", now)
                else:
                    self._play(want, now)
            row, col = self._advance(now)
            if self.clip == "sleep" and not self.in_intro:
                k = int((now % BREATH_SECONDS) / BREATH_SECONDS * BREATH_STEPS)
                key, sprite = (row, col, k, bubble), self.breath[(col, k)]
            else:
                key, sprite = (row, col, None, bubble), self.cells[(row, col)]

        if key != self.last_key:
            self.surface.show(self._compose(key, sprite, bubble), self.canvas_w, self.canvas_h)
            self.last_key = key

    def _maybe_wander(self, now):
        stop = self.hovering or self.drag or self.mood != "idle"
        if self.glide:
            g = self.glide
            step = g["speed"] * (now - g["t"])
            g["t"] = now
            if stop or abs(g["target"] - self.x) <= step:
                if not stop:
                    self.x = int(g["target"])
                self.glide = None
                self.next_wander = now + random.uniform(40, 90)
                self._save_config()
            else:
                self.x += int(math.copysign(max(1, step), g["dx"]))
            self.root.geometry(f"+{self.x}+{self.y}")
            return
        if not self.cfg.get("wander") or stop or now < self.next_wander or self.clip not in ("idle", "look"):
            return
        left, _, right, _ = virtual_screen()
        lo, hi = max(left, self.x - int(350 * self.dpi)), min(right - self.canvas_w, self.x + int(350 * self.dpi))
        if hi - lo < 60:
            self.next_wander = now + 60
            return
        target = random.randint(lo, hi)
        if abs(target - self.x) < 60 * self.dpi:
            self.next_wander = now + 20
            return
        self.glide = {"target": target, "dx": target - self.x, "speed": 90 * self.dpi, "t": now}

    def _clamp_position(self):
        left, top, right, bottom = virtual_screen()
        self.x = min(max(self.x, left - self.canvas_w // 2), right - self.canvas_w // 2)
        self.y = min(max(self.y, top - self.bubble_h), bottom - self.canvas_h // 2)

    # -- mouse
    def _set_hover(self, on):
        self.hovering = on

    def _drag_start(self, e):
        self.glide = None
        self.drag = (e.x_root - self.x, e.y_root - self.y)
        self.drag_anchor_x = e.x_root

    def _drag_move(self, e):
        if self.drag:
            # count a direction only after a few pixels of sideways pull, so wobble doesn't flip her
            dx = e.x_root - self.drag_anchor_x
            if abs(dx) >= 4 * self.dpi:
                self.drag_dir = 1 if dx > 0 else -1
                self.drag_moved_at = time.time()
                self.drag_anchor_x = e.x_root
            self.x, self.y = e.x_root - self.drag[0], e.y_root - self.drag[1]
            self.root.geometry(f"+{self.x}+{self.y}")

    def _drag_end(self, e):
        if self.drag:
            self.drag = None
            self._save_config()

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        self.size_var = tk.StringVar(value=self.cfg.get("size", "medium"))
        for name in ("small", "medium", "large"):
            m.add_radiobutton(label=f"Size: {name}", variable=self.size_var, value=name, command=self._resize)
        self.wander_var = tk.BooleanVar(value=bool(self.cfg.get("wander", True)))
        m.add_checkbutton(label="Swim around when idle", variable=self.wander_var, command=self._toggle_wander)
        m.add_separator()
        m.add_command(label="Hide for 1 hour", command=self._hide_hour)
        m.add_command(label="Quit Sirena", command=self._quit)
        return m

    def _popup(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _resize(self):
        self.cfg["size"] = self.size_var.get()
        bottom, center = self.y + self.canvas_h, self.x + self.canvas_w // 2
        self._build_frames()
        self.x, self.y = center - self.canvas_w // 2, bottom - self.canvas_h
        self.root.geometry(f"{self.canvas_w}x{self.canvas_h}+{self.x}+{self.y}")
        self._save_config()

    def _toggle_wander(self):
        self.cfg["wander"] = bool(self.wander_var.get())
        self.glide = None
        self._save_config()

    def _hide_hour(self):
        self.hidden_until = time.time() + 3600
        self.surface.show(bytes(self.canvas_w * self.canvas_h * 4), self.canvas_w, self.canvas_h)
        self.last_key = None

    def _quit(self):
        self._save_config()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 47823))  # one Sirena at a time
    except OSError:
        sys.exit(0)
    os.makedirs(STATES_DIR, exist_ok=True)
    try:
        Sirena().run()
    except Exception:
        log_error()
        raise


if __name__ == "__main__":
    main()
