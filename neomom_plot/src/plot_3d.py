# plot_3d.py
#
# 3D radiation pattern visualization with:
# - Linear geometry (E_mag)
# - dB or linear color mapping
# - Ground plane + horizon circle
# - Custom axes
# - Peak marker
# - Peak gain annotation (from metadata: gain_peak_dBi)
# - Beamwidth annotation
# - Annotation modes: 'title', 'lobe', 'none'

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401
from matplotlib import cm

from pattern_math import reshape_to_grid, reshape_column_to_grid
from plot_panel import make_title
from display_config import cfg


# ---------------------------------------------------------------
# Spherical → Cartesian (NEC convention: theta from +Z)
# ---------------------------------------------------------------

def _spherical_to_cartesian(theta_deg, phi_deg, R):
    THETA = np.radians(theta_deg)[:, None]
    PHI   = np.radians(phi_deg)[None, :]

    X = R * np.sin(THETA) * np.cos(PHI)
    Y = R * np.sin(THETA) * np.sin(PHI)
    Z = R * np.cos(THETA)
    return X, Y, Z



# ---------------------------------------------------------------
# ARRL surface helpers  (same nonlinear law as polar plots)
# ---------------------------------------------------------------

def _arrl_radius(db):
    """
    ARRL nonlinear radial mapping.
    db=0   -> 1.000 (outer),  db=-3  -> 0.840
    db=-10 -> 0.558,          db=-20 -> 0.312
    db=-30 -> 0.174,          db=-40 -> 0.097
    db=-50 -> 0.054 (floor, maps to r=0)
    """
    return (0.89) ** (-0.5 * np.clip(db, -50.0, 0.0))


def _arrl_normalize(E_mag):
    """Convert linear E_mag to ARRL-normalised radii in [0, 1]."""
    peak  = np.max(E_mag)
    E_db  = 20.0 * np.log10(np.maximum(E_mag / peak, 1e-6))
    r_outer = _arrl_radius(0.0)    # 1.000
    r_floor = _arrl_radius(-50.0)  # ~0.054
    r_raw   = _arrl_radius(E_db)
    return (r_raw - r_floor) / (r_outer - r_floor)


def _arrl_colorbar(fig, ax, scale_label):
    """Colorbar with ARRL dB tick marks."""
    ring_dbs = [0, -3, -10, -20, -30, -40]
    r_outer  = _arrl_radius(0.0)
    r_floor  = _arrl_radius(-50.0)
    r_ticks  = [((_arrl_radius(db) - r_floor) / (r_outer - r_floor))
                for db in ring_dbs]
    m    = cm.ScalarMappable(cmap='jet')
    m.set_clim(0.0, 1.0)
    cbar = fig.colorbar(m, ax=ax, shrink=0.7)
    cbar.set_label(scale_label, fontsize=cfg.font_3d_label)
    cbar.set_ticks(r_ticks)
    cbar.set_ticklabels([f"{db} dB" for db in ring_dbs],
                        fontsize=cfg.font_3d_annot)
    return m, cbar


# ---------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------

