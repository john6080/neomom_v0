# data_reader.py
#
# Purpose: Parse antenna pattern CSV files.
# Returns: (metadata dict, pandas DataFrame)
# This module has NO knowledge of GUI or plotting.

import pandas as pd
import numpy as np
from io import StringIO
import sys
import os


def parse_peak_pair(value_str):
    """
    Parse a metadata value that contains two floats.
    Example input:  '25.00000       90.00000'
    Returns: (theta_float, phi_float) tuple or None if parse fails.
    """
    parts = value_str.split()
    if len(parts) >= 2:
        try:
            return (float(parts[0]), float(parts[1]))
        except ValueError:
            return None
    return None


def parse_complex(value_str):
    """
    Parse a complex impedance string in the format '(real,imag)'.
    Example input:  '(73.50742,-0.5210419)'
    Returns: complex number, or None if parse fails.
    """
    try:
        # Strip parentheses and split on comma
        s = value_str.strip().strip('()')
        parts = s.split(',')
        if len(parts) == 2:
            return complex(float(parts[0]), float(parts[1]))
    except (ValueError, AttributeError):
        pass
    return None


def read_antenna_file(filepath):
    """
    Parse an antenna pattern file with # comment/metadata header.

    Parameters
    ----------
    filepath : str
        Path to the antenna pattern file

    Returns
    -------
    meta : dict
        All metadata extracted from header comments.
        Notable keys:
            meta['title']             : str
            meta['frequency_mhz']     : float
            meta['wavelength_m']      : float
            meta['gain_peak_dbi']     : float
            meta['input_impedance']   : complex  e.g. (73.5-0.52j)
            meta['swr']               : float
            meta['ground_type']       : str
            meta['height_above_ground']: float
            meta['e_theta_max']       : (theta, phi) tuple
            meta['e_phi_max']         : (theta, phi) tuple
            meta['e_total_max']       : (theta, phi) tuple
            meta['ntheta']            : int
            meta['nphi']              : int

    df : pandas DataFrame
        Columns: theta_deg, phi_deg,
                 re_Etheta, im_Etheta,
                 re_Ephi,   im_Ephi
    """

    # ----------------------------------------------------------------
    # SECTION 1: Read raw lines, split metadata from data
    # ----------------------------------------------------------------
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

    # ----------------------------------------------------------------
    # SECTION 2: Parse metadata lines into a dictionary
    # ----------------------------------------------------------------
    PEAK_KEYS    = {'e_theta_max', 'e_phi_max', 'e_total_max'}
    COMPLEX_KEYS = {'input_impedance'}

    meta = {}

    for line in meta_lines:
        content = line.lstrip('#').strip()
        if ':' not in content:
            continue

        key, _, value = content.partition(':')
        key   = key.strip().lower().replace(' ', '_')
        value = value.strip()

        if not key:
            continue

        if key in PEAK_KEYS:
            meta[key] = parse_peak_pair(value)
        elif key in COMPLEX_KEYS:
            meta[key] = parse_complex(value)
        else:
            meta[key] = value

    # ----------------------------------------------------------------
    # SECTION 3: Convert scalar metadata values to proper types
    # ----------------------------------------------------------------
    float_keys = [
        'frequency_mhz', 'gain_peak_dbi', 'wavelength_m',
        'theta_start', 'theta_stop', 'theta_step',
        'phi_start',   'phi_stop',   'phi_step',
        'swr',         'height_above_ground',
    ]
    int_keys = ['ntheta', 'nphi']

    for key in float_keys:
        if key in meta:
            try:
                meta[key] = float(meta[key])
            except (ValueError, TypeError):
                pass

    for key in int_keys:
        if key in meta:
            try:
                meta[key] = int(meta[key])
            except (ValueError, TypeError):
                pass

    # ----------------------------------------------------------------
    # SECTION 4: Derived display strings for GUI and plot headers
    # ----------------------------------------------------------------
    # Input impedance: format as 'R ± jX Ω'
    z = meta.get('input_impedance')
    if isinstance(z, complex):
        sign = '+' if z.imag >= 0 else '-'
        meta['impedance_str'] = f"{z.real:.2f} {sign} j{abs(z.imag):.2f} Ω"
    else:
        meta['impedance_str'] = str(z) if z else '?'

    # SWR: format to 3 significant figures
    swr = meta.get('swr')
    meta['swr_str'] = f"{swr:.3g}" if isinstance(swr, float) else '?'

    # Height: format with units
    h = meta.get('height_above_ground')
    meta['height_str'] = f"{h:.4g} m" if isinstance(h, float) else '?'

    # Frequency: format to reasonable precision
    f = meta.get('frequency_mhz')
    meta['freq_str'] = f"{f:.4g} MHz" if isinstance(f, float) else '?'

    # ----------------------------------------------------------------
    # SECTION 5: Parse the data block with pandas
    # ----------------------------------------------------------------
    col_names = [
        'theta_deg', 'phi_deg',
        're_Etheta', 'im_Etheta',
        're_Ephi',   'im_Ephi'
    ]

    data_text = '\n'.join(data_lines)

    df = pd.read_csv(
        StringIO(data_text),
        sep=r'\s+',
        names=col_names,
        dtype=float
    )

    # ----------------------------------------------------------------
    # SECTION 6: Validate row count against grid descriptors
    # ----------------------------------------------------------------
    if 'ntheta' in meta and 'nphi' in meta:
        expected = meta['ntheta'] * meta['nphi']
        actual   = len(df)
        if actual != expected:
            print(f"WARNING: Expected {expected} data rows "
                  f"(nTheta={meta['ntheta']} x nPhi={meta['nphi']}) "
                  f"but found {actual} rows.")

    return meta, df


