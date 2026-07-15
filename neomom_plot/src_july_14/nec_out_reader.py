# nec_out_reader.py
#
# Purpose: Parse NEC5 .out file far-field pattern section and return
#          data in the same format as data_reader.read_antenna_file()
#          so neomom_plot can overlay NEC5 patterns alongside NeoMoM.
#
# NEC5 output columns (RADIATION PATTERNS section):
#   THETA  PHI  GAIN_VERT  GAIN_HOR  GAIN_TOTAL  AXIAL  TILT  SENSE
#   |Etheta|  phase_theta  |Ephi|  phase_phi
#
# NeoMoM CSV columns:
#   theta_deg  phi_deg  re_Etheta  im_Etheta  re_Ephi  im_Ephi
#
# Conversion: re = |E| * cos(phase_rad)
#             im = |E| * sin(phase_rad)

import re
import math
import numpy as np
import os


def read_nec_out(filepath):
    """
    Parse a NEC5 .out file and return pattern data in neomom format.

    Parameters
    ----------
    filepath : str — path to NEC5 .out file

    Returns
    -------
    meta : dict — matches keys from data_reader.read_antenna_file()
    data : dict — keys: theta, phi, re_Etheta, im_Etheta, re_Ephi, im_Ephi
                  plus gain_theta_db, gain_phi_db, gain_total_db

    Raises
    ------
    FileNotFoundError, ValueError
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Cannot find: {filepath}')

    with open(filepath, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    # ------------------------------------------------------------------
    # Parse metadata
    # ------------------------------------------------------------------
    meta = {
        'source'       : 'nec5',
        'filepath'     : filepath,
        'title'        : '',
        'freq_mhz'     : None,
        'ground'       : '',
        'gain_peak_dbi': None,
        'theta_peak'   : None,
        'phi_peak'     : None,
    }

    for line in lines:
        # Title from CM card echo
        m = re.search(r'^\s{20,}([A-Za-z].*\S)\s*$', line)
        if m and not meta['title'] and 'Generated' not in line:
            meta['title'] = m.group(1).strip()

        # Frequency
        m = re.search(r'FREQUENCY=\s*([\d.E+\-]+)\s*MHZ', line)
        if m:
            meta['freq_mhz'] = float(m.group(1))

        # Ground
        if 'REAL' in line.upper() and 'GROUND' not in meta['ground']:
            meta['ground'] = 'real'
        if 'FREE SPACE' in line.upper():
            meta['ground'] = 'free_space'
        if 'PERFECT' in line.upper() and 'GND' in line.upper():
            meta['ground'] = 'perfect'

    # ------------------------------------------------------------------
    # Find RADIATION PATTERNS section(s)
    # NEC5 outputs one section per frequency — take the last one
    # (matches the single FR card frequency)
    # ------------------------------------------------------------------
    pat_starts = []
    for i, line in enumerate(lines):
        if 'RADIATION PATTERNS' in line:
            pat_starts.append(i)

    if not pat_starts:
        raise ValueError('No RADIATION PATTERNS section found in NEC5 output')

    # Use the last pattern section
    pat_start = pat_starts[-1]

    # Data begins at offset +5 from section header:
    #  +0: "- - - RADIATION PATTERNS - - -"
    #  +1: blank
    #  +2: column header line 1
    #  +3: column header line 2 (THETA PHI ...)
    #  +4: units line (DEGREES DEGREES DB ...)
    #  +5: first data row
    DATA_OFFSET = 5

    rows = []
    for line in lines[pat_start + DATA_OFFSET:]:
        stripped = line.strip()
        if not stripped:
            break   # blank line = end of pattern block
        parts = stripped.split()
        if len(parts) < 12:
            break   # short line = end of data
        try:
            theta     = float(parts[0])
            phi       = float(parts[1])
            gain_v    = float(parts[2])
            gain_h    = float(parts[3])
            gain_tot  = float(parts[4])
            # parts[5]=axial  parts[6]=tilt  parts[7]=SENSE (text)
            mag_t     = float(parts[8])
            phase_t   = float(parts[9])
            mag_p     = float(parts[10])
            phase_p   = float(parts[11])
        except (ValueError, IndexError):
            break

        # Convert magnitude+phase → real+imaginary
        pt = math.radians(phase_t)
        pp = math.radians(phase_p)
        rows.append([
            theta, phi,
            mag_t * math.cos(pt), mag_t * math.sin(pt),
            mag_p * math.cos(pp), mag_p * math.sin(pp),
            gain_v, gain_h, gain_tot
        ])

    if not rows:
        raise ValueError('No data rows parsed from RADIATION PATTERNS section')

    arr = np.array(rows, dtype=float)

    data = {
        'theta'        : arr[:, 0],
        'phi'          : arr[:, 1],
        're_Etheta'    : arr[:, 2],
        'im_Etheta'    : arr[:, 3],
        're_Ephi'      : arr[:, 4],
        'im_Ephi'      : arr[:, 5],
        'gain_theta_db': arr[:, 6],
        'gain_phi_db'  : arr[:, 7],
        'gain_total_db': arr[:, 8],
    }

    # Peak gain
    idx_peak = int(np.argmax(arr[:, 8]))
    meta['gain_peak_dbi'] = float(arr[idx_peak, 8])
    meta['theta_peak']    = float(arr[idx_peak, 0])
    meta['phi_peak']      = float(arr[idx_peak, 1])

    return meta, data


# ------------------------------------------------------------------
# Self-test
# ------------------------------------------------------------------
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print('Usage: python3 nec_out_reader.py <file.out>')
        sys.exit(1)

    meta, data = read_nec_out(sys.argv[1])

    print('\n--- METADATA ---')
    for k, v in meta.items():
        print(f'  {k:20s} : {v}')

    print(f'\n--- DATA ---')
    print(f'  Rows      : {len(data["theta"])}')
    print(f'  Theta     : {data["theta"].min():.1f} to {data["theta"].max():.1f} deg')
    print(f'  Phi       : {data["phi"].min():.1f} to {data["phi"].max():.1f} deg')
    print(f'  Peak gain : {meta["gain_peak_dbi"]:.2f} dBi'
          f' @ theta={meta["theta_peak"]:.1f} phi={meta["phi_peak"]:.1f}')