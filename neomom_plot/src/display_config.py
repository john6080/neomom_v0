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

import platform
import tkinter as tk


class DisplayConfig:
    """
    Computes display-aware sizing on first import.

    Figure size and font size are set INDEPENDENTLY by resolution tier.
    Reducing figure size no longer shrinks fonts.

    Linux tiers (set in _detect_screen):
        1080p : FIG_POLAR_IN=4.5, MPL_DPI=100, FONT_BASE=10
        1440p : FIG_POLAR_IN=5.5, MPL_DPI=120, FONT_BASE=11
        4K    : FIG_POLAR_IN=6.0, MPL_DPI=200, FONT_BASE=14

    Tune FONT_BASE up/down by 1pt increments for your monitor.
    """

    WIN_POLAR_SCALE = 0.5
    WIN_3D_SCALE    = 0.5

    def __init__(self):
        self._detect_screen()
        self._compute_sizes()

    def _detect_screen(self):
        root = tk.Tk()
        root.withdraw()
        self.screen_w_px = root.winfo_screenwidth()
        self.screen_h_px = root.winfo_screenheight()
        self.logical_w   = self.screen_w_px
        self.logical_h   = self.screen_h_px

        sw = self.screen_w_px
        sh = self.screen_h_px

        if platform.system() == 'Windows':
            self.FIG_POLAR_IN = 6.0
            self.MPL_DPI      = 200
            self.FONT_BASE    = 14
            try:
                actual_dpi = root.winfo_fpixels('1i')
                self._win_dpi_scale = actual_dpi / 96.0
            except Exception:
                self._win_dpi_scale = 1.0

        else:
            self._win_dpi_scale = 1.0

            if sw >= 3500 and sh >= 2000:
                # 4K (~3840x2160)
                self.FIG_POLAR_IN = 6.0
                self.MPL_DPI      = 200
                self.FONT_BASE    = 14

            elif sw >= 2500 and sh >= 1400:
                # 1440p (~2560x1440)
                self.FIG_POLAR_IN = 5.5
                self.MPL_DPI      = 120
                self.FONT_BASE    = 11

            else:
                # 1080p (~1920x1080)
                self.FIG_POLAR_IN = 4.5
                self.MPL_DPI      = 100
                self.FONT_BASE    = 10   # ← tune this for 1080p font size

        root.destroy()

    def _compute_sizes(self):
        p = self.FIG_POLAR_IN
        f = self.FONT_BASE        # font base — independent of figure size

        if platform.system() == 'Windows':
            _pp   = p * self.WIN_POLAR_SCALE
            _3d_p = p * 1.1 * self.WIN_3D_SCALE
            if self._win_dpi_scale > 1.0:
                self.mpl_dpi = round(self.MPL_DPI / self._win_dpi_scale)
            else:
                self.mpl_dpi = self.MPL_DPI
        else:
            _pp          = p
            _3d_p        = p * 1.1
            self.mpl_dpi = self.MPL_DPI

        # Figure sizes (width, height) in inches
        self.fig_polar   = (_pp,         _pp)
        self.fig_cart    = (_pp * 1.6,   _pp * 0.7)
        self.fig_heatmap = (_pp * 2.2,   _pp * 0.8)
        self.fig_3d      = (_3d_p,       _3d_p)

        # --------------------------------------------------------------
        # Font sizes — derived from FONT_BASE, NOT from figure size.
        # This means fonts stay readable even when figures are smaller.
        # --------------------------------------------------------------
        self.font_title  = round(f * 1.1, 1)   # slightly larger than base
        self.font_label  = round(f * 1.0, 1)   # base size
        self.font_tick   = round(f * 0.9, 1)   # slightly smaller
        self.font_legend = round(f * 0.9, 1)
        self.font_annot  = round(f * 0.85, 1)

        # 3D fonts — same base, slightly larger title
        self.font_3d_title = round(f * 1.2, 1)
        self.font_3d_label = round(f * 1.0, 1)
        self.font_3d_annot = round(f * 0.85, 1)

        # Line widths — still tied to figure size
        self.lw_plot  = max(round(1.5 * (_pp / 4.5), 2), 0.4)
        self.lw_minor = max(round(0.8 * (_pp / 4.5), 2), 0.2)
        self.lw_grid  = max(round(0.5 * (_pp / 4.5), 2), 0.2)

    def report(self):
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
        print(f"  FONT_BASE         : {self.FONT_BASE} pt")
        print(f"  MPL_DPI (base)    : {self.MPL_DPI}")
        print(f"  mpl_dpi (actual)  : {self.mpl_dpi}")
        print(f"  fig_polar         : {fmt(self.fig_polar)} in  →  {px(self.fig_polar)}")
        print(f"  fig_cart          : {fmt(self.fig_cart)} in  →  {px(self.fig_cart)}")
        print(f"  fig_heatmap       : {fmt(self.fig_heatmap)} in  →  {px(self.fig_heatmap)}")
        print(f"  fig_3d            : {fmt(self.fig_3d)} in  →  {px(self.fig_3d)}")
        print(f"  font_title        : {self.font_title} pt")
        print(f"  font_label        : {self.font_label} pt")
        print(f"  font_tick         : {self.font_tick} pt")
        print(f"  font_3d_title     : {self.font_3d_title} pt")
        print(f"{'='*50}\n")


# ----------------------------------------------------------------
# Singleton — import this everywhere
# ----------------------------------------------------------------
cfg = DisplayConfig()


# ----------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------
if __name__ == '__main__':
    cfg.report()