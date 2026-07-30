# plot_panel.py
#
# Purpose: All plot types for antenna pattern visualization.
# Each function creates its own independent floating window.
# No GUI logic, no file I/O, no math beyond what pattern_math
# already computed.
#
# Caller always passes:
#   out_df  : DataFrame from pattern_math.apply_component_and_scale()
#             (has columns E_mag, E_scaled plus original columns)
#   meta    : metadata dict from data_reader
#   component : string e.g. 'Etotal'
#   scale     : string e.g. 'ARRL'
#   cut_angle : float, the angle value for this cut
#
# ==========================================================================
# BUG FIX — overlay normalization (2024-06)
# ==========================================================================
# Each call to apply_component_and_scale() normalises that component to
# ITS OWN peak.  On an overlay this means Eh (|E_phi| ~ 1e-6 V·m) maps
# to the OUTER RING, visually identical to Ev — making physically-zero
# Eh appear to have the same gain as Ev.
#
# Fix: _global_emag_peak() finds the maximum |E| across ALL components
# in the plotted slice.  _normalize_radii_from_emag() then maps every
# component against that SHARED reference so the relative levels are
# preserved.  Ev peaks at the outer ring; Eh (if truly null) appears at
# the centre.

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from display_config import cfg


# ----------------------------------------------------------------
# SECTION 1: Shared utilities
# ----------------------------------------------------------------

def make_title(meta, component, scale, cut_type, cut_angle):
    """
    Build a consistent two-line title for all plot windows.
    Line 1: antenna description
    Line 2: what this plot shows
    """
    title_str = meta.get('title', 'Antenna Pattern')
    freq      = meta.get('frequency_mhz', '?')
    gain      = meta.get('gain_peak_dbi', '?')
    gain_str  = f"{gain:.3g}" if isinstance(gain, float) else str(gain)

    if cut_type == 'Elevation':
        angle_str = f"phi = {cut_angle:.1f}°"
    elif cut_type == 'Azimuth':
        angle_str = f"theta = {cut_angle:.1f}°"
    else:
        angle_str = f"{cut_angle:.1f}°"

    line1 = f"{title_str}  |  {freq} MHz  |  {component}  |  {scale}"
    line2 = f"{cut_type} cut at {angle_str}   (peak gain: {gain_str} dBi)"
    return f"{line1}\n{line2}"


def db_polar_rings(ax, db_min, db_max=0):
    """
    Auto-scaled dB rings for non-ARRL dB scales.
    """
    dynamic_range = db_max - db_min
    if dynamic_range <= 20:
        spacing = 2
    elif dynamic_range <= 40:
        spacing = 5
    else:
        spacing = 10

    levels = np.arange(db_max, db_min, -spacing)
    for db in levels:
        r = (db - db_min) / (db_max - db_min)
        ax.text(np.radians(45), r, f"{db:.0f}",
                fontsize=cfg.font_annot, color='gray',
                ha='left', va='bottom')


# ----------------------------------------------------------------
# SECTION 2: Elevation cut  (theta varies, phi fixed)
# ----------------------------------------------------------------

def plot_elevation_cartesian(out_df, meta, component, scale, phi_cut):
    """
    Cartesian elevation cut: x = theta (deg), y = E_scaled.
    Plots full theta range present in data (0-90 or 0-180).
    """
    phi_vals    = out_df['phi_deg'].unique()
    nearest_phi = phi_vals[np.argmin(np.abs(phi_vals - phi_cut))]
    slice_df    = out_df[out_df['phi_deg'] == nearest_phi].copy()
    slice_df    = slice_df.sort_values('theta_deg')

    fig, ax = plt.subplots(figsize=cfg.fig_cart, dpi=cfg.mpl_dpi)
    fig.canvas.manager.set_window_title(
        f"Elevation Cut (Cartesian) - phi={nearest_phi:.1f}°")

    ax.plot(slice_df['theta_deg'], slice_df['E_scaled'],
            linewidth=cfg.lw_plot, color='steelblue')

    ax.set_xlabel('Elevation Angle θ (degrees)', fontsize=cfg.font_label)
    ax.set_ylabel(_scale_ylabel(scale), fontsize=cfg.font_label)
    ax.set_title(make_title(meta, component, scale,
                            'Elevation', nearest_phi),
               fontsize=cfg.font_title)
    ax.set_xlim(slice_df['theta_deg'].min(),
                slice_df['theta_deg'].max())
    _set_y_limits(ax, scale)
    ax.tick_params(axis='both', labelsize=cfg.font_tick)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))

    _add_peak_annotation(ax, slice_df, scale, coords='cartesian')
    fig.tight_layout()
    plt.show(block=False)


def plot_elevation_polar(out_df, meta, component, scale, phi_cut,
                         hemisphere='upper'):
    """
    Polar elevation cut.

    hemisphere : 'upper' — semicircle -90° to +90°
                 'full'  — full circle -180° to +180°
    """
    thetas_deg, E_scaled, nearest_phi = _build_elevation_cut(
        out_df, phi_cut, hemisphere)

    # Re-normalize to the peak within THIS cut so the plot fills
    # the outer ring and relative lobe sizes are clearly visible.
    # E_scaled is globally normalized (0-1 over full sphere) so
    # a weak-direction cut would otherwise appear undersized.
    cut_peak = np.max(np.abs(E_scaled))
    if cut_peak > 0:
        E_scaled = E_scaled / cut_peak

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                           subplot_kw={'projection': 'polar'})
    fig.canvas.manager.set_window_title(
        f"Elevation Cut (Polar) - phi={nearest_phi:.1f}° [{hemisphere}]")

    thetas_rad = np.radians(thetas_deg)
    radii      = _normalize_radii(E_scaled, scale)

    ax.plot(thetas_rad, radii, linewidth=cfg.lw_plot, color='steelblue')

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    if hemisphere == 'upper':
        ax.set_thetamin(-90)
        ax.set_thetamax(90)
    else:
        ax.set_thetamin(-180)
        ax.set_thetamax(180)

    _polar_grid_labels(ax, scale, E_scaled)
    _polar_ang_tick_params(ax)
    ax.set_title(make_title(meta, component, scale,
                            'Elevation', nearest_phi), pad=15, fontsize=cfg.font_title)
    fig.tight_layout()
    plt.show(block=False)


