# pattern_math.py
#
# Purpose: Compute field quantities and amplitude scales from raw
#          complex E-field components.
#
# This module knows about math only.
# No GUI, no plotting, no file I/O.


import numpy as np
import pandas as pd


# ----------------------------------------------------------------
# SECTION 1: Field component magnitudes
# ----------------------------------------------------------------
# These are the three user-selectable field quantities.
# Input is the raw DataFrame from data_reader.
# Each function adds a column 'E_mag' to a copy of the DataFrame.
#
# Why copies?  So the caller always gets a clean result and the
# original df is never modified.  Safe for multiple plot windows
# using the same data simultaneously.

def compute_Ev(df):
    """
    Vertical polarization magnitude: |E_theta|
    E_theta is the co-polar component for a vertical antenna.
    """
    out = df.copy()
    out['E_mag'] = np.sqrt(df['re_Etheta']**2 + df['im_Etheta']**2)
    return out


def compute_Eh(df):
    """
    Horizontal polarization magnitude: |E_phi|
    E_phi is the co-polar component for a horizontal antenna.
    """
    out = df.copy()
    out['E_mag'] = np.sqrt(df['re_Ephi']**2 + df['im_Ephi']**2)
    return out


def compute_Etotal(df):
    """
    Total field magnitude: sqrt(|E_theta|^2 + |E_phi|^2)
    Polarization-independent total radiated field.
    """
    out = df.copy()
    Etheta_mag = np.sqrt(df['re_Etheta']**2 + df['im_Etheta']**2)
    Ephi_mag   = np.sqrt(df['re_Ephi']**2   + df['im_Ephi']**2)
    out['E_mag'] = np.sqrt(Etheta_mag**2 + Ephi_mag**2)
    return out


# Lookup dict so GUI can select by string name
FIELD_COMPONENTS = {
    'Ev'     : compute_Ev,
    'Eh'     : compute_Eh,
    'Etotal' : compute_Etotal,
}


# ----------------------------------------------------------------
# SECTION 2: Amplitude scales
# ----------------------------------------------------------------
# All scale functions take a pandas Series of linear |E| magnitudes
# and return a new Series in the requested scale.
#
# IMPORTANT: We add a small epsilon before log operations to avoid
# log(0) = -inf on true nulls in the pattern.  1e-30 is well below
# any physically meaningful signal so it never distorts real data.

EPSILON = 1e-30


def scale_linear(E_mag, meta=None):
    """
    Linear scale. Normalized to 1.0 at pattern peak.
    Uses _peak_emag_no_zenith from meta if available to exclude
    the theta=0 singularity from the normalization reference.
    """
    if meta is not None and '_peak_emag_no_zenith' in meta:
        peak = meta['_peak_emag_no_zenith']
    else:
        peak = float(E_mag.max())
    if peak == 0:
        return E_mag.copy()
    return E_mag / peak


def scale_db_peak(E_mag, meta=None):
    """
    dB relative to pattern peak.
    Peak = 0 dB.  Deep nulls clipped to -999 dB floor.
    20*log10 because E is a field quantity (not power).
    Uses _peak_emag_no_zenith from meta if available.
    """
    if meta is not None and '_peak_emag_no_zenith' in meta:
        peak = meta['_peak_emag_no_zenith']
    else:
        peak = float(E_mag.max())
    if peak == 0:
        return pd.Series(np.full(len(E_mag), -999.0))
    db = 20.0 * np.log10((E_mag + EPSILON) / peak)
    return db.clip(lower=-999.0)   # finite floor, no -inf

def scale_dbi(E_mag, meta):
    """
    Absolute gain scale in dBi.
    Uses gain_peak_dBi from metadata to anchor the pattern.
    dBi = dB_peak_relative + gain_peak_dBi
    Requires meta dict with 'gain_peak_dbi' key.
    """
    db_rel = scale_db_peak(E_mag, meta)
    gain   = meta.get('gain_peak_dbi', 0.0)
    if not isinstance(gain, (int, float)):
        gain = 0.0
    return db_rel + gain


