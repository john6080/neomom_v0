# sweep_data.py
#
# Purpose: Internal data model for impedance sweep datasets.
#          All derived quantities (Y, SWR, etc.) are computed
#          on demand from the stored Rin/Xin arrays.
#
# Usage:
#   from sweep_data import SweepData, COLOR_CYCLE
#   ds = SweepData(name='NeoMoM', ...)

import numpy as np
from dataclasses import dataclass, field

# ------------------------------------------------------------------
# Colour cycle — distinct colours for overlaid datasets
# ------------------------------------------------------------------
COLOR_CYCLE = [
    '#1f77b4',   # blue
    '#d62728',   # red
    '#2ca02c',   # green
    '#ff7f0e',   # orange
    '#9467bd',   # purple
    '#8c564b',   # brown
    '#e377c2',   # pink
    '#17becf',   # cyan
]

LINE_STYLES = ['-', '--', '-.', ':']


def next_color(existing):
    """Return next unused colour from COLOR_CYCLE."""
    used = {ds.color for ds in existing}
    for c in COLOR_CYCLE:
        if c not in used:
            return c
    return COLOR_CYCLE[len(existing) % len(COLOR_CYCLE)]


def next_linestyle(existing):
    """Return next line style based on dataset count."""
    return LINE_STYLES[len(existing) % len(LINE_STYLES)]


# ------------------------------------------------------------------
# SweepData — one dataset
# ------------------------------------------------------------------

@dataclass
class SweepData:
    """
    One impedance sweep dataset.

    Only freq_mhz, Rin, Xin are stored.
    All other quantities are computed on demand.

    Attributes
    ----------
    name      : display name shown in dataset panel and legend
    filepath  : source file path
    source    : 'neomom' or 'eznec'
    meta      : dict from Zin_reader — title, nfreq, resonance, etc.
    freq_mhz  : 1-D numpy array — frequency [MHz]
    Rin       : 1-D numpy array — resistance [Ohm]
    Xin       : 1-D numpy array — reactance [Ohm]
    color     : matplotlib colour string
    linestyle : matplotlib line style string
    visible   : whether to include in plots
    """
    name:      str
    filepath:  str
    source:    str
    meta:      dict
    freq_mhz:  np.ndarray
    Rin:       np.ndarray
    Xin:       np.ndarray
    color:     str  = '#1f77b4'
    linestyle: str  = '-'
    visible:   bool = True

    # ----------------------------------------------------------
    # Computed quantities — derived from Rin/Xin on demand
    # ----------------------------------------------------------

    @property
    def Zin_mag(self):
        return np.sqrt(self.Rin**2 + self.Xin**2)

    @property
    def Zin_cpx(self):
        return self.Rin + 1j * self.Xin

    @property
    def Yin_cpx(self):
        z = self.Zin_cpx
        mag = np.abs(z)
        return np.where(mag > 0, 1.0 / z, 0j)

    @property
    def Gin(self):
        return np.real(self.Yin_cpx)

    @property
    def Bin(self):
        return np.imag(self.Yin_cpx)

    @property
    def Yin_mag(self):
        return np.abs(self.Yin_cpx)

    def swr(self, Z0=50.0):
        """Compute SWR at arbitrary reference impedance Z0."""
        z    = self.Zin_cpx
        gamma = (z - Z0) / (z + Z0)
        gm   = np.clip(np.abs(gamma), 0.0, 0.9999)
        return np.clip((1 + gm) / (1 - gm), 1.0, 999.0)

    def return_loss_db(self, Z0=50.0):
        """Return loss in dB = -20*log10(|gamma|)."""
        z     = self.Zin_cpx
        gamma = (z - Z0) / (z + Z0)
        gm    = np.clip(np.abs(gamma), 1e-12, 1.0)
        return -20.0 * np.log10(gm)

    # ----------------------------------------------------------
    # Derived scalar quantities
    # ----------------------------------------------------------

    def f_res_mhz(self):
        """Frequency of Bin zero crossing (resonance)."""
        from Zin_reader import _find_zero_crossing
        return _find_zero_crossing(self.freq_mhz, self.Bin)

    def swr_min(self, Z0=50.0):
        """Minimum SWR and its frequency."""
        s = self.swr(Z0)
        idx = int(np.argmin(s))
        return float(s[idx]), float(self.freq_mhz[idx])

    def rin_at_res(self):
        """Rin at resonance (interpolated)."""
        from Zin_reader import _find_zero_crossing, _interpolate_at
        f_res = _find_zero_crossing(self.freq_mhz, self.Bin)
        return _interpolate_at(self.freq_mhz, self.Rin, f_res)

    # ----------------------------------------------------------
    # Display helpers
    # ----------------------------------------------------------

    def label(self):
        """Short label for legend."""
        return self.name

    def status_text(self, Z0=50.0):
        """One-line status bar summary."""
        f_res = self.f_res_mhz()
        swr_v, f_swr = self.swr_min(Z0)
        rin_res = self.rin_at_res()

        parts = [f'{self.name}:']
        if f_res:
            parts.append(f'res={f_res:.4f} MHz')
        if rin_res:
            parts.append(f'Rin={rin_res:.1f}Ω')
        parts.append(f'SWR min={swr_v:.3f} @ {f_swr:.4f} MHz')
        return '   '.join(parts)