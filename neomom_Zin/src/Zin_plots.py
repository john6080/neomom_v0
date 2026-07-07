# Zin_plots.py
#
# Purpose: Plot functions for NeoMOM impedance sweep data.
#
# Each function takes a matplotlib Axes object and the data/meta
# dicts from Zin_reader.read_Zin_file().  Returns nothing — the
# caller owns the figure and axes.
#
# This module has NO knowledge of tkinter or the GUI layout.
# It only knows about matplotlib axes.
#
# Functions:
#   plot_RX   -- R and X vs frequency
#   plot_GB   -- G and B vs frequency (B zero crossing = resonance)
#   plot_SWR  -- SWR vs frequency
#   annotate_resonance -- shared helper, marks resonance on an axes

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from ham_bands   import overlay_bands
from Zin_reader  import compute_swr


# ------------------------------------------------------------------
# Colour and line style constants
# ------------------------------------------------------------------
COL_R   = '#1f77b4'   # blue  — resistance / conductance
COL_X   = '#d62728'   # red   — reactance / susceptance
COL_SWR = '#2ca02c'   # green — SWR
COL_RES = '#ff7f0e'   # orange — resonance marker
COL_REF = '#888888'   # grey  — reference lines (zero, SWR=2)

LW      = 1.8         # main curve linewidth
LW_REF  = 0.8         # reference line linewidth
LW_RES  = 1.2         # resonance marker linewidth


# ------------------------------------------------------------------
# plot_RX: resistance and reactance vs frequency
# ------------------------------------------------------------------
def plot_RX(ax, data, meta, show_bands=True):
    """
    Plot Rin (blue) and Xin (red) vs frequency on a shared axes.

    Features:
     - Zero reactance reference line (grey dashed)
     - Vertical resonance marker at Bin zero crossing
     - Annotation box with resonance frequency and Rin at resonance

    Parameters
    ----------
    ax   : matplotlib Axes
    data : dict from Zin_reader.read_Zin_file()
    meta : dict from Zin_reader.read_Zin_file()
    """
    freq = data['freq_mhz']
    Rin  = data['Rin']
    Xin  = data['Xin']

    # ---- curves ----
    ax.plot(freq, Rin, color=COL_R, lw=LW, label='R$_{in}$ [Ω]')
    ax.plot(freq, Xin, color=COL_X, lw=LW, label='X$_{in}$ [Ω]', linestyle='--')

    # ---- zero reactance reference ----
    ax.axhline(0, color=COL_REF, lw=LW_REF, linestyle=':')

    # ---- resonance marker ----
    f_res = meta.get('f_res_mhz')
    if f_res:
        _mark_resonance(ax, f_res, meta, label_pos='upper left')

    # ---- ham band overlay ----
    if show_bands:
        overlay_bands(ax, data['freq_mhz'].min(), data['freq_mhz'].max())

    # ---- formatting ----
    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('Impedance [Ω]')
    ax.set_title(_make_title(meta, 'Impedance vs Frequency'))
    ax.legend(loc='upper right', framealpha=0.85)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    _set_freq_limits(ax, freq)


