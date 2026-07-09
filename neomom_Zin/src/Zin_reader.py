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
# EZNEC file reader
# ------------------------------------------------------------------

def read_eznec_file(filepath):
    """
    Parse an EZNEC Pro/2+ frequency sweep export file.

    Expected format (CSV):
        Line 1 : "EZNEC Pro/2+ ver. X.X"
        Line 2 : "title", "date"
        Line 3 : "Alt Z0: ", <value>
        Line 4 : column headers (quoted)
        Line 5+: freq, src#, R, X, SWR(50), SWR(altZ0)

    Returns same (meta, data) format as read_Zin_file() so the GUI
    and plot functions work identically for both file types.

    Parameters
    ----------
    filepath : str

    Returns
    -------
    meta : dict
    data : dict of 1-D numpy arrays
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Cannot find file: {filepath}')

    with open(filepath, 'r', errors='ignore') as f:
        lines = [l.rstrip('\n') for l in f.readlines()]

    if len(lines) < 5:
        raise ValueError(f'File too short to be a valid EZNEC export: {filepath}')

    # ---- parse header lines ----
    meta = {}
    meta['source_type'] = 'eznec'

    # Line 1 — version
    meta['version'] = lines[0].strip().strip('"')

    # Line 2 — title, date
    parts2 = [p.strip().strip('"') for p in lines[1].split(',')]
    meta['title'] = parts2[0] if parts2 else ''
    meta['date']  = parts2[1] if len(parts2) > 1 else ''

    # Line 3 — Alt Z0
    try:
        meta['z0_alt_ohm'] = float(lines[2].split(',')[1].strip())
    except (IndexError, ValueError):
        meta['z0_alt_ohm'] = 50.0

    # Line 4 — column headers (skip)
    # Line 5+ — data
    rows = []
    for line in lines[4:]:
        line = line.strip()
        if not line:
            continue
        try:
            vals = [float(v) for v in line.split(',')]
            if len(vals) >= 4:
                rows.append(vals)
        except ValueError:
            continue

    if not rows:
        raise ValueError(f'No data rows found in: {filepath}')

    arr = np.array(rows, dtype=float)

    # Columns: freq, src#, R, X, SWR(50), SWR(altZ0)
    freq_mhz = arr[:, 0]
    Rin      = arr[:, 2]
    Xin      = arr[:, 3]

    # Compute full set from R and X
    Zin_mag  = np.sqrt(Rin**2 + Xin**2)
    Zin_cpx  = Rin + 1j * Xin
    Yin_cpx  = np.where(Zin_mag > 0, 1.0 / Zin_cpx, 0j)
    Gin      = np.real(Yin_cpx)
    Bin      = np.imag(Yin_cpx)
    Yin_mag  = np.abs(Yin_cpx)
    SWR      = compute_swr(Rin, Xin, Z0=50.0)

    data = {
        'freq_mhz' : freq_mhz,
        'Rin'      : Rin,
        'Xin'      : Xin,
        'Zin_mag'  : Zin_mag,
        'Gin'      : Gin,
        'Bin'      : Bin,
        'Yin_mag'  : Yin_mag,
        'SWR'      : SWR,
    }

    # Populate meta fields to match neomom format
    meta['nfreq']     = len(freq_mhz)
    meta['fstart_mhz'] = float(freq_mhz[0])
    meta['fstop_mhz']  = float(freq_mhz[-1])
    meta['fstep_mhz']  = float(freq_mhz[1] - freq_mhz[0]) if len(freq_mhz) > 1 else 0.0
    meta['z0_ref_ohm'] = 50.0

    # Derived quantities — same as neomom reader
    meta['f_res_mhz']    = _find_zero_crossing(freq_mhz, Bin)
    idx_swr              = int(np.argmin(SWR))
    meta['swr_min']      = float(SWR[idx_swr])
    meta['f_swr_min_mhz'] = float(freq_mhz[idx_swr])
    meta['Rin_res']      = _interpolate_at(freq_mhz, Rin, meta['f_res_mhz'])

    return meta, data


def detect_and_read(filepath):
    """
    Auto-detect file type and call the correct reader.

    Detection:
      - First line contains 'EZNEC' -> read_eznec_file()
      - Otherwise                   -> read_Zin_file()

    Returns (meta, data) in the standard format.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Cannot find file: {filepath}')

    with open(filepath, 'r', errors='ignore') as f:
        first_line = f.readline()

    if 'EZNEC' in first_line.upper():
        return read_eznec_file(filepath)
    else:
        return read_Zin_file(filepath)


# ------------------------------------------------------------------
# SweepData factory functions
# ------------------------------------------------------------------

def sweep_from_file(filepath, name=None, color='#1f77b4', linestyle='-'):
    """
    Auto-detect file type, read it, and return a SweepData object.

    Parameters
    ----------
    filepath  : str   path to NeoMoM _Zin.csv or EZNEC .txt
    name      : str   display name; defaults to filename stem
    color     : str   matplotlib color
    linestyle : str   matplotlib line style

    Returns
    -------
    SweepData
    """
    from sweep_data import SweepData
    import os

    meta, data = detect_and_read(filepath)

    if name is None:
        name = os.path.splitext(os.path.basename(filepath))[0]

    source = meta.get('source_type', 'neomom')

    return SweepData(
        name      = name,
        filepath  = filepath,
        source    = source,
        meta      = meta,
        freq_mhz  = data['freq_mhz'],
        Rin       = data['Rin'],
        Xin       = data['Xin'],
        color     = color,
        linestyle = linestyle,
    )


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