def plot_3d_pattern(out_dict, meta, scale,
                    hemisphere='upper',
                    annotation_mode='title',
                    surface_mode='linear'):
    """
    annotation_mode:
        'title' → Peak gain + beamwidth in title
        'lobe'  → Annotation near peak marker
        'none'  → No annotation
    """

    fig = plt.figure(figsize=cfg.fig_heatmap, dpi=cfg.mpl_dpi)
    ax = fig.add_subplot(111, projection='3d')

    # Force popup window to be square
    mgr = plt.get_current_fig_manager()
    try:
        w = int(cfg.fig_3d[0] * cfg.mpl_dpi)
        h = int(cfg.fig_3d[1] * cfg.mpl_dpi)
        mgr.window.wm_geometry(f"{w}x{h}")
    except:
        pass

    fig.canvas.manager.set_window_title("3D Radiation Pattern")

    grid_for_colorbar = None

    for comp, out_df in out_dict.items():

        # -----------------------------------------------------------
        # 1. Reshape scaled grid (E_scaled) for colors
        # -----------------------------------------------------------
        theta_vals_full, phi_vals, grid_scaled_full = reshape_to_grid(out_df, meta)

        # Hemisphere mask
        if hemisphere == 'upper':
            mask = theta_vals_full <= 90.0
            theta_vals = theta_vals_full[mask]
            grid_scaled = grid_scaled_full[mask, :]
        else:
            theta_vals = theta_vals_full
            grid_scaled = grid_scaled_full

        # -----------------------------------------------------------
        # 2. Geometry uses linear E_mag ONLY
        # -----------------------------------------------------------
        _theta_check, _phi_check, E_mag_full = reshape_column_to_grid(out_df, 'E_mag')
        # Sanity check: E_mag grid must line up with the E_scaled grid
        # reshaped above (same theta/phi axes, same row-major assumption).
        assert np.array_equal(_theta_check, theta_vals_full)
        assert np.array_equal(_phi_check, phi_vals)

        if hemisphere == 'upper':
            E_mag = E_mag_full[mask, :]
        else:
            E_mag = E_mag_full

        if surface_mode == 'arrl':
            R = _arrl_normalize(E_mag)
        else:
            _r = E_mag / np.max(E_mag)
            R  = _r ** 2   # gain = E² (normalized power)

        # -----------------------------------------------------------
        # 3. Color mapping — linear surface: gain [0,1]; ARRL: dB scale
        # -----------------------------------------------------------
        if surface_mode == 'linear':
            grid_clipped = np.clip(R, 0.0, 1.0)
            gmin, gmax   = 0.0, 1.0
            colors       = cm.jet(grid_clipped)
        elif scale in ('dB peak', 'dBi', 'ARRL'):
            grid_clipped = np.clip(grid_scaled, -40.0, 0.0)
            gmin, gmax = -40.0, 0.0
            colors = cm.jet((grid_clipped - gmin) / (gmax - gmin))
        else:
            grid_clipped = np.clip(grid_scaled, 0.0, 1.0)
            gmin, gmax = 0.0, 1.0
            colors = cm.jet(grid_clipped)

        grid_for_colorbar = grid_clipped

        # -----------------------------------------------------------
        # 4. Convert to Cartesian
        # -----------------------------------------------------------
        X, Y, Z = _spherical_to_cartesian(theta_vals, phi_vals, R)

        # -----------------------------------------------------------
        # 5. Peak location
        # -----------------------------------------------------------
        peak_idx = np.unravel_index(np.argmax(E_mag), E_mag.shape)
        theta_peak = theta_vals[peak_idx[0]]
        phi_peak   = phi_vals[peak_idx[1]]

        # Convert peak to Cartesian
        Xp = np.sin(np.radians(theta_peak)) * np.cos(np.radians(phi_peak))
        Yp = np.sin(np.radians(theta_peak)) * np.sin(np.radians(phi_peak))
        Zp = np.cos(np.radians(theta_peak))

        # -----------------------------------------------------------
        # 6. Peak gain (use solver-computed absolute gain)
        # -----------------------------------------------------------
        true_peak_gain = meta.get("gain_peak_dbi", None)

        if true_peak_gain is not None:
            peak_gain_str = f"{true_peak_gain:.2f} dBi"
        else:
            # Fallback: normalized plot data
            if scale in ('dB peak', 'dBi', 'ARRL'):
                peak_gain = grid_scaled[peak_idx]
                peak_gain_str = f"{peak_gain:.1f} dB"
            else:
                peak_gain = E_mag[peak_idx]
                peak_gain_str = f"{peak_gain:.3f} (linear)"

        # -----------------------------------------------------------
        # 7. Beamwidth (half-power)
        # -----------------------------------------------------------
        j = peak_idx[1]
        slice_vals = grid_scaled[:, j]

        if scale in ('dB peak', 'dBi', 'ARRL'):
            target = grid_scaled[peak_idx] - 3.0
        else:
            target = E_mag[peak_idx] * (10**(-3/20))

        theta_array = theta_vals
        i_peak = peak_idx[0]

        left_idx = i_peak
        while left_idx > 0 and slice_vals[left_idx] > target:
            left_idx -= 1

        right_idx = i_peak
        while right_idx < len(slice_vals)-1 and slice_vals[right_idx] > target:
            right_idx += 1

        beamwidth = theta_array[right_idx] - theta_array[left_idx]
        beamwidth_str = f"{beamwidth:.1f}°"

        # -----------------------------------------------------------
        # 8. Plot radiation surface
        # -----------------------------------------------------------
        ax.plot_surface(
            X, Y, Z,
            rstride=1, cstride=1,
            facecolors=colors,
            linewidth=0,
            antialiased=True,
            alpha=0.90
        )

        # Peak marker
        ax.scatter([Xp], [Yp], [Zp],
                   color='red', s=60, depthshade=True)

        # Lobe annotation
        if annotation_mode == 'lobe':
            ax.text(Xp, Yp, Zp,
                    f"Peak: {peak_gain_str}\nBW: {beamwidth_str}",
                    color='red', fontsize=cfg.font_3d_annot,
                    ha='left', va='bottom')

    # ---------------------------------------------------------------
    # 9. Remove axes
    # ---------------------------------------------------------------
    ax.set_axis_off()

    # ---------------------------------------------------------------
    # 10. Ground plane (upper hemisphere only)
    # ---------------------------------------------------------------
    if hemisphere == 'upper':
        r = max(abs(X).max(), abs(Y).max())
        theta = np.linspace(0, 2*np.pi, 200)
        radius = np.linspace(0, r, 100)
        T, Rg = np.meshgrid(theta, radius)

        gp_x = Rg * np.cos(T)
        gp_y = Rg * np.sin(T)
        gp_z = np.zeros_like(gp_x)

        ax.plot_surface(
            gp_x, gp_y, gp_z,
            color='lightgray',
            alpha=0.35,
            linewidth=0
        )

    # ---------------------------------------------------------------
    # 11. Horizon circle
    # ---------------------------------------------------------------
    r = max(abs(X).max(), abs(Y).max())
    phi = np.linspace(0, 2*np.pi, 361)
    cx = r * np.cos(phi)
    cy = r * np.sin(phi)
    cz = np.zeros_like(cx)
    ax.plot(cx, cy, cz, color='black', linewidth=1.2)

    # ---------------------------------------------------------------
    # 12. Custom axes
    # ---------------------------------------------------------------
    ax.plot([-r, r], [0, 0], [0, 0], color='black', linewidth=1.2)
    ax.text(r, 0, 0, "+X (φ=0°)", fontsize=cfg.font_3d_label, ha='left', va='center')
    ax.text(-r, 0, 0, "-X (φ=180°)", fontsize=cfg.font_3d_label, ha='right', va='center')

    ax.plot([0, 0], [-r, r], [0, 0], color='black', linewidth=1.2)
    ax.text(0, r, 0, "+Y (φ=90°)", fontsize=cfg.font_3d_label, ha='center', va='bottom')
    ax.text(0, -r, 0, "-Y (φ=270°)", fontsize=cfg.font_3d_label, ha='center', va='top')

    z_len = 1.25*r
    ax.plot([0, 0], [0, 0], [0, z_len], color='black', linewidth=1.2)
    ax.text(0, 0, z_len, "Zenith", fontsize=cfg.font_3d_label, ha='center', va='bottom')

    # ---------------------------------------------------------------
    # 13. Title + colorbar
    # ---------------------------------------------------------------
    base_title = make_title(meta, " & ".join(out_dict.keys()),
                            scale, "3D Pattern", 0).split("\n")[0]

    if annotation_mode == 'title':
        title = f"{base_title}   |   Peak: {peak_gain_str}   BW: {beamwidth_str}"
    else:
        title = base_title

    ax.set_title(title, pad=20, fontsize=cfg.font_3d_title)

    # Colorbar
    if surface_mode == 'arrl':
        _arrl_colorbar(fig, ax, 'ARRL (dB)')
    elif surface_mode == 'linear':
        m = cm.ScalarMappable(cmap='jet')
        m.set_clim(0.0, 1.0)
        cbar = fig.colorbar(m, ax=ax, shrink=0.7)
        cbar.set_label('Gain (normalized)', fontsize=cfg.font_3d_label)
        cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
        cbar.set_ticklabels(["0.0", "0.25", "0.5", "0.75", "1.0"], fontsize=cfg.font_3d_annot)
    else:
        m = cm.ScalarMappable(cmap='jet')
        m.set_clim(gmin, gmax)
        cbar = fig.colorbar(m, ax=ax, shrink=0.7)
        cbar.set_label(scale, fontsize=cfg.font_3d_label)
        if scale in ('dB peak', 'dBi', 'ARRL'):
            cbar.set_ticks([-40, -30, -20, -10, 0])
            cbar.set_ticklabels(["-40 dB", "-30", "-20", "-10", "0"], fontsize=cfg.font_3d_annot)
        else:
            cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
            cbar.set_ticklabels(["0.0", "0.25", "0.5", "0.75", "1.0"], fontsize=cfg.font_3d_annot)

    # ---------------------------------------------------------------
    # 14. Equal aspect ratio
    # ---------------------------------------------------------------
    max_range = np.array([
        X.max() - X.min(),
        Y.max() - Y.min(),
        Z.max() - Z.min()
    ]).max() / 2.0

    mid_x = (X.max() + X.min()) * 0.5
    mid_y = (Y.max() + Y.min()) * 0.5
    mid_z = (Z.max() + Z.min()) * 0.5

    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)

    ax.set_box_aspect([1,1,1])

    plt.tight_layout()
    plt.show(block=False)