# ------------------------------------------------------------------
# plot_GB: conductance and susceptance vs frequency
# ------------------------------------------------------------------
def plot_GB(ax, data, meta, show_bands=True):
    """
    Plot Gin (blue) and Bin (red) vs frequency.

    Bin = Im(Y) = Im(1/Zin).  The zero crossing of Bin marks
    antenna resonance — this is the key MoM validation diagnostic.

    Features:
     - Zero susceptance reference line (grey dashed) — resonance reference
     - Vertical resonance marker with frequency annotation
     - Values displayed in milli-Siemens for readability

    Parameters
    ----------
    ax   : matplotlib Axes
    data : dict from Zin_reader.read_Zin_file()
    meta : dict from Zin_reader.read_Zin_file()
    """
    freq = data['freq_mhz']
    Gin  = data['Gin']  * 1000.0   # S -> mS
    Bin  = data['Bin']  * 1000.0   # S -> mS

    # ---- curves ----
    ax.plot(freq, Gin, color=COL_R, lw=LW, label='G$_{in}$ [mS]')
    ax.plot(freq, Bin, color=COL_X, lw=LW, label='B$_{in}$ [mS]', linestyle='--')

    # ---- zero susceptance reference — resonance is where Bin = 0 ----
    ax.axhline(0, color=COL_REF, lw=LW_REF, linestyle=':')

    # ---- Gin peak annotation ----
    # Gin peak marks resonance for a lossless antenna.
    # Rrad = 1/Gin_peak [Ohm] — useful for comparison to literature.
    idx_peak = int(np.argmax(Gin))
    f_peak   = float(data['freq_mhz'][idx_peak])
    Gin_peak = float(Gin[idx_peak])              # already in mS
    Rrad     = 1000.0 / Gin_peak if Gin_peak > 0 else 0.0  # Ohm

    ax.plot(f_peak, Gin_peak, 'o',
            color=COL_R, ms=5, zorder=6)

    peak_label = (f'G$_{{in}}$ peak\n'
                  f'f = {f_peak:.4f} MHz\n'
                  f'G$_{{in}}$ = {Gin_peak:.3f} mS\n'
                  f'R$_{{rad}}$ = 1/G = {Rrad:.1f} \u03a9')

    ax.annotate(
        peak_label,
        xy=(f_peak, Gin_peak),
        xytext=(0.03, 0.55),
        textcoords='axes fraction',
        fontsize=8,
        color=COL_R,
        bbox=dict(boxstyle='round,pad=0.4', fc='white',
                  ec=COL_R, alpha=0.88),
        arrowprops=dict(arrowstyle='->', color=COL_R, lw=0.8)
    )

    # ---- resonance marker ----
    f_res = meta.get('f_res_mhz')
    if f_res:
        _mark_resonance(ax, f_res, meta, label_pos='upper left')

    # ---- ham band overlay ----
    if show_bands:
        overlay_bands(ax, data['freq_mhz'].min(), data['freq_mhz'].max())

    # ---- formatting ----
    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('Admittance [mS]')
    ax.set_title(_make_title(meta, 'Admittance vs Frequency'))
    ax.legend(loc='upper right', framealpha=0.85)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    _set_freq_limits(ax, freq)