# ----------------------------------------------------------------
# SECTION 3: Azimuth cut  (phi varies, theta fixed)
# ----------------------------------------------------------------

def plot_azimuth_cartesian(out_df, meta, component, scale, theta_cut):
    """
    Cartesian azimuth cut: x = phi (deg), y = E_scaled.
    """
    theta_vals    = out_df['theta_deg'].unique()
    nearest_theta = theta_vals[np.argmin(np.abs(theta_vals - theta_cut))]
    slice_df      = out_df[out_df['theta_deg'] == nearest_theta].copy()
    slice_df      = slice_df.sort_values('phi_deg')

    fig, ax = plt.subplots(figsize=cfg.fig_cart, dpi=cfg.mpl_dpi)
    fig.canvas.manager.set_window_title(
        f"Azimuth Cut (Cartesian) - theta={nearest_theta:.1f}°")

    ax.plot(slice_df['phi_deg'], slice_df['E_scaled'],
            linewidth=cfg.lw_plot, color='darkorange')

    ax.set_xlabel('Azimuth Angle φ (degrees)', fontsize=cfg.font_label)
    ax.set_ylabel(_scale_ylabel(scale), fontsize=cfg.font_label)
    ax.set_title(make_title(meta, component, scale,
                            'Azimuth', nearest_theta),
               fontsize=cfg.font_title)
    ax.set_xlim(0, 360)
    ax.tick_params(axis='both', labelsize=cfg.font_tick)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(30))
    _set_y_limits(ax, scale)
    ax.grid(True, linestyle='--', alpha=0.5)

    _add_peak_annotation(ax, slice_df, scale, coords='cartesian')
    fig.tight_layout()
    plt.show(block=False)


def plot_azimuth_polar(out_df, meta, component, scale, theta_cut):

    """
    Polar azimuth cut: compass rose format, North=0°, clockwise.
    """
    theta_vals    = out_df['theta_deg'].unique()
    nearest_theta = theta_vals[np.argmin(np.abs(theta_vals - theta_cut))]
    slice_df      = out_df[out_df['theta_deg'] == nearest_theta].copy()
    slice_df      = slice_df.sort_values('phi_deg')

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                        subplot_kw={'projection': 'polar'})

    fig.canvas.manager.set_window_title(
        f"Azimuth Cut (Polar) - theta={nearest_theta:.1f}°")

    phis_rad = np.radians(slice_df['phi_deg'].values)
    radii    = _normalize_radii(slice_df['E_scaled'].values, scale)

    ax.plot(phis_rad, radii, linewidth=cfg.lw_plot, color='darkorange')
    ax.plot([phis_rad[-1], phis_rad[0]],
            [radii[-1],    radii[0]],
            linewidth=cfg.lw_plot, color='darkorange')

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    ax.set_thetagrids(range(0, 360, 30))
    _polar_ang_tick_params(ax)

    import matplotlib.ticker as ticker
    ax.minorticks_on()
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator(2))
    minor_locs = np.deg2rad(np.arange(0, 360, 10))
    ax.set_xticks(minor_locs, minor=True)
    ax.tick_params(axis='x', which='minor', length=4, width=0.8)

    _polar_grid_labels(ax, scale, slice_df['E_scaled'])
    ax.set_title(make_title(meta, component, scale,
                            'Azimuth', nearest_theta), pad=15, fontsize=cfg.font_title)

    fig.tight_layout()
    plt.show(block=False)


# ----------------------------------------------------------------
# SECTION 3b: Overlay plots — multiple components, same polar axes
# ----------------------------------------------------------------

def plot_elevation_polar_overlay(out_dict, meta, scale, phi_cut,
                                 hemisphere='upper'):
    """
    Elevation polar overlay. Plots any subset of Ev, Eh, Etotal.
    All components share a COMMON normalisation reference so that
    the relative levels between Ev, Eh, and Etotal are physically
    correct (Eh will not appear as large as Ev if it is truly null).

    Parameters
    ----------
    out_dict   : dict  {component_name: out_df}
    meta       : metadata dict
    scale      : scale string
    phi_cut    : desired phi angle (degrees)
    hemisphere : 'upper' (default) or 'full'

    If meta['source'] == 'nec5' (set by nec_out_reader.read_nec_out()),
    every line additionally gets small black dot markers and the title
    is tagged "[NEC5 data]". Without this, a solo NEC5 plot renders
    with the exact same colored lines as a solo NeoMoM plot -- fine
    stylistically, but genuinely easy to mistake for the other dataset
    at a glance, especially across multiple open plot windows. NeoMoM
    plots (meta without that key) are completely unaffected.
    """
    COLORS = {'Ev': 'steelblue', 'Eh': 'darkorange', 'Etotal': 'green'}
    is_nec5 = (meta.get('source') == 'nec5')

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                           subplot_kw={'projection': 'polar'},
                           constrained_layout=True)
    fig.get_layout_engine().set(w_pad=0.05, h_pad=0.05)

    nearest_phi = None
    all_E       = []

    # ------------------------------------------------------------------
    # Compute GLOBAL |E| peak across all components in this slice.
    # This is the key fix: every component is normalised to the same
    # reference, preserving physical relative levels.
    # ------------------------------------------------------------------
    global_emag = _global_emag_peak(out_dict,
                                    phi_cut=phi_cut,
                                    hemisphere=hemisphere)

    for comp, out_df in out_dict.items():
        thetas_deg, E_mag_slice, p_near = _build_elevation_cut_emag(
            out_df, phi_cut, hemisphere)
        if nearest_phi is None:
            nearest_phi = p_near

        thetas_rad = np.radians(thetas_deg)
        radii      = _normalize_radii_from_emag(E_mag_slice, global_emag, scale)

        line_kwargs = dict(linewidth=cfg.lw_plot,
                           color=COLORS.get(comp, 'gray'), label=comp)
        if is_nec5:
            line_kwargs.update(marker='o', markersize=3, markeredgewidth=0,
                               markerfacecolor='black')
        ax.plot(thetas_rad, radii, **line_kwargs)
        all_E.append(E_mag_slice)

    hemi_label = 'Upper hemisphere' if hemisphere == 'upper' \
                 else 'Full sphere'
    nec5_tag = ' [NEC5]' if is_nec5 else ''
    fig.canvas.manager.set_window_title(
        f"Elevation Cut (Polar) - phi={nearest_phi:.1f}° [{hemi_label}]{nec5_tag}")

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    if hemisphere == 'upper':
        ax.set_thetamin(-90)
        ax.set_thetamax(90)
        major_deg = np.arange(-90, 91, 30)
    else:
        ax.set_thetamin(-180)
        ax.set_thetamax(180)
        major_deg = np.arange(-180, 181, 30)

    ax.set_thetagrids(major_deg)
    _polar_ang_tick_params(ax)

    # Build ring labels from global_emag so they are in consistent units
    _polar_grid_labels_global(ax, scale, global_emag, meta)
    ax.legend(loc='lower right', fontsize=cfg.font_legend)

    title_str  = meta.get('title', 'Antenna Pattern')
    freq       = meta.get('frequency_mhz', '?')
    gain       = meta.get('gain_peak_dbi', '?')
    gain_str   = f"{gain:.3g}" if isinstance(gain, float) else str(gain)
    comp_str   = ' & '.join(out_dict.keys())
    source_tag = '  [NEC5 data]' if is_nec5 else ''
    ax.set_title(
        f"{title_str}  |  {freq} MHz  |  {comp_str}  |  {scale}{source_tag}\n"
        f"Elevation cut at phi = {nearest_phi:.1f}°  [{hemi_label}]"
        f"   (peak gain: {gain_str} dBi)",
        pad=15, fontsize=cfg.font_title)

    # Manual minor tick marks every 10° on outer ring
    if hemisphere == 'upper':
        minor_deg = np.arange(-90, 91, 10)
    else:
        minor_deg = np.arange(-180, 181, 10)

    major_set = set(major_deg)
    minor_deg = [d for d in minor_deg if d not in major_set]
    minor_rad = np.deg2rad(minor_deg)

    r_outer  = 1.0
    tick_len = 0.03

    for ang in minor_rad:
        ax.plot([ang, ang],
                [r_outer - tick_len, r_outer],
                color='gray',
                linewidth=cfg.lw_minor,
                solid_capstyle='butt',
                zorder=5,
                clip_on=False)

    plt.show(block=False)


