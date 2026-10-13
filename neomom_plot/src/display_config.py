# SPDX-License-Identifier: MIT
# Copyright (c) 2026 John Shaeffer (KZ4TS)

# display_config.py
#
# Matplotlib figure sizes, DPI and font sizes for the NeoMOM plot GUI,
# derived from the ONE unified display scale in shared/dpi_scaling.py.
#
# Usage (unchanged — the public API is identical):
#   from display_config import cfg
#   fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi)
#
# WHAT CHANGED
# ------------------------------------------------------------------
# Previously this module computed its own scale from screen resolution
# tiers and a hand-edited WIN_OS_SCALE constant, AND it created a Tk
# root at import time.  Both are gone:
#   * Scale now comes from shared/dpi_scaling.py (real DPI; see that
#     module for the per-OS policy and the NEOMOM_UI_SCALE override).
#   * Sizing is computed LAZILY on first attribute access, so importing
#     this module never creates a Tk root -- which is what let the old
#     version run before enable_hidpi() and defeat Windows DPI
#     awareness.  By the time any cfg.* is read (at plot time) the app
#     root already exists.
#
# Figure sizes are fixed in INCHES; mpl_dpi carries the physical
# enlargement (mpl_dpi = 96 * scale), so font point sizes stay at their
# base values and are NOT also multiplied by the scale (doing both
# double-scaled the old per-tier code).

import os
import sys


# ── Locate shared/dpi_scaling.py (source tree or frozen bundle) ─────────────
def _bootstrap_shared_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (getattr(sys, "_MEIPASS", here), here,
                 os.path.join(here, "..", "..", "shared")):
        if os.path.isdir(cand) and cand not in sys.path:
            sys.path.insert(0, cand)


_bootstrap_shared_path()
from dpi_scaling import DpiScaling


class DisplayConfig:
    """
    Lazily-computed, display-aware matplotlib sizing.

    Public attributes (computed on first access):
        scale
        mpl_dpi
        fig_polar, fig_cart, fig_heatmap, fig_3d          (inches)
        font_title, font_label, font_tick, font_legend, font_annot
        font_3d_title, font_3d_label, font_3d_annot
        lw_plot, lw_minor, lw_grid
    """

    # Base polar-figure edge (inches) at scale 1.0 — the old 1080p tier,
    # so a standard-DPI display looks exactly as it did before.
    _BASE_IN   = 4.5
    _FONT_BASE = 10

    # -- lazy computation -------------------------------------------
    def _compute(self):
        import tkinter as tk
        root = tk._get_default_root()
        temp = None
        if root is None:
            # Standalone use (e.g. the self-test) with no app root yet.
            temp = tk.Tk()
            temp.withdraw()
            root = temp
        # Read the unified scale only; the app owns the Tk root's own
        # point->pixel scaling, so we must NOT re-apply it here.
        ui = DpiScaling(root, apply_tk_scaling=False)
        if temp is not None:
            temp.destroy()

        self.scale   = ui.scale
        self.mpl_dpi = ui.fig_dpi

        p = self._BASE_IN
        self.fig_polar   = (p,        p)
        self.fig_cart    = (p * 1.6,  p * 0.7)
        self.fig_heatmap = (p * 2.2,  p * 0.8)
        self.fig_3d      = (p * 1.1,  p * 1.1)

        f = self._FONT_BASE
        self.font_title    = round(f * 1.1,  1)
        self.font_label    = round(f * 1.0,  1)
        self.font_tick     = round(f * 0.9,  1)
        self.font_legend   = round(f * 0.9,  1)
        self.font_annot    = round(f * 0.85, 1)
        self.font_3d_title = round(f * 1.2,  1)
        self.font_3d_label = round(f * 1.0,  1)
        self.font_3d_annot = round(f * 0.85, 1)

        # Line widths at the base figure size (dpi carries enlargement).
        self.lw_plot  = 1.5
        self.lw_minor = 0.8
        self.lw_grid  = 0.5

        self.__dict__['_ready'] = True

    def _ensure(self):
        if not self.__dict__.get('_ready'):
            self._compute()

    def __getattr__(self, name):
        # Reached only for attributes not yet set. Compute once, retry.
        if name.startswith('_'):
            raise AttributeError(name)
        self._ensure()
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(name)

    # -- diagnostics ------------------------------------------------
    def report(self):
        self._ensure()
        print("=" * 52)
        print("  NeoMOM plot display config")
        print("=" * 52)
        print(f"  scale       : {self.scale:.3f}")
        print(f"  mpl_dpi     : {self.mpl_dpi}")
        print(f"  fig_polar   : {self.fig_polar} in")
        print(f"  fig_cart    : {self.fig_cart} in")
        print(f"  fig_heatmap : {self.fig_heatmap} in")
        print(f"  fig_3d      : {self.fig_3d} in")
        print(f"  font_title  : {self.font_title} pt")
        print(f"  font_label  : {self.font_label} pt")
        print(f"  font_tick   : {self.font_tick} pt")
        print("=" * 52)


# ----------------------------------------------------------------
# Singleton — import this everywhere (unchanged public name).
# ----------------------------------------------------------------
cfg = DisplayConfig()


# ----------------------------------------------------------------
# Self-test:  python3 display_config.py
# ----------------------------------------------------------------
if __name__ == '__main__':
    from dpi_scaling import enable_hidpi
    enable_hidpi()
    cfg.report()
