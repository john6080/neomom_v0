# display_config.py
#
# Purpose: Detect monitor resolution and UI scaling, then compute
# matplotlib figure sizes and font sizes that fill the screen well.
#
# Usage:
#   from display_config import cfg
#   fig, ax = plt.subplots(figsize=cfg.fig_polar)
#
# All other modules import the singleton `cfg` — do not instantiate
# DisplayConfig directly.
#
# Tuning guide (Linux):
#   Run:  python3 display_config.py
#   Adjust FONT_BASE for your resolution tier until text is readable.
#   FIG_POLAR_IN and MPL_DPI control plot window physical size.
#   Fonts are INDEPENDENT of figure size — tuned separately.

import platform
import tkinter as tk


class DisplayConfig:
    """
    Computes display-aware sizing on first import.

    Figure size and font size are set INDEPENDENTLY by resolution tier.
    Reducing figure size does NOT shrink fonts.

    Linux tiers (detected from screen resolution):
        1080p : FIG_POLAR_IN=4.5  MPL_DPI=100  FONT_BASE=10
        1440p : FIG_POLAR_IN=5.5  MPL_DPI=120  FONT_BASE=11
        4K    : FIG_POLAR_IN=6.0  MPL_DPI=200  FONT_BASE=10

    Windows: uses WIN_POLAR_SCALE / WIN_3D_SCALE multipliers.
    Font base is tuned independently per tier.

    Single tuning knob per tier:
        FONT_BASE  — increase/decrease by 1pt for all fonts together
    """

    WIN_POLAR_SCALE = 0.5
    WIN_3D_SCALE    = 0.5

    def __init__(self):
        self._detect_screen()
        self._compute_sizes()

    def _detect_screen(self):
        """Record screen size; set FIG_POLAR_IN, MPL_DPI, FONT_BASE by tier."""
        root = tk.Tk()
        root.withdraw()
        self.screen_w_px = root.winfo_screenwidth()
        self.screen_h_px = root.winfo_screenheight()
        self.logical_w   = self.screen_w_px
        self.logical_h   = self.screen_h_px

        sw = self.screen_w_px
        sh = self.screen_h_px

        if platform.system() == 'Windows':
            # ----------------------------------------------------------------
            # Windows HiDPI workaround
            #
            # Python/tkinter runs DPI-unaware by default on Windows, so both
            # winfo_screenwidth() and ctypes DPI calls return LOGICAL pixels
            # (physical / OS_scale).  On a 4K monitor at 200% scaling:
            #   logical resolution = 1920x1080  (same as a real 1080p monitor)
            #   physical resolution = 3840x2160
            #
            # matplotlib is also DPI-unaware, so the OS doubles all figure
            # dimensions AND font sizes when rendering to the physical display.
            #
            # Solution: set WIN_OS_SCALE below to match your Windows display
            # scaling setting (Settings > Display > Scale):
            #   100% scaling  →  WIN_OS_SCALE = 1.0  (no correction needed)
            #   125% scaling  →  WIN_OS_SCALE = 1.25
            #   150% scaling  →  WIN_OS_SCALE = 1.5
            #   200% scaling  →  WIN_OS_SCALE = 2.0  ← 4K monitor typical
            # ----------------------------------------------------------------
            WIN_OS_SCALE = 1.5  # ← SET THIS to your Windows display scaling

            self._win_dpi_scale = WIN_OS_SCALE
            self.FIG_POLAR_IN   = 6.0
            self.MPL_DPI        = 200
            self.FONT_BASE      = 10  # divided by WIN_OS_SCALE in _compute_sizes

        else:
            self._win_dpi_scale = 1.0

            if sw >= 3500 and sh >= 2000:
                # 4K (~3840x2160) at 200% Ubuntu scaling
                # Figure: 6.0in x 200dpi = 1200px (OS doubles to 2400px)
                # Font: 10pt base — keeps text readable without being huge
                self.FIG_POLAR_IN = 6.0
                self.MPL_DPI      = 200
                self.FONT_BASE    = 10   # ← tune for 4K font size

            elif sw >= 2500 and sh >= 1400:
                # 1440p (~2560x1440)
                self.FIG_POLAR_IN = 5.5
                self.MPL_DPI      = 120
                self.FONT_BASE    = 11   # ← tune for 1440p font size

            else:
                # 1080p (~1920x1080) — default
                self.FIG_POLAR_IN = 4.5
                self.MPL_DPI      = 100
                self.FONT_BASE    = 10   # ← tune for 1080p font size

        root.destroy()

    def _compute_sizes(self):
        """
        Derive all figure and font sizes.

        Figure sizes cascade from FIG_POLAR_IN and MPL_DPI.
        Font sizes cascade from FONT_BASE — independent of figure size.
        """
        p = self.FIG_POLAR_IN
        f = self.FONT_BASE

        if platform.system() == 'Windows':
            _pp   = p * self.WIN_POLAR_SCALE
            _3d_p = p * 1.1 * self.WIN_3D_SCALE
            if self._win_dpi_scale > 1.0:
                self.mpl_dpi = round(self.MPL_DPI / self._win_dpi_scale)
                # Divide font sizes by OS scale too — Windows doubles
                # matplotlib font sizes at high DPI just like figure sizes.
                f = round(f / self._win_dpi_scale, 2)
            else:
                self.mpl_dpi = self.MPL_DPI
        else:
            _pp          = p
            _3d_p        = p * 1.1
            self.mpl_dpi = self.MPL_DPI

        # ── Figure sizes (width, height) in inches ──────────────────────
        self.fig_polar   = (_pp,         _pp)
        self.fig_cart    = (_pp * 1.6,   _pp * 0.7)
        self.fig_heatmap = (_pp * 2.2,   _pp * 0.8)
        self.fig_3d      = (_3d_p,       _3d_p)

        # ── Font sizes — from FONT_BASE, NOT figure size ─────────────────
        # Changing figure size will NOT change font sizes.
        # On Windows, f is pre-divided by _win_dpi_scale above so OS
        # doubling restores it to the intended size.
        # Tune FONT_BASE in _detect_screen() for your monitor.
        self.font_title  = round(f * 1.1, 1)
        self.font_label  = round(f * 1.0, 1)
        self.font_tick   = round(f * 0.9, 1)
        self.font_legend = round(f * 0.9, 1)
        self.font_annot  = round(f * 0.85, 1)

        # 3D fonts — same base, slightly larger title
        self.font_3d_title = round(f * 1.2, 1)
        self.font_3d_label = round(f * 1.0, 1)
        self.font_3d_annot = round(f * 0.85, 1)

        # ── Line widths — still tied to figure size ──────────────────────
        _lw = _pp / (self.FIG_POLAR_IN *
                     (self.WIN_POLAR_SCALE if platform.system() == 'Windows' else 1.0))
        self.lw_plot  = max(round(1.5 * _lw, 2), 0.4)
        self.lw_minor = max(round(0.8 * _lw, 2), 0.2)
        self.lw_grid  = max(round(0.5 * _lw, 2), 0.2)

    def report(self):
        """Print a summary — useful for tuning on a new monitor."""
        def fmt(t): return f"({t[0]:.2f}, {t[1]:.2f})"
        def px(t):
            w = round(t[0] * self.mpl_dpi)
            h = round(t[1] * self.mpl_dpi)
            return f"{w}x{h}px"
        print(f"\n{'='*50}")
        print(f"  Display Configuration")
        print(f"{'='*50}")
        print(f"  Screen (tkinter)  : {self.screen_w_px} x {self.screen_h_px} px")
        print(f"  Platform          : {platform.system()}")
        print(f"  Windows DPI scale : {self._win_dpi_scale:.2f}x  (1.0 on Linux/Mac)")
        print(f"  FIG_POLAR_IN      : {self.FIG_POLAR_IN} in")
        print(f"  FONT_BASE         : {self.FONT_BASE} pt  (tune per tier in _detect_screen)")
        print(f"  MPL_DPI (base)    : {self.MPL_DPI}")
        print(f"  mpl_dpi (actual)  : {self.mpl_dpi}")
        print(f"  fig_polar         : {fmt(self.fig_polar)} in  →  {px(self.fig_polar)}")
        print(f"  fig_cart          : {fmt(self.fig_cart)} in  →  {px(self.fig_cart)}")
        print(f"  fig_heatmap       : {fmt(self.fig_heatmap)} in  →  {px(self.fig_heatmap)}")
        print(f"  fig_3d            : {fmt(self.fig_3d)} in  →  {px(self.fig_3d)}")
        eff = self._win_dpi_scale if platform.system() == 'Windows' else 1.0
        print(f"  font_title        : {self.font_title} pt  "
              f"(effective on screen: {self.font_title*eff:.1f} pt)")
        print(f"  font_label        : {self.font_label} pt  "
              f"(effective on screen: {self.font_label*eff:.1f} pt)")
        print(f"  font_tick         : {self.font_tick} pt  "
              f"(effective on screen: {self.font_tick*eff:.1f} pt)")
        print(f"  font_3d_title     : {self.font_3d_title} pt  "
              f"(effective on screen: {self.font_3d_title*eff:.1f} pt)")
        print(f"  font_3d_label     : {self.font_3d_label} pt  "
              f"(effective on screen: {self.font_3d_label*eff:.1f} pt)")
        print(f"{'='*50}\n")
        print(f"  Tuning: adjust FONT_BASE in _detect_screen() for your tier.")
        print(f"  Current FONT_BASE = {self.FONT_BASE} pt")
        print(f"  Run cfg.report() after each change to verify.\n")


# ----------------------------------------------------------------
# Singleton — import this everywhere
# ----------------------------------------------------------------
cfg = DisplayConfig()


# ----------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------
if __name__ == '__main__':
    cfg.report()