def plot_azimuth_polar_overlay(out_dict, meta, scale, theta_cut):
    """
    Azimuth polar overlay. Plots any subset of Ev, Eh, Etotal.
    All components share a COMMON normalisation reference so that
    the relative levels between Ev, Eh, and Etotal are physically
    correct (Eh will not appear as large as Ev if it is truly null).

    See plot_elevation_polar_overlay() docstring: if meta['source'] ==
    'nec5', lines get small black dot markers and the title is tagged
    "[NEC5 data]" so a solo NEC5 plot is never confusable with a solo
    NeoMoM plot. NeoMoM plots are completely unaffected.
    """
    COLORS = {'Ev': 'steelblue', 'Eh': 'darkorange', 'Etotal': 'green'}
    is_nec5 = (meta.get('source') == 'nec5')

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                           subplot_kw={'projection': 'polar'},
                           constrained_layout=True)
    fig.get_layout_engine().set(w_pad=0.05, h_pad=0.05)

    nearest_theta = None

    # ------------------------------------------------------------------
    # Compute GLOBAL |E| peak across all components in this slice.
    # This is the key fix: every component is normalised to the same
    # reference, preserving physical relative levels.
    # ------------------------------------------------------------------
    global_emag = _global_emag_peak(out_dict, theta_cut=theta_cut)

    for comp, out_df in out_dict.items():
        theta_vals = out_df['theta_deg'].unique()
        nt         = theta_vals[np.argmin(np.abs(theta_vals - theta_cut))]
        if nearest_theta is None:
            nearest_theta = nt

        slice_df = out_df[out_df['theta_deg'] == nt].copy()
        slice_df = slice_df.sort_values('phi_deg')

        phis_rad = np.radians(slice_df['phi_deg'].values)
        radii    = _normalize_radii_from_emag(
                       slice_df['E_mag'].values, global_emag, scale)

        line_kwargs = dict(linewidth=cfg.lw_plot,
                           color=COLORS.get(comp, 'gray'), label=comp)
        if is_nec5:
            line_kwargs.update(marker='o', markersize=3, markeredgewidth=0,
                               markerfacecolor='black')
        ax.plot(phis_rad, radii, **line_kwargs)
        ax.plot([phis_rad[-1], phis_rad[0]],
                [radii[-1],    radii[0]],
                linewidth=cfg.lw_plot, color=COLORS.get(comp, 'gray'))

    nec5_tag = ' [NEC5]' if is_nec5 else ''
    fig.canvas.manager.set_window_title(
        f"Azimuth Cut (Polar) - theta={nearest_theta:.1f}°{nec5_tag}")

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_thetagrids(range(0, 360, 30))
    _polar_ang_tick_params(ax)

    _polar_grid_labels_global(ax, scale, global_emag, meta)

    ax.legend(loc='lower right', fontsize=cfg.font_legend)

    title_str  = meta.get('title', 'Antenna Pattern')
    freq       = meta.get('frequency_mhz', '?')
    gain       = meta.get('gain_peak_dbi', '?')
    gain_str   = f"{gain:.3g}" if isinstance(gain, float) else str(gain)
    comp_str   = ' & '.join(out_dict.keys())
    source_tag = '  [NEC5 data]' if is_nec5 else ''
    ax.set_title(
        f"{title_str}  |  {freq} MHz  |  {comp_str}  |  {scale}{source_tag}\n"
        f"Azimuth cut at theta = {nearest_theta:.1f}°"
        f"   (peak gain: {gain_str} dBi)",
        pad=15, fontsize=cfg.font_title)

    # Manual minor tick marks every 10° on outer ring
    minor_deg = np.arange(0, 360, 10)
    minor_rad = np.deg2rad(minor_deg)
    r_outer   = 1.0
    tick_len  = 0.03

    for ang in minor_rad:
        ax.plot([ang, ang],
                [r_outer - tick_len, r_outer],
                color='gray',
                linewidth=cfg.lw_minor,
                solid_capstyle='butt',
                zorder=5,
                clip_on=False)

    plt.show(block=False)