# ------------------------------------------------------------------
# plot_SWR: SWR vs frequency
# ------------------------------------------------------------------
def plot_SWR(ax, data, meta, show_bands=True, Z0=50.0):
    """
    Plot SWR vs frequency.

    SWR is recomputed from Rin/Xin at the given Z0 reference impedance
    so the plot updates correctly when Z0 changes in the GUI.

    Features:
     - SWR = 2.0 reference line (grey dashed) — standard bandwidth marker
     - Vertical resonance marker at Bin zero crossing
     - Annotation with SWR minimum, frequency, and Z0 reference
     - Z0 shown in plot title and annotation box
     - Y-axis clipped at SWR_MAX

    Parameters
    ----------
    ax        : matplotlib Axes
    data      : dict from Zin_reader.read_Zin_file()
    meta      : dict from Zin_reader.read_Zin_file()
    show_bands: bool — overlay ham band markers
    Z0        : float — reference impedance [Ohm], default 50.0
    """
    SWR_MAX = 20.0

    freq = data['freq_mhz']
    # Recompute SWR at the user-selected Z0
    swr  = np.clip(compute_swr(data['Rin'], data['Xin'], Z0), 1.0, SWR_MAX)

    # ---- curve ----
    ax.plot(freq, swr, color=COL_SWR, lw=LW, label='SWR')

    # ---- SWR = 2 reference ----
    ax.axhline(2.0, color=COL_REF, lw=LW_REF, linestyle='--',
               label='SWR = 2')

    # ---- resonance marker ----
    f_res = meta.get('f_res_mhz')
    if f_res:
        _mark_resonance(ax, f_res, meta, label_pos='upper right')

    # ---- SWR minimum annotation ----
    swr_min = meta.get('swr_min')
    f_min   = meta.get('f_swr_min_mhz')
    # Recompute SWR min at current Z0
    idx_min   = int(np.argmin(swr))
    swr_min   = float(swr[idx_min])
    f_min     = float(freq[idx_min])

    ax.annotate(
        f'SWR min = {swr_min:.2f}\n@ {f_min:.4f} MHz\nZ\u2080 = {Z0:.1f} \u03a9',
        xy=(f_min, swr_min),
        xytext=(0.05, 0.85),
        textcoords='axes fraction',
        fontsize=8,
        color=COL_SWR,
        bbox=dict(boxstyle='round,pad=0.3', fc='white',
                  ec=COL_SWR, alpha=0.85),
        arrowprops=dict(arrowstyle='->', color=COL_SWR, lw=0.8)
    )

    # ---- ham band overlay ----
    if show_bands:
        overlay_bands(ax, data['freq_mhz'].min(), data['freq_mhz'].max())

    # ---- formatting ----
    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('SWR')
    ax.set_title(_make_title(meta, f'SWR vs Frequency  |  Z₀ = {Z0:.1f} Ω'))
    ax.set_ylim(bottom=1.0, top=min(SWR_MAX, swr.max() * 1.1))
    ax.legend(loc='upper right', framealpha=0.85)
    ax.grid(True, which='major', linestyle=':', alpha=0.5)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    _set_freq_limits(ax, freq)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _mark_resonance(ax, f_res, meta, label_pos='upper left'):
    """
    Draw a vertical line at resonance frequency and add an annotation
    box with resonance frequency and Rin at resonance.
    """
    ax.axvline(f_res, color=COL_RES, lw=LW_RES,
               linestyle='-.', label=f'Resonance {f_res:.4f} MHz')

    Rin_res = meta.get('Rin_res')
    if Rin_res:
        label = f'f$_{{res}}$ = {f_res:.4f} MHz\nR$_{{in}}$ = {Rin_res:.1f} Ω'
    else:
        label = f'f$_{{res}}$ = {f_res:.4f} MHz'

    # Position the box
    if label_pos == 'upper left':
        xy_text = (0.03, 0.92)
    else:
        xy_text = (0.70, 0.92)

    ax.annotate(
        label,
        xy=(f_res, ax.get_ylim()[1]),
        xytext=xy_text,
        textcoords='axes fraction',
        fontsize=8,
        color=COL_RES,
        bbox=dict(boxstyle='round,pad=0.3', fc='white',
                  ec=COL_RES, alpha=0.85)
    )


def _make_title(meta, plot_type):
    """Build a plot title from metadata."""
    title = meta.get('title', '')
    ground = meta.get('ground', '').capitalize()
    if title:
        return f'{title}  |  {plot_type}  |  {ground}'
    return f'{plot_type}  |  {ground}'


def _set_freq_limits(ax, freq):
    """Set x-axis limits with a small margin."""
    fmin = freq.min()
    fmax = freq.max()
    margin = (fmax - fmin) * 0.02
    ax.set_xlim(fmin - margin, fmax + margin)


# ------------------------------------------------------------------
# Self-test — plots all three to screen
# ------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    from Zin_reader import read_Zin_file, compute_swr

    if len(sys.argv) < 2:
        print("Usage: python3 Zin_plots.py <_Zin.csv>")
        sys.exit(1)

    meta, data = read_Zin_file(sys.argv[1])

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(meta.get('title', 'NeoMOM Impedance Sweep'), fontsize=11)

    plot_RX (axes[0], data, meta, show_bands=True)
    plot_GB (axes[1], data, meta, show_bands=True)
    plot_SWR(axes[2], data, meta, show_bands=True, Z0=50.0)

    fig.tight_layout()
    plt.show()