# Zin_reader.py
#
# Purpose: Parse NeoMOM impedance sweep _Zin.csv files.
# Returns: (metadata dict, data dict of numpy arrays)
#
# This module has NO knowledge of GUI or plotting.
# Mirrors the structure of data_reader.py in neomom_plot.

import numpy as np
import os


def read_Zin_file(filepath):
    """
    Parse a NeoMOM impedance sweep CSV file.

    Parameters
    ----------
    filepath : str
        Path to the _Zin.csv file.

    Returns
    -------
    meta : dict
        Metadata extracted from # header lines.
        Notable keys:
            meta['title']        : str
            meta['file']         : str  — source .nml filename
            meta['ground']       : str
            meta['nports']       : int
            meta['nfreq']        : int
            meta['fstart_mhz']   : float
            meta['fstop_mhz']    : float
            meta['fstep_mhz']    : float  (0 if not in header)
            meta['z0_ref_ohm']   : float
            meta['f_res_mhz']    : float  — frequency of Bin zero crossing
            meta['swr_min']      : float  — minimum SWR
            meta['f_swr_min_mhz']: float  — frequency of SWR minimum

    data : dict of 1-D numpy arrays
        Keys:
            'freq_mhz'  : frequency [MHz]
            'Rin'       : resistance [Ohm]
            'Xin'       : reactance [Ohm]
            'Zin_mag'   : |Zin| [Ohm]
            'Gin'       : conductance [S]
            'Bin'       : susceptance [S]
            'Yin_mag'   : |Yin| [S]
            'SWR'       : standing wave ratio

    Raises
    ------
    FileNotFoundError  if filepath does not exist.
    ValueError         if the data block cannot be parsed.
    """

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Cannot find file: {filepath}")

    meta_lines = []
    data_lines = []

    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith('#'):
                meta_lines.append(stripped)
            elif stripped:
                data_lines.append(stripped)

    # ------------------------------------------------------------------
    # Parse metadata
    # ------------------------------------------------------------------
    meta = {}

    for line in meta_lines:
        content = line.lstrip('#').strip()
        if ':' not in content:
            continue
        key, _, value = content.partition(':')
        key   = key.strip().lower().replace(' ', '_')
        value = value.strip()
        if key:
            meta[key] = value

    # Convert to correct types
    int_keys   = ['nports', 'nfreq']
    float_keys = ['fstart_mhz', 'fstop_mhz', 'fstep_mhz', 'z0_ref_ohm']

    for k in int_keys:
        if k in meta:
            try:
                meta[k] = int(meta[k])
            except (ValueError, TypeError):
                pass

    for k in float_keys:
        if k in meta:
            try:
                meta[k] = float(meta[k])
            except (ValueError, TypeError):
                pass

    # Default fstep_mhz if not present (older files)
    if 'fstep_mhz' not in meta:
        meta['fstep_mhz'] = 0.0

    # ------------------------------------------------------------------
    # Parse data block
    # ------------------------------------------------------------------
    col_names = ['freq_mhz', 'Rin', 'Xin', 'Zin_mag',
                 'Gin', 'Bin', 'Yin_mag', 'SWR']

    rows = []
    for line in data_lines:
        try:
            vals = [float(v) for v in line.split()]
            if len(vals) >= 8:
                rows.append(vals[:8])
        except ValueError:
            continue

    if not rows:
        raise ValueError(f"No data rows found in: {filepath}")

    arr = np.array(rows, dtype=float)

    data = {
        'freq_mhz' : arr[:, 0],
        'Rin'      : arr[:, 1],
        'Xin'      : arr[:, 2],
        'Zin_mag'  : arr[:, 3],
        'Gin'      : arr[:, 4],
        'Bin'      : arr[:, 5],
        'Yin_mag'  : arr[:, 6],
        'SWR'      : arr[:, 7],
    }

    # ------------------------------------------------------------------
    # Derived quantities — resonance and SWR minimum
    # ------------------------------------------------------------------

    # Resonant frequency — Bin zero crossing (sign change in susceptance)
    # Use linear interpolation between the two points bracketing zero.
    meta['f_res_mhz'] = _find_zero_crossing(data['freq_mhz'], data['Bin'])

    # SWR minimum
    idx_swr = int(np.argmin(data['SWR']))
    meta['swr_min']       = float(data['SWR'][idx_swr])
    meta['f_swr_min_mhz'] = float(data['freq_mhz'][idx_swr])

    # Rin at resonance (interpolated)
    meta['Rin_res'] = _interpolate_at(
        data['freq_mhz'], data['Rin'], meta['f_res_mhz'])

    return meta, data


