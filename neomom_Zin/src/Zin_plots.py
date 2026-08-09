# Zin_plots.py
#
# Purpose: Plot functions for impedance sweep datasets.
#
# All functions accept a list of SweepData objects so any number
# of datasets can be overlaid on the same axes.
#
# Functions:
#   plot_RX   -- R and X vs frequency
#   plot_GB   -- G and B vs frequency (B zero crossing = resonance)
#   plot_SWR  -- SWR vs frequency at user-selected Z0

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from ham_bands   import overlay_bands
from Zin_reader  import compute_swr, _find_zero_crossing

# ------------------------------------------------------------------
# Style constants
# ------------------------------------------------------------------
COL_RES = '#ff7f0e'   # orange — resonance marker
COL_REF = '#888888'   # grey   — reference lines
LW      = 1.8         # main curve linewidth
LW_REF  = 0.8         # reference line
LW_RES  = 1.2         # resonance marker


# ------------------------------------------------------------------
# plot_RX
# ------------------------------------------------------------------
def plot_RX(ax, datasets, show_bands=True):
    """
    Plot Rin (solid) and Xin (dashed) vs frequency for all datasets.

    Each dataset uses its own colour; Xin uses the same colour
    with dashed line style for visual pairing.
    """
    for ds in datasets:
        if not ds.visible:
            continue
        ax.plot(ds.freq_mhz, ds.Rin,
                color=ds.color, lw=LW, linestyle=ds.linestyle,
                label=f'{ds.name}  R$_{{in}}$')
        ax.plot(ds.freq_mhz, ds.Xin,
                color=ds.color, lw=LW, linestyle='--',
                label=f'{ds.name}  X$_{{in}}$', alpha=0.75)

    ax.axhline(0, color=COL_REF, lw=LW_REF, linestyle=':')
    _add_resonance_markers(ax, datasets)

    if show_bands:
        _overlay_bands_auto(ax, datasets)

    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('Impedance [Ω]')
    ax.set_title(_make_title(datasets, 'Impedance vs Frequency'))
    ax.legend(loc='upper right', framealpha=0.85, fontsize=8)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    _set_freq_limits(ax, datasets)


# ------------------------------------------------------------------
# plot_GB
# ------------------------------------------------------------------
def plot_GB(ax, datasets, show_bands=True):
    """
    Plot Gin (solid) and Bin (dashed) vs frequency for all datasets.

    Bin zero crossing marks resonance — key MoM validation diagnostic.
    Values shown in milli-Siemens.
    """
    for ds in datasets:
        if not ds.visible:
            continue
        Gin_ms = ds.Gin * 1000.0
        Bin_ms = ds.Bin * 1000.0

        ax.plot(ds.freq_mhz, Gin_ms,
                color=ds.color, lw=LW, linestyle=ds.linestyle,
                label=f'{ds.name}  G$_{{in}}$')
        ax.plot(ds.freq_mhz, Bin_ms,
                color=ds.color, lw=LW, linestyle='--',
                label=f'{ds.name}  B$_{{in}}$', alpha=0.75)

        # Gin peak annotation — one per dataset
        idx_peak  = int(np.argmax(Gin_ms))
        f_peak    = float(ds.freq_mhz[idx_peak])
        Gin_peak  = float(Gin_ms[idx_peak])
        Rin_peak  = 1000.0 / Gin_peak if Gin_peak > 0 else 0.0
        ax.plot(f_peak, Gin_peak, 'o', color=ds.color, ms=5, zorder=6)
        ax.annotate(
            f'{ds.name}\nG peak={Gin_peak:.3f} mS\nR$_{{in}}$=1/G={Rin_peak:.1f} Ω',
            xy=(f_peak, Gin_peak),
            xytext=(0.03, 0.90 - datasets.index(ds) * 0.18),
            textcoords='axes fraction', fontsize=7,
            color=ds.color,
            bbox=dict(boxstyle='round,pad=0.3', fc='white',
                      ec=ds.color, alpha=0.85),
            arrowprops=dict(arrowstyle='->', color=ds.color, lw=0.8)
        )

    ax.axhline(0, color=COL_REF, lw=LW_REF, linestyle=':')
    _add_resonance_markers(ax, datasets)

    if show_bands:
        _overlay_bands_auto(ax, datasets)

    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('Admittance [mS]')
    ax.set_title(_make_title(datasets, 'Admittance vs Frequency'))
    ax.legend(loc='upper right', framealpha=0.85, fontsize=8)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    _set_freq_limits(ax, datasets)


