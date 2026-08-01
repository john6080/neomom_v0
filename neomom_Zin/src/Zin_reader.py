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


def read_s1p_file(filepath, Z0_line=50.0):
    """
    Parse a Touchstone .s1p file (standard 1-port VNA export format --
    NanoVNA, RigExpert, VNWA, most bench VNAs all support this).

    Touchstone format:
        ! comment lines (anywhere)
        # <freq_unit> S <format> R <Z0>        -- exactly one option line
            freq_unit : HZ | KHZ | MHZ | GHZ
            format    : RI (real/imag) | MA (mag/angle deg) | DB (dB/angle deg)
            Z0        : reference impedance the VNA calibrated to [Ohm]
        freq  S11_1  S11_2                     -- one row per frequency point

    S11 here is the raw reflection coefficient AT THE VNA'S REFERENCE
    PLANE -- i.e. measured through whatever coax/balun sits between the
    VNA and the antenna. No de-embedding is applied by this reader; use
    apply_port_extension() afterward if you want to rotate the reference
    plane out to the antenna terminals.

    Parameters
    ----------
    filepath : str
    Z0_line  : float, fallback reference impedance [Ohm] if the file's
               '# ... R <Z0>' option is missing or unparsable (rare;
               most exports include it). Default 50.0.

    Returns
    -------
    meta : dict  -- same shape as read_Zin_file()/read_eznec_file(), plus
                    meta['z0_vna_ohm'] : the VNA's calibration reference Z0
    data : dict of 1-D numpy arrays -- same keys as read_Zin_file()

    Raises
    ------
    FileNotFoundError, ValueError
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Cannot find file: {filepath}')

    with open(filepath, 'r', errors='ignore') as f:
        lines = [l.rstrip('\n') for l in f.readlines()]

    freq_unit = 'MHZ'
    fmt       = 'MA'
    z0_vna    = Z0_line
    saw_option_line = False

    rows = []

    for line in lines:
        s = line.strip()
        if not s or s.startswith('!'):
            continue

        if s.startswith('#'):
            # Option line, e.g. "# MHz S RI R 50"
            toks = s[1:].split()
            for i, t in enumerate(toks):
                tu = t.upper()
                if tu in ('HZ', 'KHZ', 'MHZ', 'GHZ'):
                    freq_unit = tu
                elif tu in ('RI', 'MA', 'DB'):
                    fmt = tu
                elif tu == 'R' and i + 1 < len(toks):
                    try:
                        z0_vna = float(toks[i + 1])
                    except ValueError:
                        pass
            saw_option_line = True
            continue

        # Data row: freq  val1  val2   (1-port -- exactly 3 numbers)
        try:
            vals = [float(v) for v in s.replace(',', ' ').split()]
        except ValueError:
            continue
        if len(vals) >= 3:
            rows.append(vals[:3])

    if not rows:
        raise ValueError(f'No data rows found in: {filepath}')
    if not saw_option_line:
        raise ValueError(
            f"'{filepath}' has no Touchstone '# ...' option line -- "
            f"doesn't look like a valid .s1p file.")

    arr = np.array(rows, dtype=float)

    unit_scale = {'HZ': 1e-6, 'KHZ': 1e-3, 'MHZ': 1.0, 'GHZ': 1e3}[freq_unit]
    freq_mhz = arr[:, 0] * unit_scale

    if fmt == 'RI':
        S11 = arr[:, 1] + 1j * arr[:, 2]
    elif fmt == 'MA':
        S11 = arr[:, 1] * np.exp(1j * np.radians(arr[:, 2]))
    elif fmt == 'DB':
        mag = 10.0 ** (arr[:, 1] / 20.0)
        S11 = mag * np.exp(1j * np.radians(arr[:, 2]))
    else:
        raise ValueError(f"Unrecognized Touchstone format '{fmt}'")

    Zin_cpx = z0_vna * (1.0 + S11) / (1.0 - S11)
    Rin = np.real(Zin_cpx)
    Xin = np.imag(Zin_cpx)

    Zin_mag = np.abs(Zin_cpx)
    Yin_cpx = np.where(Zin_mag > 0, 1.0 / Zin_cpx, 0j)
    Gin     = np.real(Yin_cpx)
    Bin     = np.imag(Yin_cpx)
    Yin_mag = np.abs(Yin_cpx)
    SWR     = compute_swr(Rin, Xin, Z0=z0_vna)

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

    meta = {
        'source_type' : 'vna',
        'title'       : os.path.splitext(os.path.basename(filepath))[0],
        'nfreq'       : len(freq_mhz),
        'fstart_mhz'  : float(freq_mhz[0]),
        'fstop_mhz'   : float(freq_mhz[-1]),
        'fstep_mhz'   : float(freq_mhz[1] - freq_mhz[0]) if len(freq_mhz) > 1 else 0.0,
        'z0_ref_ohm'  : z0_vna,
        'z0_vna_ohm'  : z0_vna,
    }
    meta['f_res_mhz']     = _find_zero_crossing(freq_mhz, Bin)
    idx_swr               = int(np.argmin(SWR))
    meta['swr_min']       = float(SWR[idx_swr])
    meta['f_swr_min_mhz'] = float(freq_mhz[idx_swr])
    meta['Rin_res']       = _interpolate_at(freq_mhz, Rin, meta['f_res_mhz'])

    return meta, data


# ------------------------------------------------------------------
# Port extension (de-embed a length of feedline back to the antenna)
# ------------------------------------------------------------------

def apply_port_extension(freq_mhz, Rin, Xin, Z0_line=50.0,
                         length_m=0.0, vf=0.66, loss_db_per_100m=0.0):
    """
    Rotate a measured (Rin, Xin) sweep -- taken at the far end of a
    feedline, e.g. in the shack -- back to the antenna terminals, by
    undoing the transmission-line transformation of `length_m` of line
    with velocity factor `vf` and (optionally) matched-line loss
    `loss_db_per_100m`.

    Physics
    -------
    Gamma_meas is the reflection coefficient measured at the VNA, with
    reference impedance Z0_line (the line's own characteristic
    impedance -- normally the same as the VNA's calibration Z0, e.g.
    50 Ohm, for a well-matched-Z0 coax).

    For a uniform line of complex propagation constant
        gamma = alpha + j*beta
    the reflection coefficient transforms along the line as
        Gamma(z) = Gamma_load * exp(-2*gamma*z)
    measured looking from a distance z in front of the load. Since the
    VNA is `length_m` of line AWAY from the antenna (the load), we
    invert this to recover the antenna-plane Gamma from the measured
    (VNA-plane) Gamma:
        Gamma_antenna = Gamma_meas * exp(+2*gamma*length_m)

    The +2*alpha*length_m term restores the magnitude lost to cable
    attenuation (a real, physical amplification of the recovered
    Gamma -- not a fudge factor); the +2*beta*length_m term undoes the
    phase rotation, which is the part that matters even for lossless
    "ideal" coax.

    Only phase rotation (loss_db_per_100m=0) is exact for a genuinely
    lossless line. The loss term uses a simple matched-line
    approximation (uniform attenuation regardless of local mismatch,
    i.e. this does NOT account for the loss-vs-standing-wave
    interaction that occurs on a badly mismatched line) -- adequate
    for typical ham SWR ranges and cable lengths, not a substitute for
    full lossy-line ABCD-matrix de-embedding on an extreme mismatch.

    Parameters
    ----------
    freq_mhz          : 1-D array, frequency [MHz]
    Rin, Xin          : 1-D arrays, MEASURED impedance at the VNA [Ohm]
    Z0_line           : float, line characteristic impedance [Ohm]
                         (== VNA calibration Z0 for a well-matched line)
    length_m          : float, physical cable length [m]
    vf                : float, cable velocity factor (0 < vf <= 1);
                         typical: solid PE coax ~0.66, foam ~0.78-0.85,
                         hardline ~0.88-0.92
    loss_db_per_100m  : float, matched-line attenuation at the sweep's
                         center frequency [dB / 100 m]; 0.0 disables
                         the loss correction (pure phase de-embed only)

    Returns
    -------
    Rin_corrected, Xin_corrected : 1-D arrays, impedance AT THE ANTENNA

    Warns (prints to stdout, does not raise)
    -----------------------------------------
    If the corrected |Gamma| exceeds 1.0 anywhere -- physically
    impossible for a passive antenna -- this most often means
    length_m/vf/loss are wrong, not that the antenna itself is active.
    Values are left uncorrected in magnitude (clipped) rather than
    silently producing a negative-resistance result.
    """
    freq_mhz = np.asarray(freq_mhz, dtype=float)
    Rin      = np.asarray(Rin, dtype=float)
    Xin      = np.asarray(Xin, dtype=float)

    if length_m <= 0.0:
        return Rin.copy(), Xin.copy()

    c = 299792458.0                       # speed of light [m/s]
    f_hz = freq_mhz * 1.0e6

    beta = 2.0 * np.pi * f_hz / (vf * c)  # phase constant [rad/m]

    # Attenuation constant [Np/m] from dB/100m at the given frequency.
    # Coax loss is not flat with frequency in reality (skin effect ~sqrt(f),
    # dielectric loss ~f); this treats loss_db_per_100m as already being
    # the value AT THE SWEEP FREQUENCIES of interest (e.g. read off a
    # cable's published loss chart at your band), not frequency-scaled here.
    alpha = (loss_db_per_100m / 100.0) / 8.685889638 if loss_db_per_100m > 0 else 0.0

    Zin_meas  = Rin + 1j * Xin
    Gamma_meas = (Zin_meas - Z0_line) / (Zin_meas + Z0_line)

    rotation = np.exp(2.0 * (alpha + 1j * beta) * length_m)
    Gamma_antenna = Gamma_meas * rotation

    mag = np.abs(Gamma_antenna)
    n_bad = int(np.sum(mag >= 1.0))
    if n_bad > 0:
        print(f'  apply_port_extension: WARNING -- |Gamma| >= 1.0 at '
              f'{n_bad} point(s) after correction. Check length_m/vf/loss_db_per_100m '
              f'-- a passive antenna cannot have |Gamma| >= 1.')
        mag_clipped = np.clip(mag, 0.0, 0.9999)
        Gamma_antenna = Gamma_antenna * (mag_clipped / np.where(mag > 0, mag, 1.0))

    Zin_antenna = Z0_line * (1.0 + Gamma_antenna) / (1.0 - Gamma_antenna)

    return np.real(Zin_antenna), np.imag(Zin_antenna)


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

    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.s1p', '.s2p'):
        return read_s1p_file(filepath)

    with open(filepath, 'r', errors='ignore') as f:
        first_line = f.readline()

    if 'EZNEC' in first_line.upper():
        return read_eznec_file(filepath)
    elif first_line.strip().startswith('#') and 'S' in first_line.upper() \
            and any(u in first_line.upper() for u in ('HZ', 'RI', 'MA', 'DB')):
        # Touchstone option line without an .s1p extension
        return read_s1p_file(filepath)
    else:
        return read_Zin_file(filepath)


# ------------------------------------------------------------------
# SweepData factory functions
# ------------------------------------------------------------------

def sweep_from_file(filepath, name=None, color='#1f77b4', linestyle='-',
                    port_ext_length_m=0.0, port_ext_vf=0.66,
                    port_ext_loss_db_per_100m=0.0):
    """
    Auto-detect file type, read it, and return a SweepData object.

    Parameters
    ----------
    filepath  : str   path to NeoMoM _Zin.csv, EZNEC .txt, or VNA .s1p
    name      : str   display name; defaults to filename stem
    color     : str   matplotlib color
    linestyle : str   matplotlib line style
    port_ext_length_m, port_ext_vf, port_ext_loss_db_per_100m :
              Port-extension (de-embedding) parameters -- see
              apply_port_extension(). Only meaningful for VNA-sourced
              data (source_type == 'vna'); ignored for NeoMoM/EZNEC
              model output, which is already referenced to the antenna
              terminals. length_m=0.0 (default) applies no correction.

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

    Rin, Xin = data['Rin'], data['Xin']

    if source == 'vna' and port_ext_length_m > 0.0:
        Z0_line = meta.get('z0_vna_ohm', 50.0)
        Rin, Xin = apply_port_extension(
            data['freq_mhz'], Rin, Xin, Z0_line=Z0_line,
            length_m=port_ext_length_m, vf=port_ext_vf,
            loss_db_per_100m=port_ext_loss_db_per_100m)
        meta['port_ext_applied']    = True
        meta['port_ext_length_m']   = port_ext_length_m
        meta['port_ext_vf']         = port_ext_vf
        meta['port_ext_loss_db_100m'] = port_ext_loss_db_per_100m
        # Recompute resonance/SWR-min metadata against the corrected data
        Zin_cpx = Rin + 1j * Xin
        Yin_cpx = np.where(np.abs(Zin_cpx) > 0, 1.0 / Zin_cpx, 0j)
        Bin_corr = np.imag(Yin_cpx)
        meta['f_res_mhz'] = _find_zero_crossing(data['freq_mhz'], Bin_corr)
        meta['Rin_res']   = _interpolate_at(data['freq_mhz'], Rin, meta['f_res_mhz'])

    return SweepData(
        name      = name,
        filepath  = filepath,
        source    = source,
        meta      = meta,
        freq_mhz  = data['freq_mhz'],
        Rin       = Rin,
        Xin       = Xin,
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