# ----------------------------------------------------------------
# SECTION 7: Command-line test
# ----------------------------------------------------------------
if __name__ == '__main__':

    if len(sys.argv) < 2:
        print("Usage: python3 data_reader.py <antenna_file.csv>")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"\nReading: {filepath}\n")

    meta, df = read_antenna_file(filepath)

    print("\n--- METADATA ---")
    for k, v in meta.items():
        print(f"  {k:30s} : {v}")

    print(f"\n--- KEY DISPLAY FIELDS ---")
    print(f"  Title      : {meta.get('title', '?')}")
    print(f"  Frequency  : {meta.get('freq_str', '?')}")
    print(f"  Impedance  : {meta.get('impedance_str', '?')}")
    print(f"  SWR        : {meta.get('swr_str', '?')}")
    print(f"  Ground     : {meta.get('ground_type', '?')}")
    print(f"  Height     : {meta.get('height_str', '?')}")
    print(f"  Peak gain  : {meta.get('gain_peak_dbi', '?')} dBi")

    print(f"\n--- PEAK ANGLES ---")
    for key in ['e_theta_max', 'e_phi_max', 'e_total_max']:
        val = meta.get(key)
        if val:
            print(f"  {key:20s} : theta={val[0]:6.1f} deg,  "
                  f"phi={val[1]:6.1f} deg")
        else:
            print(f"  {key:20s} : not found")

    print(f"\n--- DATA FRAME ---")
    print(f"  Shape   : {df.shape}  (rows, columns)")
    print(f"  Columns : {list(df.columns)}")
    theta_range = f"{df['theta_deg'].min():.1f} → {df['theta_deg'].max():.1f}"
    phi_range   = f"{df['phi_deg'].min():.1f} → {df['phi_deg'].max():.1f}"
    print(f"  theta   : {theta_range} deg")
    print(f"  phi     : {phi_range} deg")
    print(f"\n  First 3 rows:")
    print(df.head(3))
    print(f"\n  Last 3 rows:")
    print(df.tail(3))