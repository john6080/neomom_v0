# SPDX-License-Identifier: MIT
# Copyright (c) 2026 John Shaeffer (KZ4TS)

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


def finalize_meta(meta):
    """
    Shared metadata post-processing: type coercion + derived display
    strings for GUI / plot headers.

    Factored out of read_antenna_file() so that other readers -- notably
    nec_out_reader.read_nec_out() for NEC5 .out files -- can produce a
    meta dict in this exact same shape. Anything downstream (neomom_plot.py,
    plot_panel.py) only ever relies on this shape, never on which reader
    produced it.

    Mutates and returns the same dict for convenience.
    """
    # ---- Section 3: convert scalar metadata values to proper types ----
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

    # ---- Section 4: derived display strings ----
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

    return meta


def validate_pattern_data(meta, df, filepath):
    """
    Sanity-check that (meta, df) actually look like an antenna radiation
    pattern dataset -- not some other file that happened to parse
    without raising an exception (e.g. a neomom_Zin.csv impedance-vs-
    frequency sweep: different data entirely, but if it happens to have
    the same number of whitespace-separated columns per row, a naive
    reader can "succeed" while silently mislabeling frequency/impedance
    values as theta/phi/field data).

    Shared between read_antenna_file() (CSV) and
    nec_out_reader.read_nec_out() (NEC5 .out) so both enforce the same
    bar. Raises ValueError with a specific, actionable message on
    failure; never silently proceeds with data that doesn't look like a
    real theta/phi sweep. Returns None (mutates nothing) on success.
    """
    fname = os.path.basename(filepath)
    required_cols = ['theta_deg', 'phi_deg',
                     're_Etheta', 'im_Etheta', 're_Ephi', 'im_Ephi']

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"'{fname}' doesn't look like an antenna pattern file -- "
            f"missing expected column(s): {', '.join(missing)}.")

    if len(df) < 4:
        raise ValueError(
            f"'{fname}' has only {len(df)} data row(s) -- too few to be "
            f"a theta/phi pattern sweep. Wrong file?")

    theta = df['theta_deg']
    phi   = df['phi_deg']

    if theta.isna().any() or phi.isna().any():
        raise ValueError(
            f"'{fname}' has non-numeric or missing theta/phi values. "
            f"This usually means the file's column layout doesn't "
            f"match a pattern file (wrong number of fields per row?).")

    if theta.min() < -0.5 or theta.max() > 180.5:
        raise ValueError(
            f"'{fname}': theta values range from {theta.min():.2f} to "
            f"{theta.max():.2f}, outside the valid 0-180\u00b0 range for "
            f"an elevation angle. This usually means '{fname}' isn't a "
            f"radiation pattern file (e.g. an impedance-vs-frequency "
            f"sweep instead) -- double check you picked the right file.")

    if phi.min() < -180.5 or phi.max() > 360.5:
        raise ValueError(
            f"'{fname}': phi values range from {phi.min():.2f} to "
            f"{phi.max():.2f}, outside any valid azimuth-angle "
            f"convention (0-360\u00b0 or -180-180\u00b0). This usually "
            f"means '{fname}' isn't a radiation pattern file -- double "
            f"check you picked the right file.")

    if theta.nunique() < 2 or phi.nunique() < 2:
        raise ValueError(
            f"'{fname}' only has a single distinct theta or phi value "
            f"across all rows -- that's not a 2D pattern sweep. "
            f"Wrong file?")

    ntheta = meta.get('ntheta')
    nphi   = meta.get('nphi')
    if not (isinstance(ntheta, int) and isinstance(nphi, int)):
        raise ValueError(
            f"'{fname}' doesn't declare an ntheta x nphi grid size -- "
            f"every genuine neomom pattern file does. This usually "
            f"means '{fname}' is a different kind of file entirely "
            f"(e.g. an impedance sweep) rather than a radiation "
            f"pattern -- double check you picked the right file.")

    expected = ntheta * nphi
    if len(df) != expected:
        raise ValueError(
            f"'{fname}' declares a {ntheta} x {nphi} grid "
            f"({expected} rows) but contains {len(df)} data rows. "
            f"The file may be truncated or corrupted.")


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
    # SECTION 3 + 4: Type coercion + derived display strings.
    # Factored into finalize_meta() so nec_out_reader.py (NEC5 .out
    # files) can produce a meta dict in this exact same shape.
    # ----------------------------------------------------------------
    meta = finalize_meta(meta)

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
    # SECTION 6: Validate that this actually looks like a pattern file
    # ----------------------------------------------------------------
    validate_pattern_data(meta, df, filepath)

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