def _find_zero_crossing(x, y):
    """
    Find the x value where y crosses zero using linear interpolation.
    Returns the first zero crossing found, or None if none exists.

    Parameters
    ----------
    x : 1-D array   independent variable (frequency)
    y : 1-D array   dependent variable (Bin susceptance)

    Returns
    -------
    float or None
    """
    for i in range(len(y) - 1):
        if y[i] * y[i + 1] <= 0.0:
            # Linear interpolation
            dy = y[i + 1] - y[i]
            if abs(dy) < 1e-30:
                return float(x[i])
            t = -y[i] / dy
            return float(x[i] + t * (x[i + 1] - x[i]))
    return None


def _interpolate_at(x, y, x0):
    """
    Linear interpolation of y at x = x0.
    Returns None if x0 is outside the range of x.
    """
    if x0 is None:
        return None
    for i in range(len(x) - 1):
        if x[i] <= x0 <= x[i + 1]:
            t = (x0 - x[i]) / (x[i + 1] - x[i])
            return float(y[i] + t * (y[i + 1] - y[i]))
    return None


# ------------------------------------------------------------------
# SWR recomputation utility
# ------------------------------------------------------------------

def compute_swr(Rin, Xin, Z0=50.0):
    """
    Recompute SWR from Rin and Xin arrays at arbitrary Z0.

    Parameters
    ----------
    Rin  : numpy array  — resistance [Ohm]
    Xin  : numpy array  — reactance [Ohm]
    Z0   : float        — reference impedance [Ohm], default 50.0

    Returns
    -------
    swr  : numpy array  — SWR, clipped to [1, 999]
    """
    import numpy as np
    Zin   = Rin + 1j * Xin
    gamma = (Zin - Z0) / (Zin + Z0)
    gm    = np.abs(gamma)
    # Guard against |gamma| >= 1 (open/short circuit)
    gm    = np.clip(gm, 0.0, 0.9999)
    swr   = (1.0 + gm) / (1.0 - gm)
    return np.clip(swr, 1.0, 999.0)


# ------------------------------------------------------------------
# Command-line self-test
# ------------------------------------------------------------------
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 Zin_reader.py <_Zin.csv>")
        sys.exit(1)

    meta, data = read_Zin_file(sys.argv[1])

    print("\n--- METADATA ---")
    for k, v in meta.items():
        print(f"  {k:20s} : {v}")

    print(f"\n--- DATA ---")
    print(f"  Points    : {len(data['freq_mhz'])}")
    print(f"  Freq range: {data['freq_mhz'][0]:.4f} — "
          f"{data['freq_mhz'][-1]:.4f} MHz")
    print(f"  Rin range : {data['Rin'].min():.2f} — "
          f"{data['Rin'].max():.2f} Ohm")
    print(f"  Xin range : {data['Xin'].min():.2f} — "
          f"{data['Xin'].max():.2f} Ohm")

    print(f"\n--- DERIVED ---")
    f_res = meta.get('f_res_mhz')
    if f_res:
        print(f"  Resonance : {f_res:.4f} MHz")
        print(f"  Rin @ res : {meta.get('Rin_res', '?'):.2f} Ohm")
    else:
        print(f"  Resonance : not found in this frequency range")
    print(f"  SWR min   : {meta['swr_min']:.3f} @ "
          f"{meta['f_swr_min_mhz']:.4f} MHz")