# ----------------------------------------------------------------
# SECTION 3c: Compare plots — same component(s), across TWO SOURCES
# (e.g. NeoMoM vs NEC5).
#
# Additive to Section 3b: the single-source overlay functions above are
# UNCHANGED and remain what's used whenever only one source is active,
# so behavior for anyone not using NEC5 comparison is identical to
# before this section existed.
#
# This whole section (plus nec_out_reader.py and the "Sources:" row in
# neomom_plot.py) can be deleted together to fully remove NEC5
# comparison support — nothing else in the codebase depends on it.
# ----------------------------------------------------------------

def _global_gain_peak_dbi(sources):
    """
    Max gain_peak_dbi across all active sources -- the physically
    meaningful "0 dB" reference point for a CROSS-ENGINE comparison.

    gain_peak_dbi is the one quantity that's actually comparable between
    two different EM engines: it's referenced to an isotropic radiator,
    independent of whatever internal convention each engine uses for
    raw field magnitude (reference distance, drive voltage, etc).
    Raw |E| is NOT safely comparable across engines for that reason --
    see _calibrated_reference() below.
    """
    peaks = [float(s['meta']['gain_peak_dbi'])
             for s in sources
             if isinstance(s['meta'].get('gain_peak_dbi'), (int, float))]
    return max(peaks) if peaks else 0.0


def _calibrated_reference(source_peak_emag, source_gain_peak_dbi, global_peak_dbi):
    """
    Per-source "effective global_peak" to hand to
    _normalize_radii_from_emag(), so that radii across MULTIPLE SOURCES
    are anchored to actual absolute dBi gain -- comparable across
    engines -- rather than to raw |E| field magnitude, which is NOT
    comparable across engines (different EM tools normalize the raw
    field differently even when their own dBi calibration is correct).

    ------------------------------------------------------------------
    BUG FIX (see conversation) — cross-source offset in compare plots
    ------------------------------------------------------------------
    An earlier version used ONE shared raw |E| peak across all sources
    (_global_emag_peak_multi, since removed). That's only valid if both
    sources' raw field data happens to share the same absolute
    normalization -- generally false between two different engines --
    and produced a constant dB offset between otherwise-matching curves
    (right shape, wrong absolute level) whenever it wasn't. This
    calibrates through each source's own gain_peak_dbi instead, which
    IS engine-independent, so the derived offset is real.

    Derivation: we want, for this source,
        20*log10(E_mag / X) == 20*log10(E_mag / source_peak_emag)
                                + (source_gain_peak_dbi - global_peak_dbi)
    for every E_mag (the E_mag-dependent term cancels identically),
    which solves to the single constant below.
    """
    if source_gain_peak_dbi is None:
        return source_peak_emag  # no absolute reference available -- fall back to raw
    return source_peak_emag * (10.0 ** ((global_peak_dbi - source_gain_peak_dbi) / 20.0))


def _source_line_style(index, source, comp, colors):
    """
    Rendering style for one (source, component) series in a compare plot,
    keyed on POSITION (index 0 = primary, e.g. NeoMoM; index > 0 =
    comparison overlay, e.g. NEC5) rather than on the source's name, so
    this generalizes past exactly "NeoMoM vs NEC5".

    index == 0 (primary source): full-weight solid line, colored by
    component -- exactly like every other plot in the app.

    index > 0 (comparison source): small black dot markers, NO
    connecting line, and NO per-component color -- deliberately. For a
    quick eyeball validation the question is just "does the reference
    data land on the model's curve", per component; a second full set
    of colored/dashed lines only doubles the number of near-identical
    curves you have to visually untangle. Uniform black dots read
    unambiguously as "the other dataset" at a glance, and which
    component a given dot belongs to is resolved by which colored line
    it lands on, not by its own color.
    """
    if index == 0:
        return dict(linewidth=cfg.lw_plot, alpha=1.0,
                    linestyle=source.get('linestyle', 'solid'),
                    marker='None', color=colors.get(comp, 'gray'),
                    zorder=3)

    return dict(linewidth=0, linestyle='None',
                marker='o', markersize=2, markeredgewidth=0,
                color='black', alpha=0.8, zorder=5)


