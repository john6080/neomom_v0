# nec_out_reader.py
#
# Purpose: Parse a NEC5 .out file (RADIATION PATTERNS section + a few
# header blocks) into EXACTLY the (meta, df) shape that
# data_reader.read_antenna_file() returns for a neomom CSV. That's the
# whole contract -- anywhere in this app that accepts a neomom CSV can
# accept a NEC5 .out file instead, with zero other changes.
#
#   df   columns : theta_deg, phi_deg, re_Etheta, im_Etheta, re_Ephi, im_Ephi
#   meta keys    : title, frequency_mhz, wavelength_m, ground_type,
#                  input_impedance, swr, gain_peak_dbi,
#                  e_theta_max, e_phi_max, e_total_max, ntheta, nphi,
#                  + all derived display strings from finalize_meta()
#
# This module is intentionally standalone: nothing else in the codebase
# imports from its internals, only from this (meta, df) contract. It can
# be deleted at any time (e.g. once NEC5 validation is done) without
# touching data_reader.py, plot_panel.py, or the core plotting pipeline --
# only the optional comparison feature in neomom_plot.py goes away
# (see the try/except import guard there).
#
# ==========================================================================
# BUG FIX (2024-xx) — full-sphere data was being silently truncated
# ==========================================================================
# Near pattern nulls (TOTAL gain = -999.99), NEC5 omits the SENSE
# (LEFT/RIGHT) column entirely -- polarization sense is undefined there.
# That drops the row's field count from 12 to 11. An earlier version of
# this parser assumed a fixed column count, choked on the first such row,
# and silently stopped -- returning only 36 of 5329 rows (one partial
# phi=0 cut instead of the full 73-theta x 73-phi sphere). Fixed by
# branching on field count instead of assuming SENSE is always present.

import re
import math
import os

import numpy as np
import pandas as pd

from data_reader import finalize_meta, validate_pattern_data


def _first_match(text, pattern, cast=float, flags=0):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    try:
        return cast(m.group(1))
    except (ValueError, TypeError):
        return None


def _parse_title(lines):
    """
    Title = the first CM-comment line of the deck, found by anchoring on
    file structure rather than guessing at decoration patterns: locate
    the 'NUMERICAL ELECTROMAGNETICS CODE' banner, then the next
    all-asterisk divider line after it, then the first non-blank line
    after that divider.
    """
    idx_banner = None
    for i, l in enumerate(lines[:80]):
        if 'NUMERICAL ELECTROMAGNETICS' in l.upper():
            idx_banner = i
            break
    if idx_banner is None:
        return None

    idx_div = None
    for i in range(idx_banner + 1, min(idx_banner + 30, len(lines))):
        s = lines[i].strip()
        if s and set(s) <= {'*'}:
            idx_div = i
            break
    if idx_div is None:
        return None

    for i in range(idx_div + 1, min(idx_div + 15, len(lines))):
        s = lines[i].strip()
        if s and not (set(s) <= {'*'}):
            return s
    return None


def _parse_ground_type(text):
    """
    Ground type as NEC5 actually computed it for this run -- scoped to
    the 'ANTENNA ENVIRONMENT' section specifically. Earlier versions
    searched the whole file text and false-matched explanatory GN/GE
    card documentation that some NEC front-ends (e.g. nml_to_nec.py)
    embed as CM comment lines near the top of the deck -- that text
    describes card SYNTAX, not what this particular run used.
    """
    m = re.search(r'ANTENNA ENVIRONMENT.*?(?=- - - STRUCTURE IMPEDANCE|\Z)',
                  text, re.IGNORECASE | re.DOTALL)
    section = m.group(0) if m else text

    if re.search(r'FREE\s*SPACE', section, re.IGNORECASE):
        return 'FREE_SPACE'
    if re.search(r'PERFECT\s*GROUND', section, re.IGNORECASE):
        return 'PERFECT_GROUND'
    if re.search(r'FINITE GROUND|SOMMERFELD', section, re.IGNORECASE):
        return 'REAL_GROUND'
    return 'FREE_SPACE'


def _parse_impedance(lines):
    """
    Find the ANTENNA INPUT PARAMETERS data row and pull impedance
    real/imag by POSITION FROM THE END of the token list (POWER is
    last, then admittance imag/real, then impedance imag/real) rather
    than a fixed total column count, since the leading TAG/SEG columns
    have varied across NEC5 output samples.
    """
    for i, l in enumerate(lines):
        if 'ANTENNA INPUT PARAMETERS' in l:
            for j in range(i + 1, min(i + 8, len(lines))):
                toks = lines[j].split()
                if len(toks) < 6:
                    continue
                try:
                    floats = [float(t) for t in toks]
                except ValueError:
                    continue
                if len(floats) >= 5:
                    z_real, z_imag = floats[-5], floats[-4]
                    return complex(z_real, z_imag)
            break
    return None