def scale_arrl(E_mag, meta=None):
    """
    ARRL format:
      - dB relative to peak (same as scale_db_peak)
      - Floor clipped at -40 dB
      - Intended for polar plots with 8 rings at 5 dB each
    Values below -40 dB are set to -40 dB (not -inf).
    This is the standard format in ARRL Antenna Book plots.
    """
    db = scale_db_peak(E_mag, meta)
    return db.clip(lower=-40.0)


# Lookup dict so GUI can select by string name
AMPLITUDE_SCALES = {
    'Linear'  : scale_linear,
    'dB peak' : scale_db_peak,
    'dBi'     : scale_dbi,
    'ARRL'    : scale_arrl,
}

ARRL_FLOOR = -40.0   # exported so plot module can use it for axis limits


# ----------------------------------------------------------------
# SECTION 3: Apply component + scale together
# ----------------------------------------------------------------
# This is the main entry point the GUI and plot modules will call.
# Returns a DataFrame with two extra columns:
#   'E_mag'    : linear field magnitude for the chosen component
#   'E_scaled' : amplitude in the chosen scale

def apply_component_and_scale(df, component, scale, meta):
    """
    Parameters
    ----------
    df        : raw DataFrame from data_reader
    component : string key from FIELD_COMPONENTS  e.g. 'Etotal'
    scale     : string key from AMPLITUDE_SCALES  e.g. 'ARRL'
    meta      : metadata dict from data_reader (needed for dBi)

    Returns
    -------
    out : DataFrame with original columns plus 'E_mag' and 'E_scaled'
    """
    if component not in FIELD_COMPONENTS:
        raise ValueError(f"Unknown component '{component}'. "
                         f"Choose from: {list(FIELD_COMPONENTS)}")
    if scale not in AMPLITUDE_SCALES:
        raise ValueError(f"Unknown scale '{scale}'. "
                         f"Choose from: {list(AMPLITUDE_SCALES)}")

    out        = FIELD_COMPONENTS[component](df)        # adds E_mag
    scale_func = AMPLITUDE_SCALES[scale]

    # Compute the global peak EXCLUDING theta=0 (zenith singularity).
    # At theta=0 the polar coordinate system is degenerate — all phi
    # directions converge to a single point and the engine can produce
    # numerical artifacts there that corrupt global normalization.
    # Use theta>0 rows to find the true pattern peak, then normalize
    # ALL rows (including theta=0) to that peak.
    theta_col = 'theta_deg' if 'theta_deg' in out.columns else None
    if theta_col is not None:
        mask_valid = out[theta_col] > 0.0
        peak_emag  = out.loc[mask_valid, 'E_mag'].max()
    else:
        peak_emag = out['E_mag'].max()

    if not (peak_emag > 0.0):           # catches both 0.0 and NaN
        peak_emag = out['E_mag'].max()

    # Inject a corrected peak into meta for scale functions
    meta_with_peak = dict(meta)
    meta_with_peak['_peak_emag_no_zenith'] = float(peak_emag)

    out['E_scaled'] = scale_func(out['E_mag'], meta_with_peak)  # adds E_scaled

    return out


# ----------------------------------------------------------------
# SECTION 4: Grid reshape utility
# ----------------------------------------------------------------
# For 3D and heatmap plots we need E_scaled as a 2D array:
#   rows    = theta values
#   columns = phi values
#
# NOTE: this used to assume the DataFrame rows were theta-major
# (theta held constant while phi sweeps, then theta increments),
# matching the old Fortran engine's CSV row order, and reshaped with
# a plain .values.reshape(nTheta, nPhi). That broke silently when the
# CSV loop order was changed to phi-major to match NEC5 -- .reshape()
# doesn't know or care what order the rows are in, so it kept
# "succeeding" while quietly pairing every value with the wrong
# (theta, phi). Now we pivot on the actual theta_deg/phi_deg values
# instead, so the grid is correct regardless of row order.