def plot_elevation_polar_compare(sources, phi_cut, hemisphere='upper'):
    """
    Elevation polar comparison across multiple sources (e.g. NeoMoM vs
    NEC5), each possibly showing multiple components (Ev/Eh/Etotal).

    Parameters
    ----------
    sources : list of dict, each with keys:
        'name'      : str   e.g. 'NeoMoM' or 'NEC5' — used in legend/title
        'out_dict'  : {component: out_df}  (from compute_out_dicts())
        'meta'      : metadata dict for this source
        'scale'     : scale string — must be the same across all sources
        'linestyle' : matplotlib linestyle, e.g. 'solid' / 'dashed'
    phi_cut, hemisphere : same meaning as plot_elevation_polar_overlay()

    Color still encodes component (Ev/Eh/Etotal, matching the rest of
    the app); linestyle encodes source. Legend labels read e.g.
    "Etotal (NEC5)".
    """
    COLORS = {'Ev': 'steelblue', 'Eh': 'darkorange', 'Etotal': 'green'}
    scale  = sources[0]['scale']

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                           subplot_kw={'projection': 'polar'},
                           constrained_layout=True)
    fig.get_layout_engine().set(w_pad=0.05, h_pad=0.05)

    # Cross-engine calibration -- see _calibrated_reference() docstring.
    # Each source gets its OWN reference derived from its OWN
    # gain_peak_dbi; raw |E| is never compared directly across sources.
    global_peak_dbi = _global_gain_peak_dbi(sources)

    nearest_phi = None
    for i, s in enumerate(sources):
        source_peak_emag = _global_emag_peak(s['out_dict'], phi_cut=phi_cut,
                                             hemisphere=hemisphere)
        source_gain_peak_dbi = s['meta'].get('gain_peak_dbi')
        ref = _calibrated_reference(source_peak_emag, source_gain_peak_dbi,
                                    global_peak_dbi)

        for j, (comp, out_df) in enumerate(s['out_dict'].items()):
            thetas_deg, E_mag_slice, p_near = _build_elevation_cut_emag(
                out_df, phi_cut, hemisphere)
            if nearest_phi is None:
                nearest_phi = p_near

            thetas_rad = np.radians(thetas_deg)
            radii = _normalize_radii_from_emag(E_mag_slice, ref, scale)
            style = _source_line_style(i, s, comp, COLORS)

            # Comparison sources (i > 0) render as uniform black dots
            # with no per-component color -- one legend entry covers
            # all of that source's components rather than three
            # near-identical rows.
            if i == 0:
                label = f"{comp} ({s['name']})"
            else:
                label = s['name'] if j == 0 else '_nolegend_'

            ax.plot(thetas_rad, radii, label=label, **style)

    hemi_label = 'Upper hemisphere' if hemisphere == 'upper' else 'Full sphere'
    fig.canvas.manager.set_window_title(
        f"Elevation Cut (Compare) - phi={nearest_phi:.1f}° [{hemi_label}]")

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    if hemisphere == 'upper':
        ax.set_thetamin(-90)
        ax.set_thetamax(90)
        major_deg = np.arange(-90, 91, 30)
    else:
        ax.set_thetamin(-180)
        ax.set_thetamax(180)
        major_deg = np.arange(-180, 181, 30)

    ax.set_thetagrids(major_deg)
    _polar_ang_tick_params(ax)

    primary_meta = sources[0]['meta']
    # Ring labels must reflect the COMBINED reference, not just the
    # primary source's own peak, so 'dBi' ticks are correct for whichever
    # source is actually at the outer ring.
    label_meta = dict(primary_meta)
    label_meta['gain_peak_dbi'] = global_peak_dbi
    _polar_grid_labels_global(ax, scale, global_peak_dbi, label_meta)
    ax.legend(loc='lower right', fontsize=cfg.font_legend)

    title_str = primary_meta.get('title', 'Antenna Pattern')
    freq      = primary_meta.get('frequency_mhz', '?')
    src_str   = ' vs '.join(s['name'] for s in sources)
    peak_str  = '   '.join(
        f"{s['name']} peak: {s['meta']['gain_peak_dbi']:.3g} dBi"
        for s in sources
        if isinstance(s['meta'].get('gain_peak_dbi'), (int, float)))
    ax.set_title(
        f"{title_str}  |  {freq} MHz  |  {src_str}  |  {scale}\n"
        f"Elevation cut at phi = {nearest_phi:.1f}°  [{hemi_label}]"
        f"   ({peak_str})",
        pad=15, fontsize=cfg.font_title)

    if hemisphere == 'upper':
        minor_deg = np.arange(-90, 91, 10)
    else:
        minor_deg = np.arange(-180, 181, 10)
    major_set = set(major_deg)
    minor_deg = [d for d in minor_deg if d not in major_set]
    minor_rad = np.deg2rad(minor_deg)

    r_outer, tick_len = 1.0, 0.03
    for ang in minor_rad:
        ax.plot([ang, ang], [r_outer - tick_len, r_outer],
                color='gray', linewidth=cfg.lw_minor,
                solid_capstyle='butt', zorder=5, clip_on=False)

    plt.show(block=False)


def plot_azimuth_polar_compare(sources, theta_cut):
    """
    Azimuth polar comparison across multiple sources. Same contract as
    plot_elevation_polar_compare() above — see that docstring.
    """
    COLORS = {'Ev': 'steelblue', 'Eh': 'darkorange', 'Etotal': 'green'}
    scale  = sources[0]['scale']

    fig, ax = plt.subplots(figsize=cfg.fig_polar, dpi=cfg.mpl_dpi,
                           subplot_kw={'projection': 'polar'},
                           constrained_layout=True)
    fig.get_layout_engine().set(w_pad=0.05, h_pad=0.05)

    # Cross-engine calibration -- see _calibrated_reference() docstring.
    global_peak_dbi = _global_gain_peak_dbi(sources)

    nearest_theta = None
    for i, s in enumerate(sources):
        source_peak_emag     = _global_emag_peak(s['out_dict'], theta_cut=theta_cut)
        source_gain_peak_dbi = s['meta'].get('gain_peak_dbi')
        ref = _calibrated_reference(source_peak_emag, source_gain_peak_dbi,
                                    global_peak_dbi)

        for j, (comp, out_df) in enumerate(s['out_dict'].items()):
            theta_vals = out_df['theta_deg'].unique()
            nt = theta_vals[np.argmin(np.abs(theta_vals - theta_cut))]
            if nearest_theta is None:
                nearest_theta = nt

            slice_df = out_df[out_df['theta_deg'] == nt].copy()
            slice_df = slice_df.sort_values('phi_deg')

            phis_rad = np.radians(slice_df['phi_deg'].values)
            radii = _normalize_radii_from_emag(
                slice_df['E_mag'].values, ref, scale)
            style = _source_line_style(i, s, comp, COLORS)

            if i == 0:
                label = f"{comp} ({s['name']})"
            else:
                label = s['name'] if j == 0 else '_nolegend_'

            ax.plot(phis_rad, radii, label=label, **style)
            if i == 0:
                # Close the polar loop visually -- only meaningful for
                # continuous lines, not for the comparison source's
                # marker-only dots (each point is already drawn once).
                ax.plot([phis_rad[-1], phis_rad[0]], [radii[-1], radii[0]],
                        **style)

    fig.canvas.manager.set_window_title(
        f"Azimuth Cut (Compare) - theta={nearest_theta:.1f}°")

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_thetagrids(range(0, 360, 30))
    _polar_ang_tick_params(ax)

    primary_meta = sources[0]['meta']
    label_meta = dict(primary_meta)
    label_meta['gain_peak_dbi'] = global_peak_dbi
    _polar_grid_labels_global(ax, scale, global_peak_dbi, label_meta)
    ax.legend(loc='lower right', fontsize=cfg.font_legend)

    title_str = primary_meta.get('title', 'Antenna Pattern')
    freq      = primary_meta.get('frequency_mhz', '?')
    src_str   = ' vs '.join(s['name'] for s in sources)
    peak_str  = '   '.join(
        f"{s['name']} peak: {s['meta']['gain_peak_dbi']:.3g} dBi"
        for s in sources
        if isinstance(s['meta'].get('gain_peak_dbi'), (int, float)))
    ax.set_title(
        f"{title_str}  |  {freq} MHz  |  {src_str}  |  {scale}\n"
        f"Azimuth cut at theta = {nearest_theta:.1f}°   ({peak_str})",
        pad=15, fontsize=cfg.font_title)

    minor_deg = np.arange(0, 360, 10)
    minor_rad = np.deg2rad(minor_deg)
    r_outer, tick_len = 1.0, 0.03
    for ang in minor_rad:
        ax.plot([ang, ang], [r_outer - tick_len, r_outer],
                color='gray', linewidth=cfg.lw_minor,
                solid_capstyle='butt', zorder=5, clip_on=False)

    plt.show(block=False)