# ------------------------------------------------------------------
# plot_SWR
# ------------------------------------------------------------------
def plot_SWR(ax, datasets, show_bands=True, Z0=50.0):
    """
    Plot SWR vs frequency for all datasets at reference impedance Z0.

    SWR is computed from Rin/Xin — not from any pre-stored SWR column.
    """
    SWR_MAX = 20.0

    for ds in datasets:
        if not ds.visible:
            continue
        swr = np.clip(ds.swr(Z0), 1.0, SWR_MAX)
        ax.plot(ds.freq_mhz, swr,
                color=ds.color, lw=LW, linestyle=ds.linestyle,
                label=ds.name)

        # SWR minimum annotation per dataset
        idx_min = int(np.argmin(swr))
        swr_min = float(swr[idx_min])
        f_min   = float(ds.freq_mhz[idx_min])
        y_off   = 0.85 - datasets.index(ds) * 0.18
        ax.annotate(
            f'{ds.name}\nSWR min={swr_min:.2f}\n@ {f_min:.4f} MHz\nZ\u2080={Z0:.1f} \u03a9',
            xy=(f_min, swr_min),
            xytext=(0.05, y_off),
            textcoords='axes fraction', fontsize=7,
            color=ds.color,
            bbox=dict(boxstyle='round,pad=0.3', fc='white',
                      ec=ds.color, alpha=0.85),
            arrowprops=dict(arrowstyle='->', color=ds.color, lw=0.8)
        )

    ax.axhline(2.0, color=COL_REF, lw=LW_REF, linestyle='--', label='SWR=2')
    _add_resonance_markers(ax, datasets)

    if show_bands:
        _overlay_bands_auto(ax, datasets)

    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('SWR')
    ax.set_title(_make_title(datasets,
                             f'SWR vs Frequency  |  Z\u2080 = {Z0:.1f} \u03a9'))
    ax.set_ylim(bottom=1.0)
    ax.legend(loc='upper right', framealpha=0.85, fontsize=8)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    _set_freq_limits(ax, datasets)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _add_resonance_markers(ax, datasets):
    """Add vertical resonance line for each visible dataset."""
    for ds in datasets:
        if not ds.visible:
            continue
        f_res = ds.f_res_mhz()
        if f_res:
            ax.axvline(f_res, color=ds.color, lw=LW_RES,
                       linestyle='-.', alpha=0.6,
                       label=f'{ds.name} res={f_res:.4f} MHz')


def _overlay_bands_auto(ax, datasets):
    """Overlay ham bands spanning the union of all dataset ranges."""
    visible = [ds for ds in datasets if ds.visible]
    if not visible:
        return
    fmin = min(ds.freq_mhz.min() for ds in visible)
    fmax = max(ds.freq_mhz.max() for ds in visible)
    overlay_bands(ax, fmin, fmax)


def _make_title(datasets, plot_type):
    """Build title from dataset names."""
    visible = [ds for ds in datasets if ds.visible]
    if not visible:
        return plot_type
    names = ' vs '.join(ds.name for ds in visible)
    return f'{plot_type}  |  {names}'


def _set_freq_limits(ax, datasets):
    """Set x-axis limits spanning all visible datasets."""
    visible = [ds for ds in datasets if ds.visible]
    if not visible:
        return
    fmin = min(ds.freq_mhz.min() for ds in visible)
    fmax = max(ds.freq_mhz.max() for ds in visible)
    margin = (fmax - fmin) * 0.02
    ax.set_xlim(fmin - margin, fmax + margin)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())