def reshape_column_to_grid(out_df, column):
    """
    Reshape any single column of out_df into a 2D (nTheta, nPhi) array.

    This is the ONE place in the codebase that builds a (theta, phi)
    grid. Every caller that needs one -- E_scaled for color, E_mag for
    3D surface radius, or anything else -- should go through this
    function rather than reshaping inline, so any future change to
    the CSV row order only needs a fix (if any) in one place.

    Builds the grid via pandas.pivot() keyed on the actual theta_deg /
    phi_deg values rather than row position, so it's correct regardless
    of whether the source rows are theta-major or phi-major -- no
    assumption about loop/row order at all.

    Parameters
    ----------
    out_df : DataFrame with 'theta_deg', 'phi_deg', and `column`
    column : str, name of the column to reshape (e.g. 'E_scaled', 'E_mag')

    Returns
    -------
    theta_vals : 1D array of unique theta values (degrees), sorted
    phi_vals   : 1D array of unique phi values (degrees), sorted
    grid       : 2D array shape (nTheta, nPhi) of `column` values
    """
    theta_vals = np.sort(out_df['theta_deg'].unique())
    phi_vals   = np.sort(out_df['phi_deg'].unique())

    try:
        pivot = out_df.pivot(index='theta_deg', columns='phi_deg',
                             values=column)
    except ValueError as e:
        # pandas raises this if (theta_deg, phi_deg) pairs repeat --
        # a real data problem (duplicate rows), not an ordering issue.
        raise ValueError(
            f"Cannot build a (theta, phi) grid for '{column}': {e}. "
            f"This usually means the file has duplicate (theta, phi) "
            f"rows."
        )

    pivot = pivot.reindex(index=theta_vals, columns=phi_vals)

    if pivot.isna().any().any():
        n_missing = int(pivot.isna().sum().sum())
        n_total   = len(theta_vals) * len(phi_vals)
        raise ValueError(
            f"Cannot build a complete ({len(theta_vals)} theta x "
            f"{len(phi_vals)} phi) grid for '{column}' -- "
            f"{n_missing} of {n_total} (theta, phi) combinations are "
            f"missing from the data. File may be truncated or the "
            f"sweep isn't a full rectangular grid."
        )

    grid = pivot.values

    return theta_vals, phi_vals, grid


def reshape_to_grid(out_df, meta):
    """
    Reshape the E_scaled column into a 2D numpy array.

    Thin wrapper around reshape_column_to_grid() kept for backward
    compatibility with existing callers (plot_panel.py heatmap, etc.).
    `meta` is accepted but unused -- retained for call-signature compatibility.

    Returns
    -------
    theta_vals : 1D array of unique theta values (degrees)
    phi_vals   : 1D array of unique phi values (degrees)
    grid       : 2D array shape (nTheta, nPhi) of E_scaled values
    """
    return reshape_column_to_grid(out_df, 'E_scaled')


# ----------------------------------------------------------------
# SECTION 5: Command-line test
# ----------------------------------------------------------------
if __name__ == '__main__':
    import sys
    from data_reader import read_antenna_file

    if len(sys.argv) < 2:
        print("Usage: python3 pattern_math.py <antenna_file.csv>")
        sys.exit(1)

    meta, df = read_antenna_file(sys.argv[1])

    print("\n--- Testing all component + scale combinations ---\n")

    for comp in FIELD_COMPONENTS:
        for scale in AMPLITUDE_SCALES:
            out = apply_component_and_scale(df, comp, scale, meta)
            mn  = out['E_scaled'].min()
            mx  = out['E_scaled'].max()
            print(f"  {comp:8s} + {scale:8s} : "
                  f"min={mn:9.3f}  max={mx:9.3f}")

    print("\n--- Testing grid reshape (Etotal, ARRL) ---\n")
    out = apply_component_and_scale(df, 'Etotal', 'ARRL', meta)
    theta_vals, phi_vals, grid = reshape_to_grid(out, meta)
    print(f"  theta_vals : {len(theta_vals)} points  "
          f"{theta_vals[0]:.1f} to {theta_vals[-1]:.1f} deg")
    print(f"  phi_vals   : {len(phi_vals)} points  "
          f"{phi_vals[0]:.1f} to {phi_vals[-1]:.1f} deg")
    print(f"  grid shape : {grid.shape}")
    print(f"  grid min   : {grid.min():.3f}")
    print(f"  grid max   : {grid.max():.3f}")