# ----------------------------------------------------------------
# SECTION 4: Heatmap  (theta vs phi, color = E_scaled)
# ----------------------------------------------------------------

def plot_heatmap(out_df, meta, component, scale):
    """
    2D heatmap: x = phi, y = theta, color = E_scaled.
    Works for upper hemisphere (theta 0-90) and full sphere (0-180).
    """
    from pattern_math import reshape_to_grid

    theta_vals, phi_vals, grid = reshape_to_grid(out_df, meta)

    fig, ax = plt.subplots(figsize=cfg.fig_heatmap, dpi=cfg.mpl_dpi)
    fig.canvas.manager.set_window_title("Heatmap")

    im = ax.imshow(grid,
                   aspect='auto',
                   origin='upper',
                   extent=[phi_vals[0], phi_vals[-1],
                           theta_vals[-1], theta_vals[0]],
                   cmap='jet')

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label(_scale_ylabel(scale), fontsize=cfg.font_label)

    ax.set_xlabel('Azimuth φ (degrees)', fontsize=cfg.font_label)
    ax.set_ylabel('Elevation θ (degrees)', fontsize=cfg.font_label)
    ax.set_title(make_title(meta, component, scale, 'Heatmap', 0)
                 .split('\n')[0], fontsize=cfg.font_title)

    ax.xaxis.set_major_locator(ticker.MultipleLocator(30))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.grid(True, linestyle='--', alpha=0.3, color='white')

    fig.tight_layout()
    plt.show(block=False)


# ----------------------------------------------------------------
# SECTION 5: Private helper functions
# ----------------------------------------------------------------

def _polar_ang_tick_params(ax):
    """
    Apply scaled font size and tightened padding to the angular (outer-ring)
    tick labels on a polar axes.
    """
    pad = max(int(cfg.font_tick * 0.3), 1)
    ax.tick_params(axis='x', which='major',
                   labelsize=cfg.font_tick, pad=pad)


def _scale_ylabel(scale):
    labels = {
        'Linear'  : 'Gain (normalized)',
        'dB peak' : 'dB relative to peak',
        'dBi'     : 'Gain (dBi)',
        'ARRL'    : 'dB relative to peak (ARRL)',
    }
    return labels.get(scale, 'Amplitude')


def _set_y_limits(ax, scale):
    """Set sensible y-axis limits for Cartesian plots by scale."""
    if scale == 'Linear':
        ax.set_ylim(0, 1.05)
    elif scale == 'dB peak':
        ax.set_ylim(-60, 5)
    elif scale == 'dBi':
        pass
    elif scale == 'ARRL':
        ax.set_ylim(-52, 2)


def _arrl_radius(db):
    """
    ARRL nonlinear radial mapping: R = 0.89^(-0.5 * db)
    db=0   -> R=1.000  (outer ring)
    db=-40 -> R=0.097
    db=-50 -> R=0.054  (maps to r=0)
    """
    return (0.89) ** (-0.5 * np.clip(db, -50.0, 0.0))


def _normalize_radii(E_scaled, scale, peak_override=None):
    """
    Convert E_scaled values to radii in [0, 1] for single-component
    polar plots.  Overlay plots use _normalize_radii_from_emag instead.
    """
    if scale == 'Linear':
        return np.clip(E_scaled ** 2, 0, 1)

    elif scale == 'ARRL':
        r_outer = _arrl_radius(0.0)
        r_floor = _arrl_radius(-50.0)
        r_raw   = _arrl_radius(np.clip(E_scaled, -50.0, 0.0))
        return (r_raw - r_floor) / (r_outer - r_floor)

    elif scale in ('dB peak', 'dBi'):
        floor = -40.0
        if scale == 'dB peak':
            peak = 0.0
        elif peak_override is not None:
            peak = peak_override
        else:
            peak = float(np.max(E_scaled))
        return np.clip((E_scaled - (peak - 40)) / 40.0, 0, 1)

    return E_scaled


def _normalize_radii_from_emag(E_mag, global_peak, scale):
    """
    Convert raw |E| magnitudes to polar radii [0, 1] using a SHARED
    global_peak so every component on an overlay occupies the same scale.

    Parameters
    ----------
    E_mag        : numpy array — linear |E| for ONE component (V·m)
    global_peak  : float       — max |E| across ALL overlay components
    scale        : 'ARRL' | 'dB peak' | 'dBi' | 'Linear'

    This replaces per-component self-normalisation in overlay functions
    and is the core fix for the Eh-appears-same-as-Ev bug.
    """
    # db relative to the global peak across all overlay components
    db = 20.0 * np.log10(np.maximum(E_mag, 1e-30) / global_peak)

    if scale == 'Linear':
        # radius = E / E_global_peak  (linear, power ~ radius²)
        r = np.maximum(E_mag, 0.0) / global_peak
        return np.clip(r ** 2, 0.0, 1.0)

    elif scale == 'ARRL':
        db     = np.clip(db, -50.0, 0.0)
        r_outer = _arrl_radius(0.0)
        r_floor = _arrl_radius(-50.0)
        r_raw   = _arrl_radius(db)
        return (r_raw - r_floor) / (r_outer - r_floor)

    elif scale in ('dB peak', 'dBi'):
        floor = -40.0
        # 0 dB (global peak) → r=1,  floor dB → r=0
        return np.clip((db - floor) / (-floor), 0.0, 1.0)

    # Fallback
    return np.clip(E_mag / global_peak, 0.0, 1.0)


