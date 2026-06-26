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

    Attributes (all public, read-only by convention)
    ----------
    screen_w_px, screen_h_px : int
        Raw screen resolution in pixels.
    scale_factor : float
        OS UI scaling factor (e.g. 2.0 for 200%).
        Set explicitly here for Ubuntu/TkAgg which doesn't
        reliably auto-report HiDPI scaling.
    logical_w, logical_h : int
        Effective desktop size in logical pixels
        (physical / scale_factor).
    mpl_dpi : int
        DPI passed to matplotlib figures.  On HiDPI screens we
        use a higher DPI so figures are physically larger.

    Figure sizes (width, height) in inches for plt.subplots():
    ----------------------------------------------------------
    fig_polar   : square polar plot  (elevation or azimuth)
    fig_cart    : rectangular Cartesian plot
    fig_heatmap : wide heatmap
    fig_3d      : square-ish 3D surface plot

    Font sizes (points):
    --------------------
    font_title, font_label, font_tick, font_legend, font_annot
    """

    # ----------------------------------------------------------------
    # Direct sizing for 4K monitor at Ubuntu 200% scaling.
    # Tune FIG_POLAR_IN and MPL_DPI to taste — everything else
    # cascades from these two values.
    #
    # FIG_POLAR_IN : side length in inches for polar plots
    # MPL_DPI      : dots per inch — higher = larger physical window
    #
    # At 200% Ubuntu scaling, the window manager doubles everything,
    # so a 7-inch figure at 100 DPI appears as a 700px window which
    # the OS then scales to 1400px on screen — filling roughly
    # half a 4K display width.  Adjust up/down in steps of 0.5.
    # ----------------------------------------------------------------
    FIG_POLAR_IN = 6.0    # inches — tune this
    MPL_DPI      = 200    # DPI   — tune this
    WIN_POLAR_SCALE = 0.5  # size multiplier for polar/cart/heatmap windows on Windows
    WIN_3D_SCALE   = 0.5   # size multiplier for 3D windows on Windows

    def __init__(self):
        self._detect_screen()
        self._compute_sizes()

    def _detect_screen(self):
        """Record physical screen size and Windows DPI scale factor."""
        root = tk.Tk()
        root.withdraw()
        self.screen_w_px = root.winfo_screenwidth()
        self.screen_h_px = root.winfo_screenheight()
        self.logical_w   = self.screen_w_px
        self.logical_h   = self.screen_h_px

        # On Windows, detect the actual DPI scale factor so _compute_sizes()
        # can divide out the OS upscaling that would otherwise double the window.
        # winfo_fpixels('1i') returns actual pixels per inch; 96 = 100% scaling.
        self._win_dpi_scale = 1.0
        if platform.system() == 'Windows':
            try:
                actual_dpi = root.winfo_fpixels('1i')
                self._win_dpi_scale = actual_dpi / 96.0
            except Exception:
                self._win_dpi_scale = 1.0

        root.destroy()

    def _compute_sizes(self):
        """
        Derive all figure sizes from FIG_POLAR_IN.
        Cartesian is wider/shorter, heatmap full-width, 3D slightly larger.
        """
        p = self.FIG_POLAR_IN
        # Polar/cart/heatmap — apply WIN_POLAR_SCALE on Windows
        _pp = p * self.WIN_POLAR_SCALE if platform.system() == 'Windows' else p
        self.fig_polar   = (_pp,          _pp)
        self.fig_cart    = (_pp * 1.6,    _pp * 0.7)
        self.fig_heatmap = (_pp * 2.2,    _pp * 0.8)
        # 3D windows need an additional size reduction on Windows because
        # the forced wm_geometry interacts differently with the OS DPI scale.
        _3d_p = p * 1.1
        if platform.system() == 'Windows':
            _3d_p *= self.WIN_3D_SCALE
        self.fig_3d      = (_3d_p,      _3d_p)
        # On Windows, the OS applies its DPI scale factor on top of
        # matplotlib's own sizing, which would make every window too large.
        # Divide MPL_DPI by the detected scale so the OS upscale brings it
        # back to the intended physical size.  Works for 100 / 125 / 150 / 200%.
        if platform.system() == 'Windows' and self._win_dpi_scale > 1.0:
            self.mpl_dpi = round(self.MPL_DPI / self._win_dpi_scale)
        else:
            self.mpl_dpi = self.MPL_DPI

        # Polar/cart font sizes — scale with _pp so fonts shrink with window.
        # Floors prevent values so small that matplotlib ignores them.
        _sp = _pp / 7.0
        self.font_title  = max(round(10 * _sp, 1), 6.0)
        self.font_label  = max(round(9  * _sp, 1), 5.5)
        self.font_tick   = max(round(8  * _sp, 1), 5.0)
        self.font_legend = max(round(9  * _sp, 1), 5.5)
        self.font_annot  = max(round(8  * _sp, 1), 5.0)

        # Line widths — scale with _pp so they thin down with the window
        _lw = _pp / self.FIG_POLAR_IN   # 1.0 on Linux, WIN_POLAR_SCALE on Windows
        self.lw_plot  = max(round(1.5 * _lw, 2), 0.4)  # main pattern lines
        self.lw_minor = max(round(0.8 * _lw, 2), 0.2)  # minor tick marks
        self.lw_grid  = max(round(0.5 * _lw, 2), 0.2)  # polar grid rings

        # 3D-specific font sizes — scale with _3d_p so they shrink with the
        # window on Windows.  A floor prevents unreadably tiny text.
        _s3d = _3d_p / 7.0
        self.font_3d_title = max(round(11 * _s3d, 1), 6.0)
        self.font_3d_label = max(round(10 * _s3d, 1), 5.5)
        self.font_3d_annot = max(round( 8 * _s3d, 1), 5.0)

    def report(self):
        """Print a summary — useful for tuning on a new machine."""
        def fmt(t): return f"({t[0]:.2f}, {t[1]:.2f})"
        print(f"\n{'='*50}")
        print(f"  Display Configuration")
        print(f"{'='*50}")
        print(f"  Screen (tkinter)  : {self.screen_w_px} x {self.screen_h_px} px")
        print(f"  Windows DPI scale : {self._win_dpi_scale:.2f}x  (1.0 on Linux/Mac)")
        print(f"  FIG_POLAR_IN      : {self.FIG_POLAR_IN} in  (tune this)")
        print(f"  matplotlib DPI    : {self.mpl_dpi}      (tune this)")
        print(f"  WIN_POLAR_SCALE   : {self.WIN_POLAR_SCALE}     (Windows polar/cart window scale, tune this)")
        print(f"  WIN_3D_SCALE      : {self.WIN_3D_SCALE}     (Windows 3D window scale, tune this)")
        print(f"  fig_polar         : {fmt(self.fig_polar)} in")
        print(f"  fig_cart          : {fmt(self.fig_cart)} in")
        print(f"  fig_heatmap       : {fmt(self.fig_heatmap)} in")
        print(f"  fig_3d            : {fmt(self.fig_3d)} in")
        print(f"  font_title        : {self.font_title} pt")
        print(f"  font_tick         : {self.font_tick} pt")
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