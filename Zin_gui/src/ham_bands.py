# ham_bands.py
#
# Purpose: Ham band frequency definitions and plot overlay functions.
#
# Covers all ITU Region 2 (Americas) amateur bands from 160m to 23cm.
# Band edges follow ARRL band plan.
#
# Usage:
#   from ham_bands import overlay_bands
#   overlay_bands(ax, freq_min_mhz, freq_max_mhz)

import matplotlib.patches as mpatches

# ------------------------------------------------------------------
# Ham band definitions — (name, fLow_MHz, fHigh_MHz, colour)
# Colours are muted pastels so they don't overwhelm the data curves.
# ------------------------------------------------------------------
HAM_BANDS = [
    # HF bands
    ('160m',   1.800,   2.000,  '#b0c4de'),   # light steel blue
    ('80m',    3.500,   4.000,  '#c8e6c9'),   # light green
    ('60m',    5.3305,  5.4035, '#ffe0b2'),   # light orange
    ('40m',    7.000,   7.300,  '#fff9c4'),   # light yellow
    ('30m',   10.100,  10.150,  '#f8bbd0'),   # light pink
    ('20m',   14.000,  14.350,  '#d1c4e9'),   # light purple
    ('17m',   18.068,  18.168,  '#b2dfdb'),   # light teal
    ('15m',   21.000,  21.450,  '#b0c4de'),   # light steel blue
    ('12m',   24.890,  24.990,  '#c8e6c9'),   # light green
    ('10m',   28.000,  29.700,  '#fff9c4'),   # light yellow
    # VHF bands
    ('6m',    50.000,  54.000,  '#ffe0b2'),   # light orange
    ('2m',   144.000, 148.000,  '#f8bbd0'),   # light pink
    ('1.25m',222.000, 225.000,  '#d1c4e9'),   # light purple
    # UHF bands
    ('70cm', 420.000, 450.000,  '#b2dfdb'),   # light teal
    ('33cm', 902.000, 928.000,  '#b0c4de'),   # light steel blue
    ('23cm',1240.000,1300.000,  '#c8e6c9'),   # light green
]


def overlay_bands(ax, freq_min_mhz, freq_max_mhz, alpha_fill=0.25, alpha_edge=0.7):
    """
    Overlay ham band markers on a frequency-axis plot.

    Only bands that overlap [freq_min_mhz, freq_max_mhz] are drawn.
    Each band gets:
      - A shaded region (axvspan) at alpha_fill opacity
      - Dashed vertical lines at band edges at alpha_edge opacity
      - A small text label at the top of the shaded region

    Parameters
    ----------
    ax            : matplotlib Axes with frequency [MHz] on x-axis
    freq_min_mhz  : float  lower bound of sweep (from meta['fstart_mhz'])
    freq_max_mhz  : float  upper bound of sweep (from meta['fstop_mhz'])
    alpha_fill    : float  opacity of shaded region (default 0.25)
    alpha_edge    : float  opacity of edge lines (default 0.7)

    Returns
    -------
    list of band names that were drawn (for legend building if needed)
    """
    drawn = []
    ylims = ax.get_ylim()
    y_label = ylims[1] - (ylims[1] - ylims[0]) * 0.04  # near top

    for name, flo, fhi, colour in HAM_BANDS:

        # Skip bands that don't overlap the sweep range
        if fhi < freq_min_mhz or flo > freq_max_mhz:
            continue

        # Clip to sweep range for cleaner appearance
        flo_clipped = max(flo, freq_min_mhz)
        fhi_clipped = min(fhi, freq_max_mhz)

        # ---- shaded region ----
        ax.axvspan(flo_clipped, fhi_clipped,
                   color=colour, alpha=alpha_fill, zorder=0)

        # ---- edge lines — only draw if edge is inside sweep range ----
        if flo >= freq_min_mhz:
            ax.axvline(flo, color=colour, lw=1.0,
                       linestyle='--', alpha=alpha_edge, zorder=1)
        if fhi <= freq_max_mhz:
            ax.axvline(fhi, color=colour, lw=1.0,
                       linestyle='--', alpha=alpha_edge, zorder=1)

        # ---- band label ----
        f_mid = (flo_clipped + fhi_clipped) / 2.0
        ax.text(f_mid, y_label, name,
                ha='center', va='top',
                fontsize=7, color='#444444',
                bbox=dict(boxstyle='round,pad=0.15',
                          fc=colour, ec='none', alpha=0.7),
                zorder=5)

        drawn.append(name)

    return drawn


def bands_in_range(freq_min_mhz, freq_max_mhz):
    """
    Return list of band names that overlap [freq_min_mhz, freq_max_mhz].
    Useful for deciding whether to offer band overlay in the GUI.
    """
    return [name for name, flo, fhi, _ in HAM_BANDS
            if fhi >= freq_min_mhz and flo <= freq_max_mhz]


# ------------------------------------------------------------------
# Self-test
# ------------------------------------------------------------------
if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(10, 4))

    # Dummy SWR curve across 40m band
    freq = np.linspace(6.5, 8.5, 201)
    swr  = 1.0 + 15.0 * ((freq - 7.15) / 0.8) ** 2
    ax.plot(freq, np.clip(swr, 1, 20), 'g-', lw=1.8, label='SWR')
    ax.axhline(2.0, color='grey', lw=0.8, linestyle='--')
    ax.set_xlim(6.5, 8.5)
    ax.set_ylim(1.0, 12.0)

    overlay_bands(ax, 6.5, 8.5)

    ax.set_xlabel('Frequency [MHz]')
    ax.set_ylabel('SWR')
    ax.set_title('Ham band overlay self-test')
    ax.legend()
    plt.tight_layout()
    plt.show()
