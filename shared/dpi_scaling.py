# SPDX-License-Identifier: MIT
# Copyright (c) 2026 John Shaeffer (KZ4TS)

# ==============================================================
# dpi_scaling.py
# NeoMOM shared HiDPI / display-scaling support for all Tk GUIs
# (neomom_input, neomom_current, neomom_plot, neomom_Zin)
#
# WHY THIS MODULE EXISTS
# ----------------------------------------------------------------
# Each GUI previously computed its own scale factor, and they did
# not agree:
#   - Scale was picked from screen *resolution* (e.g. width >= 3500
#     -> 2.5x).  Resolution is not DPI: a 32" 4K monitor and a 15"
#     4K laptop share a resolution but differ ~2x in real DPI, so a
#     resolution ladder has to be re-tuned on every machine.
#   - On Windows the apps assumed the OS would scale the window for
#     them.  That is only true when you run `python app.py` from a
#     DPI-aware python.exe.  A PyInstaller-frozen .exe is DPI-UNAWARE
#     by default, so Windows bitmap-stretches the whole window
#     (blurry) above 100% scaling -- and then the app's own font
#     multiplier piled on top of that.
#   - The "fix" was a WIN_OS_SCALE constant the end user had to edit
#     in the source, set inconsistently across the apps (1.0 / 1.5 /
#     2.0), so three viewers rendered a 4K screen three ways.
#
# WHAT THIS MODULE DOES INSTEAD
# ----------------------------------------------------------------
# 1. Declares the process DPI-AWARE on Windows (per-monitor v2),
#    BEFORE any Tk root exists.  Once aware, Windows stops
#    bitmap-stretching and `winfo_fpixels('1i')` returns the TRUE
#    dots-per-inch of the monitor.
# 2. Derives one scale factor from that real DPI -- identical logic
#    on every platform, no resolution ladder, no per-machine knob.
# 3. Sets Tk's point->pixel `scaling` so point-sized fonts
#    (TkDefaultFont, ("Segoe UI", 10), ...) render at the correct
#    physical size automatically.
# 4. Provides helpers to scale raw-pixel dimensions (row heights,
#    padding, window geometry) and to pick the matplotlib figure DPI
#    for embedded plots.
#
# PLATFORM POLICY
# ----------------------------------------------------------------
#   Windows : make the process DPI-aware (above), then scale from the
#             real DPI -- reliable once the process is aware.
#
#   macOS   : Cocoa/Tk handle Retina transparently (points map to
#             backing pixels at the OS backing scale), so we apply
#             NO manual scaling by default (scale = 1.0) and let the
#             OS do its job.  This path is conservative and has not
#             yet been exercised on real hardware; the env override
#             below is the escape hatch if a Mac ever needs nudging.
#
#   Linux   : HYBRID, because automatic DPI on X11 is unreliable --
#             X routinely reports a nominal 96 dpi AND a fabricated
#             physical screen size even on a 4K panel (verified: a
#             3840x2160 / 28" monitor reporting 95.9 dpi and a bogus
#             1017mm width).  So we decide the scale in this order:
#               (a) Desktop scaling the user already set.  Tk reads
#                   Xft.dpi, so winfo_fpixels > ~96 means a scaled
#                   desktop (XFCE "Custom DPI", GNOME/KDE scaling);
#                   trust it.
#               (b) GDK_SCALE / GDK_DPI_SCALE / QT_SCALE_FACTOR in the
#                   session environment (Tk does not honour these, but
#                   they tell us the user's intent).
#               (c) Desktop at default 96 but the panel is physically
#                   high-DPI: read the TRUE physical size from xrandr
#                   (EDID) and scale from that.  This is the case the
#                   resolution ladders were flailing at.
#               (d) Last resort, if even xrandr is unavailable
#                   (Wayland with no xrandr, headless): a coarse
#                   resolution guess, clearly labelled as a guess.
#             NEOMOM_UI_SCALE overrides all of the above.
#
# RUNTIME OVERRIDE (replaces editing the source)
# ----------------------------------------------------------------
#   Set the environment variable  NEOMOM_UI_SCALE  to force a scale
#   factor, e.g.  NEOMOM_UI_SCALE=2.0  ./neomom_input
#   This is the supported way for a user on an oddly-configured
#   display to correct sizing -- no code edit, no rebuild.
#
# TYPICAL USE  (see integration notes at the bottom of this file)
# ----------------------------------------------------------------
#   # at the very top of __main__, before creating any Tk window:
#   from dpi_scaling import enable_hidpi
#   enable_hidpi()
#
#   # after creating the root / inside your App(tk.Tk) __init__:
#   from dpi_scaling import DpiScaling
#   self.ui = DpiScaling(self)          # reads DPI, scales named fonts
#   style.configure("Treeview", rowheight=self.ui.px(28))
#   self.geometry(self.ui.window_geometry(self, 0.6, 0.7,
#                                         min_w=800, min_h=600))
# ==============================================================