def read_nec_out(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Cannot find file: {filepath}")

    with open(filepath, encoding='utf-8', errors='replace') as f:
        text = f.read()
    lines = text.split('\n')

    meta = {'source': 'nec5', 'filepath': filepath}

    meta['title'] = _parse_title(lines) or os.path.basename(filepath)
    meta['frequency_mhz'] = _first_match(text, r'FREQUENCY=\s*([\d.Ee+-]+)\s*MHZ')
    meta['wavelength_m']  = _first_match(text, r'WAVELENGTH=\s*([\d.Ee+-]+)\s*METERS')
    meta['ground_type']   = _parse_ground_type(text)

    z = _parse_impedance(lines)
    if z is not None:
        meta['input_impedance'] = z
        z0 = 50.0
        gamma = abs((z - z0) / (z + z0))
        if gamma < 0.999999:
            meta['swr'] = (1.0 + gamma) / (1.0 - gamma)

    # ------------------------------------------------------------
    # RADIATION PATTERNS data block
    # ------------------------------------------------------------
    start = None
    for i, l in enumerate(lines):
        if 'RADIATION PATTERNS' in l:
            start = i
            break
    if start is None:
        raise ValueError('No RADIATION PATTERNS section found in file')

    theta_l, phi_l = [], []
    re_et_l, im_et_l, re_ep_l, im_ep_l = [], [], [], []
    total_db_l = []

    for line in lines[start:]:
        s = line.strip()
        if not s or not s[0].isdigit():
            continue
        parts = s.split()

        if len(parts) == 12:
            # theta phi vert hor total axial tilt SENSE magE phE magP phP
            theta, phi, _vert, _hor, total, _axial, _tilt, _sense, magE, phE, magP, phP = parts
        elif len(parts) == 11:
            # SENSE column absent (undefined polarization at a pattern null)
            theta, phi, _vert, _hor, total, _axial, _tilt, magE, phE, magP, phP = parts
        else:
            # Unrecognized layout -- skip defensively rather than aborting
            # the whole parse (matches the bug-fix philosophy: never let
            # one malformed row silently truncate the rest of the sphere).
            continue

        theta_f = float(theta)
        phi_f   = float(phi)
        magE_f, phE_rad = float(magE), math.radians(float(phE))
        magP_f, phP_rad = float(magP), math.radians(float(phP))

        theta_l.append(theta_f)
        phi_l.append(phi_f)
        re_et_l.append(magE_f * math.cos(phE_rad))
        im_et_l.append(magE_f * math.sin(phE_rad))
        re_ep_l.append(magP_f * math.cos(phP_rad))
        im_ep_l.append(magP_f * math.sin(phP_rad))
        total_db_l.append(float(total))

    if not theta_l:
        raise ValueError('No data rows parsed from RADIATION PATTERNS section '
                          '-- file may be truncated or in an unexpected format')

    df = pd.DataFrame({
        'theta_deg': theta_l,
        'phi_deg':   phi_l,
        're_Etheta': re_et_l,
        'im_Etheta': im_et_l,
        're_Ephi':   re_ep_l,
        'im_Ephi':   im_ep_l,
    })

    meta['ntheta'] = len(set(theta_l))
    meta['nphi']   = len(set(phi_l))

    # Peak gain / angle: use NEC5's own TOTAL(dB) column directly rather
    # than re-deriving an absolute gain figure from |E| alone -- NEC5's
    # TOTAL already folds in its own power normalization (structure loss,
    # ground loss, etc.), which raw field magnitude doesn't carry.
    total_db = np.array(total_db_l)
    idx_peak = int(np.argmax(total_db))
    meta['gain_peak_dbi'] = float(total_db[idx_peak])
    meta['e_total_max']   = (float(theta_l[idx_peak]), float(phi_l[idx_peak]))

    et_mag = np.hypot(np.array(re_et_l), np.array(im_et_l))
    ep_mag = np.hypot(np.array(re_ep_l), np.array(im_ep_l))
    idx_et = int(np.argmax(et_mag))
    idx_ep = int(np.argmax(ep_mag))
    meta['e_theta_max'] = (float(theta_l[idx_et]), float(phi_l[idx_et]))
    meta['e_phi_max']   = (float(theta_l[idx_ep]), float(phi_l[idx_ep]))

    meta = finalize_meta(meta)

    validate_pattern_data(meta, df, filepath)

    return meta, df


if __name__ == '__main__':
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else \
        '/mnt/user-data/uploads/goat_loop_NEC_REAL_GND.out'

    meta, df = read_nec_out(filepath)

    print(f"\nReading: {filepath}\n")
    print("--- METADATA ---")
    for k, v in meta.items():
        print(f"  {k:20s} : {v}")

    print(f"\n--- DATA FRAME ---")
    print(f"  Shape   : {df.shape}")
    print(f"  Columns : {list(df.columns)}")
    print(f"  theta   : {df['theta_deg'].min():.1f} -> {df['theta_deg'].max():.1f} deg "
          f"({df['theta_deg'].nunique()} unique)")
    print(f"  phi     : {df['phi_deg'].min():.1f} -> {df['phi_deg'].max():.1f} deg "
          f"({df['phi_deg'].nunique()} unique)")