# TOP DOWN VIEW ------------------------------------------
def plot_3d_pattern_topdown(out_dict, meta, scale,
                            hemisphere='upper',
                            annotation_mode='title',
                            surface_mode='linear'):
    """
    Top‑down view:
      - Camera looking down +Z
      - φ = 0° → North (up, +X)
      - φ = 90° → East (right, +Y)
    Geometry, colors, peak, beamwidth all identical to plot_3d_pattern.
    """

    fig = plt.figure(figsize=cfg.fig_heatmap, dpi=cfg.mpl_dpi)
    ax = fig.add_subplot(111, projection='3d')

    # Force popup window to be square
    mgr = plt.get_current_fig_manager()
    try:
        w = int(cfg.fig_3d[0] * cfg.mpl_dpi)
        h = int(cfg.fig_3d[1] * cfg.mpl_dpi)
        mgr.window.wm_geometry(f"{w}x{h}")
    except:
        pass

    fig.canvas.manager.set_window_title("3D Radiation Pattern (Top‑Down)")

    # Top‑down camera: look down +Z, +X up, +Y right
    ax.view_init(elev=90, azim=270)

    grid_for_colorbar = None

    for comp, out_df in out_dict.items():

        theta_vals_full, phi_vals, grid_scaled_full = reshape_to_grid(out_df, meta)

        if hemisphere == 'upper':
            mask = theta_vals_full <= 90.0
            theta_vals = theta_vals_full[mask]
            grid_scaled = grid_scaled_full[mask, :]
        else:
            theta_vals = theta_vals_full
            grid_scaled = grid_scaled_full

        _theta_check, _phi_check, E_mag_full = reshape_column_to_grid(out_df, 'E_mag')
        assert np.array_equal(_theta_check, theta_vals_full)
        assert np.array_equal(_phi_check, phi_vals)

        if hemisphere == 'upper':
            E_mag = E_mag_full[mask, :]
        else:
            E_mag = E_mag_full

        if surface_mode == 'arrl':
            R = _arrl_normalize(E_mag)
        else:
            _r = E_mag / np.max(E_mag)
            R  = _r ** 2   # gain = E² (normalized power)

        if surface_mode == 'linear':
            grid_clipped = np.clip(R, 0.0, 1.0)
            gmin, gmax   = 0.0, 1.0
            colors       = cm.jet(grid_clipped)
        elif scale in ('dB peak', 'dBi', 'ARRL'):
            grid_clipped = np.clip(grid_scaled, -40.0, 0.0)
            gmin, gmax = -40.0, 0.0
            colors = cm.jet((grid_clipped - gmin) / (gmax - gmin))
        else:
            grid_clipped = np.clip(grid_scaled, 0.0, 1.0)
            gmin, gmax = 0.0, 1.0
            colors = cm.jet(grid_clipped)

        grid_for_colorbar = grid_clipped

        # Same geometry as original
        #X, Y, Z = _spherical_to_cartesian(theta_vals, phi_vals, R)

        X0, Y0, Z0 = _spherical_to_cartesian(theta_vals, phi_vals, R)

        # Top‑down compass mapping:
        #   φ=0°  → North (up)
        #   φ=90° → East  (right)
        X = Y0   # East/West goes to horizontal
        Y = X0   # North/South goes to vertical
        Z = Z0



        peak_idx = np.unravel_index(np.argmax(E_mag), E_mag.shape)
        theta_peak = theta_vals[peak_idx[0]]
        phi_peak   = phi_vals[peak_idx[1]]

        #Xp = np.sin(np.radians(theta_peak)) * np.cos(np.radians(phi_peak))
        #Yp = np.sin(np.radians(theta_peak)) * np.sin(np.radians(phi_peak))
        #Zp = np.cos(np.radians(theta_peak))

        Xp0 = np.sin(np.radians(theta_peak)) * np.cos(np.radians(phi_peak))
        Yp0 = np.sin(np.radians(theta_peak)) * np.sin(np.radians(phi_peak))
        Zp  = np.cos(np.radians(theta_peak))

        Xp = Yp0
        Yp = Xp0



        true_peak_gain = meta.get("gain_peak_dbi", None)

        if true_peak_gain is not None:
            peak_gain_str = f"{true_peak_gain:.2f} dBi"
        else:
            if scale in ('dB peak', 'dBi', 'ARRL'):
                peak_gain = grid_scaled[peak_idx]
                peak_gain_str = f"{peak_gain:.1f} dB"
            else:
                peak_gain = E_mag[peak_idx]
                peak_gain_str = f"{peak_gain:.3f} (linear)"

        j = peak_idx[1]
        slice_vals = grid_scaled[:, j]

        if scale in ('dB peak', 'dBi', 'ARRL'):
            target = grid_scaled[peak_idx] - 3.0
        else:
            target = E_mag[peak_idx] * (10**(-3/20))

        theta_array = theta_vals
        i_peak = peak_idx[0]

        left_idx = i_peak
        while left_idx > 0 and slice_vals[left_idx] > target:
            left_idx -= 1

        right_idx = i_peak
        while right_idx < len(slice_vals)-1 and slice_vals[right_idx] > target:
            right_idx += 1

        beamwidth = theta_array[right_idx] - theta_array[left_idx]
        beamwidth_str = f"{beamwidth:.1f}°"

        ax.plot_surface(
            X, Y, Z,
            rstride=1, cstride=1,
            facecolors=colors,
            linewidth=0,
            antialiased=True,
            alpha=0.90
        )

        # Peak marker (disabled for top‑down view)
        # ax.scatter([Xp], [Yp], [Zp],
        #            color='red', s=60, depthshade=True)
        

        #if annotation_mode == 'lobe':
        #    ax.text(Xp, Yp, Zp,
        #            f"Peak: {peak_gain_str}\nBW: {beamwidth_str}",
        #            color='red', fontsize=cfg.font_3d_annot,
        #            ha='left', va='bottom')

    ax.set_axis_off()

    if hemisphere == 'upper':
        r = max(abs(X).max(), abs(Y).max())
        theta = np.linspace(0, 2*np.pi, 200)
        radius = np.linspace(0, r, 100)
        T, Rg = np.meshgrid(theta, radius)

        #gp_x = Rg * np.cos(T)
        #gp_y = Rg * np.sin(T)
        #gp_z = np.zeros_like(gp_x)

        gp_x0 = Rg * np.cos(T)
        gp_y0 = Rg * np.sin(T)
        gp_z  = np.zeros_like(gp_x0)

        gp_x = gp_y0
        gp_y = gp_x0


        ax.plot_surface(
            gp_x, gp_y, gp_z,
            color='lightgray',
            alpha=0.35,
            linewidth=0
        )

    r = max(abs(X).max(), abs(Y).max())
    phi = np.linspace(0, 2*np.pi, 361)
    #cx = r * np.cos(phi)
    #cy = r * np.sin(phi)
    #cz = np.zeros_like(cx)
    cx0 = r * np.cos(phi)
    cy0 = r * np.sin(phi)
    cz  = np.zeros_like(cx0)

    cx = cy0
    cy = cx0


    ax.plot(cx, cy, cz, color='black', linewidth=1.2)

    # Axes: compass in top‑down view
    # +X = North (up), +Y = East (right)

    # Horizontal line: left–right
    ax.plot([-r, r], [0, 0], [0, 0], color='black', linewidth=1.2)
    ax.text( r, 0, 0, "+Y (East, φ=90°)",  fontsize=cfg.font_3d_label, ha='left',  va='center')
    ax.text(-r, 0, 0, "-Y (West, φ=270°)", fontsize=cfg.font_3d_label, ha='right', va='center')

    # Vertical line: up–down
    ax.plot([0, 0], [-r, r], [0, 0], color='black', linewidth=1.2)
    ax.text(0,  r, 0, "+X (North, φ=0°)",   fontsize=cfg.font_3d_label, ha='center', va='bottom')
    ax.text(0, -r, 0, "-X (South, φ=180°)", fontsize=cfg.font_3d_label, ha='center', va='top')




    z_len = 1.25*r
    ax.plot([0, 0], [0, 0], [0, z_len], color='black', linewidth=1.2)
    ax.text(0, 0, z_len, "Zenith", fontsize=cfg.font_3d_label, ha='center', va='bottom')

    base_title = make_title(meta, " & ".join(out_dict.keys()),
                            scale, "3D Pattern (Top‑Down)", 0).split("\n")[0]

    if annotation_mode == 'title':
        title = f"{base_title}   |   Peak: {peak_gain_str}   BW: {beamwidth_str}"
    else:
        title = base_title

    ax.set_title(title, pad=20, fontsize=cfg.font_3d_title)

    if surface_mode == 'arrl':
        _arrl_colorbar(fig, ax, 'ARRL (dB)')
    elif surface_mode == 'linear':
        m = cm.ScalarMappable(cmap='jet')
        m.set_clim(0.0, 1.0)
        cbar = fig.colorbar(m, ax=ax, shrink=0.7)
        cbar.set_label('Gain (normalized)', fontsize=cfg.font_3d_label)
        cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
        cbar.set_ticklabels(["0.0", "0.25", "0.5", "0.75", "1.0"], fontsize=cfg.font_3d_annot)
    else:
        m = cm.ScalarMappable(cmap='jet')
        m.set_clim(gmin, gmax)
        cbar = fig.colorbar(m, ax=ax, shrink=0.7)
        cbar.set_label(scale, fontsize=cfg.font_3d_label)
        if scale in ('dB peak', 'dBi', 'ARRL'):
            cbar.set_ticks([-40, -30, -20, -10, 0])
            cbar.set_ticklabels(["-40 dB", "-30", "-20", "-10", "0"], fontsize=cfg.font_3d_annot)
        else:
            cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
            cbar.set_ticklabels(["0.0", "0.25", "0.5", "0.75", "1.0"], fontsize=cfg.font_3d_annot)

    max_range = np.array([
        X.max() - X.min(),
        Y.max() - Y.min(),
        Z.max() - Z.min()
    ]).max() / 2.0

    mid_x = (X.max() + X.min()) * 0.5
    mid_y = (Y.max() + Y.min()) * 0.5
    mid_z = (Z.max() + Z.min()) * 0.5

    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)

    ax.set_box_aspect([1,1,1])

    plt.tight_layout()
    plt.show(block=False)