from __future__ import annotations

import os
import platform
import sys

# Reference DPI at which scale == 1.0.  96 is the Windows/X11 "100%"
# baseline; 72pt-per-inch is Tk's point definition, used for the
# point->pixel scaling call.
_BASE_DPI = 96.0
_POINTS_PER_INCH = 72.0

# How far above _BASE_DPI a reported DPI must sit before we treat it as
# a deliberately scaled desktop (rather than X's default 96 jitter).
_DPI_EPS = 12.0          # i.e. >= ~108 dpi counts as "scaled"

_ENV_OVERRIDE = "NEOMOM_UI_SCALE"


# --------------------------------------------------------------
# Step 1 -- process DPI awareness (must run before the first Tk root)
# --------------------------------------------------------------
def enable_hidpi() -> str:
    """
    Declare this process DPI-aware so the OS does not bitmap-scale it.

    Call this ONCE, as early as possible in __main__, BEFORE the first
    tkinter.Tk() is created.  Calling it after a root exists is too
    late on Windows and has no effect.

    Returns a short string describing what was applied -- handy for a
    startup log line.  Safe to call on any platform; it is a no-op
    everywhere except Windows.
    """
    if platform.system() != "Windows":
        # Linux: X reports physical pixels already.
        # macOS: Cocoa handles Retina; nothing to declare.
        return "no-op (non-Windows)"

    import ctypes

    # Preferred: Per-Monitor-v2 (Windows 10 1703+).  Correct behaviour
    # when the window is dragged between monitors of different DPI.
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        ctx = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctx):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass

    # Fallback: Per-Monitor aware (Windows 8.1+), via shcore.
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE == 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass

    # Last resort: system-DPI aware (Vista+).  Not per-monitor, but
    # still stops the blurry bitmap stretch on a single-DPI setup.
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system-dpi"
    except (AttributeError, OSError):
        return "unavailable"