def _global_emag_peak(out_dict, theta_cut=None, phi_cut=None,
                      hemisphere=None):
    """
    Find the maximum |E| magnitude across ALL components in out_dict,
    restricted to the slice being plotted.

    Parameters
    ----------
    out_dict   : {comp: out_df}  — DataFrames with 'E_mag' column
    theta_cut  : fixed theta for azimuth cut (degrees); None for elev
    phi_cut    : fixed phi for elevation cut (degrees); None for azim
    hemisphere : 'upper' | 'full' — used only for elevation cuts

    Returns
    -------
    global_peak : float  (V·m, same units as E_mag)
    """
    global_peak = 0.0

    for comp, out_df in out_dict.items():
        if theta_cut is not None:
            # Azimuth cut — slice at fixed theta
            tv  = out_df['theta_deg'].unique()
            nt  = tv[np.argmin(np.abs(tv - theta_cut))]
            sl  = out_df[out_df['theta_deg'] == nt]

        elif phi_cut is not None:
            # Elevation cut — slice at fixed phi PLUS back-azimuth phi+180°
            # Both halves are shown in the plot so the peak must
            # account for both directions.
            pv      = out_df['phi_deg'].unique()
            np_     = pv[np.argmin(np.abs(pv - phi_cut))]
            p_back  = (phi_cut + 180.0) % 360.0
            p_back  = pv[np.argmin(np.abs(pv - p_back))]
            sl_fwd  = out_df[out_df['phi_deg'] == np_]
            sl_back = out_df[out_df['phi_deg'] == p_back]
            if hemisphere == 'upper':
                sl_fwd  = sl_fwd [sl_fwd ['theta_deg'] <= 90.0]
                sl_back = sl_back[sl_back['theta_deg'] <= 90.0]
            import pandas as _pd
            sl = _pd.concat([sl_fwd, sl_back])

        else:
            sl = out_df

        peak = float(sl['E_mag'].max())
        if peak > global_peak:
            global_peak = peak

    return global_peak if global_peak > 0.0 else 1.0


def _polar_grid_labels(ax, scale, E_scaled_series):
    """
    Set polar axis ring ticks and labels for a single-component plot.
    (Overlay plots use _polar_grid_labels_global instead.)
    """
    import matplotlib.ticker as ticker

    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator(2))
    ax.yaxis.grid(False, which='minor')

    if scale == 'ARRL':
        ring_dbs = [0, -3, -10, -20, -30, -40, -50]
        r_outer  = _arrl_radius(0.0)
        r_floor  = _arrl_radius(-50.0)
        r_ticks  = [(_arrl_radius(db) - r_floor) / (r_outer - r_floor)
                    for db in ring_dbs]
        r_labels = [f"{db}" for db in ring_dbs[:-1]] + ['']

    elif scale == 'dB peak':
        floor    = -40.0
        peak     = 0.0
        spacing  = 5
        ring_dbs = list(range(0, int(floor) - 1, -spacing))
        r_ticks  = [(db - floor) / (peak - floor) for db in ring_dbs]
        r_labels = [f"{db}" for db in ring_dbs]

    elif scale == 'dBi':
        peak     = float(np.max(E_scaled_series))
        floor    = peak - 40.0
        spacing  = 5
        ring_dbs = [peak - s for s in range(0, 41, spacing)]
        r_ticks  = [(db - floor) / (peak - floor) for db in ring_dbs]
        r_labels = [f"{db:.0f}" for db in ring_dbs]

    else:  # Linear
        r_ticks  = [0.2, 0.4, 0.6, 0.8, 1.0]
        r_labels = ['0.2', '0.4', '0.6', '0.8', '1.0']

    ax.set_yticks(r_ticks)
    ax.set_yticklabels(r_labels, fontsize=cfg.font_tick, color='gray')
    ax.tick_params(axis='y', which='major', labelsize=cfg.font_tick)
    ax.set_rlabel_position(22.5)
    ax.set_ylim(0, 1.0)
    ax.yaxis.grid(True, which='major', linestyle='--', linewidth=cfg.lw_grid,
                  color='gray', alpha=0.6)


def _polar_grid_labels_global(ax, scale, global_emag, meta):
    """
    Set polar axis ring ticks and labels for OVERLAY plots, using the
    global |E| peak so ring labels reflect dB below the pattern maximum
    (not below each individual component's peak).
    """
    import matplotlib.ticker as ticker

    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator(2))
    ax.yaxis.grid(False, which='minor')

    if scale == 'ARRL':
        ring_dbs = [0, -3, -10, -20, -30, -40, -50]
        r_outer  = _arrl_radius(0.0)
        r_floor  = _arrl_radius(-50.0)
        r_ticks  = [(_arrl_radius(db) - r_floor) / (r_outer - r_floor)
                    for db in ring_dbs]
        r_labels = [f"{db}" for db in ring_dbs[:-1]] + ['']

    elif scale == 'dB peak':
        ring_dbs = [0, -5, -10, -15, -20, -25, -30, -35, -40]
        floor    = -40.0
        r_ticks  = [(db - floor) / (-floor) for db in ring_dbs]
        r_labels = [f"{db}" for db in ring_dbs]

    elif scale == 'dBi':
        # Anchor to actual gain_peak_dBi from metadata if available;
        # otherwise estimate from global_emag.
        gain_peak = meta.get('gain_peak_dbi')
        if not isinstance(gain_peak, (int, float)):
            # fallback: outer ring = global_emag (arbitrary V·m reference)
            gain_peak = 0.0
        floor    = gain_peak - 40.0
        spacing  = 5
        ring_dbs = [gain_peak - s for s in range(0, 41, spacing)]
        r_ticks  = [(db - floor) / (gain_peak - floor) for db in ring_dbs]
        r_labels = [f"{db:.0f}" for db in ring_dbs]

    else:  # Linear
        r_ticks  = [0.2, 0.4, 0.6, 0.8, 1.0]
        r_labels = ['0.04', '0.16', '0.36', '0.64', '1.0']  # power ratios

    ax.set_yticks(r_ticks)
    ax.set_yticklabels(r_labels, fontsize=cfg.font_tick, color='gray')
    ax.tick_params(axis='y', which='major', labelsize=cfg.font_tick)
    ax.set_rlabel_position(22.5)
    ax.set_ylim(0, 1.0)
    ax.yaxis.grid(True, which='major', linestyle='--', linewidth=cfg.lw_grid,
                  color='gray', alpha=0.6)