# def compute_topdown_footprint_from_3d(out_dict, meta, hemisphere='upper'):
#     """
#     Returns:
#         phi_deg : 1D array of azimuth angles (deg)
#         r_norm  : 1D array of normalized radius vs phi (matches 3D top‑down footprint)
#     """
#     # Assume single component in out_dict (e.g., 'total')
#     comp, out_df = next(iter(out_dict.items()))

#     theta_vals_full, phi_vals, grid_scaled_full = reshape_to_grid(out_df, meta)

#     if hemisphere == 'upper':
#         mask = theta_vals_full <= 90.0
#         theta_vals = theta_vals_full[mask]
#         grid_scaled = grid_scaled_full[mask, :]
#     else:
#         theta_vals = theta_vals_full
#         grid_scaled = grid_scaled_full

#     theta_unique = np.sort(out_df['theta_deg'].unique())
#     phi_unique   = np.sort(out_df['phi_deg'].unique())
#     nTheta_full  = len(theta_unique)
#     nPhi_full    = len(phi_unique)

#     E_mag_full = out_df['E_mag'].values.reshape(nTheta_full, nPhi_full)

#     if hemisphere == 'upper':
#         E_mag = E_mag_full[mask, :]
#     else:
#         E_mag = E_mag_full

#     # Normalize magnitude to get radius
#     R = E_mag / np.max(E_mag)

#     # For each phi column, take max radius over theta (top‑down footprint)
#     r_top = R.max(axis=0)          # shape: (nPhi,)
#     phi_deg = phi_vals             # already in degrees

#     # Normalize again just to be safe
#     r_norm = r_top / r_top.max()

#     return phi_deg, r_norm