# --------------------------------------------------------------
# Step 2 -- the scaling object (one per app, built from the root)
# --------------------------------------------------------------
class DpiScaling:
    """
    Display-scaling facts derived from the REAL monitor DPI.

    Construct it with your Tk root (or any Tk widget) after the root
    exists.  Unless apply_tk_scaling=False, constructing it enlarges
    Tk's standard named fonts by `scale` so the chrome renders at the
    right physical size.

    NOTE on `tk scaling`: on X11 Tk's `tk scaling` value does NOT
    affect font point->pixel conversion at all (that uses the X
    server's Xft.dpi), so setting it leaves default-font widgets tiny
    on a HiDPI panel.  The reliable, cross-platform fix is to resize
    the named fonts directly -- which is what scale_fonts() does, and
    what pt() mirrors for explicit font sizes.

    Attributes
    ----------
    dpi   : float  -- detected dots-per-inch of the screen
    scale : float  -- UI scale factor (1.0 at _BASE_DPI = 96)
    source: str    -- how `scale` was decided ("env", "dpi", "macos")

    Methods
    -------
    px(n)                 -- scale a raw-pixel dimension -> int
    pt(points)            -- scale a font POINT size -> int
    scale_fonts()         -- enlarge Tk's standard named fonts in place
    window_geometry(...)  -- a centered "WxH+X+Y" string in real px
    report()              -- print a summary for tuning on a new box
    fig_dpi               -- matplotlib figure DPI for embedded plots
    """

    # Tk's standard named fonts — resized together so that any widget
    # using a default font scales, not just ones given an explicit font.
    _NAMED_FONTS = (
        "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
        "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
        "TkIconFont", "TkTooltipFont",
    )

    def __init__(self, widget, *, apply_tk_scaling=True,
                 min_scale=1.0, max_scale=4.0):
        self._tk = widget.tk
        self._widget = widget
        self._system = platform.system()
        self.dpi = self._detect_dpi(widget)       # Tk's (often nominal) DPI
        self.real_dpi = None                       # physical, if we find it
        self.scale, self.source = self._decide_scale(min_scale, max_scale)
        # `apply_tk_scaling` kept as the public flag name for callers that
        # only want to READ the scale (e.g. matplotlib sizing) and must not
        # mutate shared Tk font state -- they pass False.
        if apply_tk_scaling:
            self.scale_fonts()
        if os.environ.get("NEOMOM_UI_DEBUG"):
            print(f"[neomom dpi] scale={self.scale:.3f} source={self.source} "
                  f"tk_dpi={self.dpi:.1f} real_dpi={self.real_dpi} "
                  f"frozen={getattr(sys, 'frozen', False)}", file=sys.stderr)

    # -- detection ---------------------------------------------------
    def _detect_dpi(self, widget) -> float:
        """
        Real DPI of the screen.  `winfo_fpixels('1i')` = pixels per
        inch as Tk sees them; once the process is DPI-aware (Windows)
        or on native X11, this is the physical DPI.  Guarded so a
        weird value can never crash startup.
        """
        try:
            dpi = float(widget.winfo_fpixels("1i"))
            if dpi > 0:
                return dpi
        except Exception:
            pass
        return _BASE_DPI

    # -- scale policy ------------------------------------------------
    def _decide_scale(self, lo, hi):
        # 1) explicit env override always wins (no rebuild needed).
        env = os.environ.get(_ENV_OVERRIDE)
        if env:
            try:
                return self._clamp(float(env), lo, hi), "env-override"
            except ValueError:
                pass  # ignore a malformed value, fall through

        # 2) macOS: let Cocoa handle Retina; do not double-scale.
        if self._system == "Darwin":
            return 1.0, "macos (OS-managed)"

        # 3) Windows: process is DPI-aware, so Tk's DPI is the truth.
        if self._system == "Windows":
            return self._clamp(self.dpi / _BASE_DPI, lo, hi), "windows-dpi"

        # 4) Linux / other X11: the hybrid ladder.
        return self._linux_scale(lo, hi)

    # -- Linux hybrid ladder ----------------------------------------
    def _linux_scale(self, lo, hi):
        # (a) Desktop scaling the user set: Tk reads Xft.dpi, so a DPI
        #     meaningfully above 96 means a scaled desktop. Trust it.
        if self.dpi >= _BASE_DPI + _DPI_EPS:
            return self._clamp(self.dpi / _BASE_DPI, lo, hi), "linux-desktop-dpi"

        # (b) Session env hints Tk ignores but which state user intent.
        env_scale = self._gdk_qt_scale()
        if env_scale and env_scale > 1.0:
            return self._clamp(env_scale, lo, hi), "linux-desktop-env"

        # (c) Default-96 desktop on a physically high-DPI panel: read
        #     the true size from xrandr/EDID and scale from that.
        rdpi = self._xrandr_real_dpi()
        if rdpi:
            self.real_dpi = rdpi
            if rdpi >= _BASE_DPI + _DPI_EPS:
                return (self._snap(self._clamp(rdpi / _BASE_DPI, lo, hi)),
                        "linux-physical-dpi")
            return 1.0, "linux-physical-dpi (standard)"

        # (d) No trustworthy signal: coarse resolution guess.
        return self._resolution_fallback(lo, hi)

    def _gdk_qt_scale(self):
        """Combine GDK_SCALE * GDK_DPI_SCALE, or QT_SCALE_FACTOR."""
        def _f(name):
            try:
                return float(os.environ[name])
            except (KeyError, ValueError):
                return None
        gdk = _f("GDK_SCALE")
        if gdk:
            return gdk * (_f("GDK_DPI_SCALE") or 1.0)
        return _f("QT_SCALE_FACTOR")

    def _xrandr_real_dpi(self):
        """
        True DPI from the active output's EDID physical size, via
        `xrandr --query`. Best-effort: returns None if xrandr is
        missing, times out, or the line can't be parsed (e.g. Wayland
        with no XWayland).

        A PyInstaller-frozen app runs with LD_LIBRARY_PATH pointed at
        its own bundled libraries; the system `xrandr` must NOT inherit
        that or it can fail to load system libs. PyInstaller saves the
        original in LD_LIBRARY_PATH_ORIG -- restore it (or drop the var)
        for the child so xrandr runs against the system environment.
        """
        import re
        import subprocess
        env = dict(os.environ)
        orig = env.get("LD_LIBRARY_PATH_ORIG")
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        elif getattr(sys, "frozen", False):
            env.pop("LD_LIBRARY_PATH", None)
        try:
            out = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True, text=True, timeout=2, env=env).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            m = re.match(r"^\S+ connected.* (\d+)mm x (\d+)mm", line)
            if not m:
                continue
            mm_w = int(m.group(1))
            g = re.search(r"\b(\d+)x(\d+)\+\d+\+\d+", line)
            if not mm_w or not g:
                return None
            return int(g.group(1)) / (mm_w / 25.4)
        return None

    def _resolution_fallback(self, lo, hi):
        """Last-resort guess from raw pixel width. Clearly labelled."""
        try:
            sw = self._widget.winfo_screenwidth()
        except Exception:
            sw = 0
        if sw >= 3400:
            scale = 1.5      # 4K-ish, physical size unknown
        elif sw >= 2400:
            scale = 1.25     # 1440p-ish
        else:
            scale = 1.0
        return self._clamp(scale, lo, hi), "linux-resolution-guess"

    @staticmethod
    def _snap(v):
        """Round to the nearest 0.05 so scales read cleanly (1.69->1.70)."""
        return round(round(v / 0.05) * 0.05, 2)

    @staticmethod
    def _clamp(v, lo, hi):
        if lo is not None:
            v = max(v, lo)
        if hi is not None:
            v = min(v, hi)
        return v

    # -- apply to Tk -------------------------------------------------
    def scale_fonts(self):
        """
        Enlarge Tk's standard named fonts by `scale`, in place.

        This is the enlargement that actually works on X11, where
        `tk scaling` does not touch fonts.  Every widget that uses a
        default font (most of them) picks up the new size immediately,
        because named fonts are live and shared.  Idempotent per root.
        A no-op when scale == 1.0 (e.g. macOS, or a standard display).
        """
        if self.scale == 1.0:
            return
        if getattr(self._widget, "_neomom_fonts_scaled", False):
            return
        import tkinter.font as tkfont
        for name in self._NAMED_FONTS:
            try:
                f = tkfont.nametofont(name, root=self._widget)
            except Exception:
                continue
            size = f.cget("size")
            if not size:
                continue
            # size > 0 is points, < 0 is pixels; scale the magnitude,
            # keep the sign.
            scaled = int(round(abs(size) * self.scale))
            f.configure(size=scaled if size > 0 else -scaled)
        try:
            self._widget._neomom_fonts_scaled = True
        except Exception:
            pass

    # -- helpers for widget code ------------------------------------
    def px(self, n) -> int:
        """Scale a RAW-PIXEL dimension (row height, pad, canvas size)."""
        return int(round(n * self.scale))

    def pt(self, points) -> int:
        """
        Scale a font POINT size.  Use at any call site that specifies
        an explicit font size, e.g. `font=("TkDefaultFont", ui.pt(10))`.
        Mirrors scale_fonts() (which handles the default-font widgets),
        because on X11 nothing else enlarges fonts.
        """
        return max(1, int(round(points * self.scale)))

    @property
    def fig_dpi(self) -> int:
        """
        DPI for an embedded matplotlib Figure so that a figure sized
        in inches is physically that many inches on screen.  With the
        process DPI-aware, this is just the real screen DPI; on macOS
        (scale 1.0) it collapses to the 96 baseline and Cocoa handles
        the Retina doubling.
        """
        return int(round(_BASE_DPI * self.scale))

    def window_geometry(self, widget, frac_w, frac_h,
                        min_w=0, min_h=0, center=False) -> str:
        """
        A Tk geometry string sized as a fraction of the screen (capped
        to the screen so the window never exceeds it) -- replaces
        hardcoded "600x475" / "1200x800" literals so one call fits
        1080p, 1440p and 4K.

        Returns SIZE ONLY ("WxH") by default and lets the window
        manager place the window.  That is the safe, conventional
        choice: an explicit "+x+y" position can land the title bar
        off-screen on some multi-monitor / panel / WM setups, leaving
        the window with no reachable title-bar buttons and unable to
        move.  Pass center=True only when you specifically want a
        centered position and know the display layout is simple.
        """
        sw = widget.winfo_screenwidth()
        sh = widget.winfo_screenheight()
        # Cap to the screen (small margins keep panels/title bar clear).
        w = min(max(int(sw * frac_w), int(min_w)), max(sw - 40, 200))
        h = min(max(int(sh * frac_h), int(min_h)), max(sh - 80, 200))
        if not center:
            return f"{w}x{h}"
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2, 0)
        return f"{w}x{h}+{x}+{y}"

    # -- diagnostics -------------------------------------------------
    def report(self):
        """Print a summary; run an app with this to tune a new display."""
        print("=" * 52)
        print("  NeoMOM display scaling")
        print("=" * 52)
        print(f"  platform        : {self._system}")
        print(f"  Tk-reported DPI : {self.dpi:.1f}")
        if self.real_dpi:
            print(f"  physical DPI    : {self.real_dpi:.1f}  (xrandr/EDID)")
        print(f"  scale factor    : {self.scale:.3f}  (source: {self.source})")
        print(f"  named fonts     : x{self.scale:.2f} (via scale_fonts)")
        print(f"  matplotlib dpi  : {self.fig_dpi}")
        print(f"  env override    : {_ENV_OVERRIDE}="
              f"{os.environ.get(_ENV_OVERRIDE, '(unset)')}")
        print("=" * 52)