def _build_elevation_cut(out_df, phi_cut, hemisphere='upper'):
    """
    Build elevation cut arrays (E_scaled) for single-component polar plot.
    """
    phi_vals    = out_df['phi_deg'].unique()
    nearest_phi = phi_vals[np.argmin(np.abs(phi_vals - phi_cut))]

    right_all = out_df[out_df['phi_deg'] == nearest_phi].copy()
    right_all = right_all.sort_values('theta_deg')

    # Both upper and full hemisphere: left side uses phi+180° data.
    # For upper hemisphere this shows the back-azimuth pattern
    # correctly — elevation cuts at phi=60° and phi=240° will
    # show different amplitudes as expected for a directional antenna.
    p_back = (nearest_phi + 180.0) % 360.0
    p_back = phi_vals[np.argmin(np.abs(phi_vals - p_back))]
    left_all = out_df[out_df['phi_deg'] == p_back].copy()
    left_all = left_all.sort_values('theta_deg')

    if hemisphere == 'upper':
        right = right_all[right_all['theta_deg'] <= 90.0]
        left  = left_all[(left_all['theta_deg'] > 0) &
                         (left_all['theta_deg'] <= 90.0)]
        left_thetas = -left['theta_deg'].values[::-1]
        left_E      =  left['E_scaled'].values[::-1]
    else:
        right = right_all
        left  = left_all[left_all['theta_deg'] > 0]
        left_thetas = -left['theta_deg'].values[::-1]
        left_E      =  left['E_scaled'].values[::-1]

    thetas_deg = np.concatenate([left_thetas,
                                 right['theta_deg'].values])
    E_scaled   = np.concatenate([left_E,
                                 right['E_scaled'].values])
    return thetas_deg, E_scaled, nearest_phi


def _build_elevation_cut_emag(out_df, phi_cut, hemisphere='upper'):
    """
    Build elevation cut arrays (E_mag — raw linear field) for overlay
    polar plots.  Returns the same shape as _build_elevation_cut but
    using the 'E_mag' column instead of 'E_scaled'.
    """
    phi_vals    = out_df['phi_deg'].unique()
    nearest_phi = phi_vals[np.argmin(np.abs(phi_vals - phi_cut))]

    right_all = out_df[out_df['phi_deg'] == nearest_phi].copy()
    right_all = right_all.sort_values('theta_deg')

    # Both upper and full hemisphere: left side uses phi+180° data.
    p_back = (nearest_phi + 180.0) % 360.0
    p_back = phi_vals[np.argmin(np.abs(phi_vals - p_back))]
    left_all = out_df[out_df['phi_deg'] == p_back].copy()
    left_all = left_all.sort_values('theta_deg')

    if hemisphere == 'upper':
        right = right_all[right_all['theta_deg'] <= 90.0]
        left  = left_all[(left_all['theta_deg'] > 0) &
                         (left_all['theta_deg'] <= 90.0)]
        left_thetas = -left['theta_deg'].values[::-1]
        left_E      =  left['E_mag'].values[::-1]
    else:
        right = right_all
        left  = left_all[left_all['theta_deg'] > 0]
        left_thetas = -left['theta_deg'].values[::-1]
        left_E      =  left['E_mag'].values[::-1]

    thetas_deg = np.concatenate([left_thetas,
                                 right['theta_deg'].values])
    E_mag      = np.concatenate([left_E,
                                 right['E_mag'].values])
    return thetas_deg, E_mag, nearest_phi


def _add_peak_annotation(ax, slice_df, scale, coords='cartesian'):
    """Mark the peak value on Cartesian plots with a dot and label."""
    idx      = slice_df['E_scaled'].idxmax()
    peak_row = slice_df.loc[idx]

    if coords == 'cartesian':
        x = peak_row.iloc[1]
        y = peak_row['E_scaled']
        ax.annotate(f"peak {y:.2f}",
                    xy=(x, y),
                    xytext=(x + 2, y - 2),
                    fontsize=cfg.font_annot,
                    color='red',
                    arrowprops=dict(arrowstyle='->', color='red'))


# ----------------------------------------------------------------
# SECTION 6: Command-line test
# ----------------------------------------------------------------
if __name__ == '__main__':
    import sys
    from data_reader  import read_antenna_file
    from pattern_math import apply_component_and_scale

    if len(sys.argv) < 2:
        print("Usage: python3 plot_panel.py <antenna_file.csv>")
        sys.exit(1)

    meta, df = read_antenna_file(sys.argv[1])

    scale      = 'ARRL'
    elev_phi   = 0.0
    azim_theta = 90.0

    out_ev     = apply_component_and_scale(df, 'Ev',     scale, meta)
    out_eh     = apply_component_and_scale(df, 'Eh',     scale, meta)
    out_etotal = apply_component_and_scale(df, 'Etotal', scale, meta)
    out_dict   = {'Ev': out_ev, 'Eh': out_eh, 'Etotal': out_etotal}

    print(f"\nOpening overlay polar windows...")
    print(f"  Elevation upper hemisphere at phi = {elev_phi:.1f} deg")
    print(f"  Azimuth cut at theta = {azim_theta:.1f} deg")
    print(f"  Scale: {scale}\n")

    plot_elevation_polar_overlay(out_dict, meta, scale, elev_phi,
                                 hemisphere='upper')
    plot_elevation_polar_overlay(out_dict, meta, scale, elev_phi,
                                 hemisphere='full')
    plot_azimuth_polar_overlay(out_dict, meta, scale, azim_theta)

    plt.show()