# --------------------------------------------------------------
# Self-test:  python3 dpi_scaling.py
# --------------------------------------------------------------
if __name__ == "__main__":
    import tkinter as tk

    enable_hidpi()
    _root = tk.Tk()
    _root.withdraw()
    DpiScaling(_root).report()
    _root.destroy()
    sys.exit(0)


# ==============================================================
# INTEGRATION NOTES  (these become the first punch-list items)
# ==============================================================
# This module is intentionally dependency-free (stdlib + tkinter).
# To make the four frozen apps import it, the build has to ship it
# in each app's src set.  Two options:
#
#   A. Canonical copy here in shared/, added to every PyInstaller
#      .spec:  put SHARED = os.path.join(SPECPATH,'..','..','shared')
#      on pathex and append (os.path.join(SHARED,'dpi_scaling.py'),
#      '.') to the datas list.  One source of truth; specs change.
#
#   B. A tiny sync step (Makefile / copy_windows.bat) that copies
#      this file into each */src/ before building.  Specs stay as-is
#      (they already glob src/*.py); the repo keeps one real copy and
#      the copies are git-ignored.
#
# Either way, REMOVE the per-app scale ladders and the WIN_OS_SCALE
# constants in neomom_input.py, neomom_current.py, neomom_Zin.py and
# neomom_plot/display_config.py, and replace them with calls to this
# module.  display_config.py can keep its figure-size tiers but should
# take dpi/scale from here instead of its own resolution test.
# ==============================================================
