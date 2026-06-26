# plots_neomom.py
#
# Purpose: Tkinter control panel for antenna pattern visualization.
# Launches as a floating window independent of all plot windows.
# Calls plot_panel.py / plot_3d.py directly — no plotting logic here.
#
# Usage:
#   python3 plots_neomom.py [antenna_file.csv]
#   (omit the file argument to open a file-chooser dialog)
#
# Layout (top to bottom):
#   [Antenna info — title, freq, gain, impedance, SWR, ground, height]
#   [Visualization Mode selector — 2D-Azimuth | 2D-Elevation | 3D | Map Overlay]
#   [Options panel — mode-specific controls + Plot button]
#   [Close All Plots button | Status bar]

import sys
import os
import json
import platform
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

from pattern_math import reshape_to_grid
import numpy as np


# ----------------------------------------------------------------
# User preferences — remembers last directory used for file open.
# Windows : %APPDATA%\plots_neomom\prefs.json
# Linux   : ~/.config/plots_neomom/prefs.json
# ----------------------------------------------------------------
from pathlib import Path

def _prefs_file():
    if platform.system() == 'Windows':
        base = Path(os.environ.get('APPDATA', Path.home()))
    else:
        base = Path.home() / '.config'
    return base / 'plots_neomom' / 'prefs.json'

def _load_prefs():
    try:
        with open(_prefs_file(), 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_prefs(prefs):
    p = _prefs_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w') as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass   # non-fatal — just don't crash if we can't write

from data_reader   import read_antenna_file
from pattern_math  import apply_component_and_scale
from plot_panel    import (plot_elevation_polar_overlay,
                           plot_azimuth_polar_overlay)
from display_config import cfg

# Scale Tkinter widget fonts for HiDPI display
import tkinter.font as tkfont


def _make_box(parent, title='', font=None, pad=4):
    """
    Bordered box using tk.LabelFrame (not ttk) for direct color control.
    Returns the frame to pack widgets into.
    """
    frame = tk.LabelFrame(parent,
                          text=title,
                          font=font,
                          fg='#333333',
                          bg=parent.cget('bg'),
                          bd=2,
                          relief='groove')
    frame.pack(fill='x', padx=8, pady=pad)
    return frame


# ----------------------------------------------------------------
# SECTION 1: Data loading
# ----------------------------------------------------------------

def load_data(filepath):
    """Load antenna file and return meta + raw DataFrame."""
    meta, df = read_antenna_file(filepath)
    return meta, df


def compute_out_dicts(df, meta, scale, comp_flags):
    """
    Build out_dict containing only the checked components.
    comp_flags : dict  {'Ev': bool, 'Eh': bool, 'Etotal': bool}
    Returns {} if nothing is checked.
    """
    out_dict = {}
    for comp, checked in comp_flags.items():
        if checked:
            out_dict[comp] = apply_component_and_scale(df, comp, scale, meta)
    return out_dict

# ----------------------------------------------------------------
# SECTION 2: Main GUI class
# ----------------------------------------------------------------

class AntennaGUI:

    PADX_SECTION = 5
    PADY_SECTION = 10

    PADX_INDENT = 75
    PADY_ITEM = 4

   
    COMP_COLORS = {'Ev': 'steelblue', 'Eh': 'darkorange', 'Etotal': 'green'}
    SCALES      = ['ARRL', 'dB peak', 'dBi', 'Linear']
    COMPONENTS  = ['Ev', 'Eh', 'Etotal']


    def on_mode_change(self):
        mode = self.vis_mode.get()
        #print(f"[DEBUG] Visualization mode changed to: {mode}")

        # Rebuild the dynamic options panel
        self._build_options_panel()


    def _build_options_panel(self):
        # Clear previous contents
        for widget in self.options_panel.winfo_children():
            widget.destroy()

        mode = self.vis_mode.get()

       # print("Mode is:", mode)

        if mode == "2D-Azimuth":
            self._build_options_2d_azimuth(self.options_panel)

        elif mode == "2D-Elevation":
            self._build_options_2d_elevation(self.options_panel)

        elif mode == "3D-Standard":
            self._build_options_3d_standard(self.options_panel)

        elif mode == "3D-TopDown":
            self._build_options_3d_topdown(self.options_panel)

        elif mode == "Map-Overlay":
            #print("Building Map Overlay panel...")

            self._build_options_map_overlay(self.options_panel)


    def _build_options_2d_azimuth(self, parent):

        ttk.Label(parent, text="2D Azimuth Options",
                font=self.fonts['meta1']).pack(anchor='w', padx=8, pady=4)

        # --- Components ---
        comp_row = ttk.Frame(parent)
        comp_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(comp_row, text="Components:", width=13).pack(side='left')

        for comp in self.COMPONENTS:
            color = self.COMP_COLORS[comp]
            tk.Checkbutton(comp_row,
                        text=comp,
                        variable=self.comp_vars[comp],
                        indicatoron=0,
                        fg=color,
                        selectcolor='#ddeeff',
                        activeforeground=color,
                        font=self.fonts['ui'],
                        relief='raised',
                        bd=2,
                        padx=8, pady=2).pack(side='left', padx=6)

        # --- Scale ---
        scale_row = ttk.Frame(parent)
        scale_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(scale_row, text="Scale:", width=13).pack(side='left')

        for s in self.SCALES:
            tk.Radiobutton(scale_row, text=s,
                        variable=self.scale_var,
                        value=s,
                        indicatoron=0,
                        font=self.fonts['ui'],
                        relief='raised',
                        bd=2,
                        padx=8, pady=2).pack(side='left', padx=6)

        # --- Theta slider ---
        azim_ctrl_row = ttk.Frame(parent)
        azim_ctrl_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(azim_ctrl_row, text="theta =", width=8).pack(side='left')

        theta_slider = ttk.Scale(azim_ctrl_row,
                                from_=self.theta_min, to=self.theta_max,
                                orient='horizontal',
                                variable=self.theta_var,
                                length=200)
        theta_slider.pack(side='left', padx=4)

        theta_entry = ttk.Entry(azim_ctrl_row,
                                textvariable=self.theta_var,
                                width=8)
        theta_entry.pack(side='left', padx=4)

        # Snap to nearest theta
        def snap_theta(*_):
            try:
                val = self.theta_var.get()
            except tk.TclError:
                return
            nearest = min(self.theta_vals, key=lambda a: abs(a - val))
            self.theta_var.set(round(nearest, 4))

        theta_slider.bind('<ButtonRelease-1>', snap_theta)
        theta_entry.bind('<Return>', snap_theta)
        theta_entry.bind('<FocusOut>', snap_theta)

        # --- Plot button ---
        ttk.Button(parent, text="Plot Azimuth",
                command=self._plot_azimuth).pack(pady=6)


    def _build_options_2d_elevation(self, parent):

        ttk.Label(parent, text="2D Elevation Options", font=self.fonts['meta1']).pack(anchor='w', pady=(0,4))



        # --- Components ---
        comp_row = ttk.Frame(parent)
        comp_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(comp_row, text="Components:", width=13).pack(side='left')

        for comp in self.COMPONENTS:
            color = self.COMP_COLORS[comp]
            tk.Checkbutton(comp_row,
                        text=comp,
                        variable=self.comp_vars[comp],
                        indicatoron=0,
                        fg=color,
                        selectcolor='#ddeeff',
                        activeforeground=color,
                        font=self.fonts['ui'],
                        relief='raised',
                        bd=2,
                        padx=8, pady=2).pack(side='left', padx=6)

        # --- Scale ---
        scale_row = ttk.Frame(parent)
        scale_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(scale_row, text="Scale:", width=13).pack(side='left')

        for s in self.SCALES:
            tk.Radiobutton(scale_row, text=s,
                        variable=self.scale_var,
                        value=s,
                        indicatoron=0,
                        font=self.fonts['ui'],
                        relief='raised',
                        bd=2,
                        padx=8, pady=2).pack(side='left', padx=6)

        # --- Phi slider ---
        elev_frame = ttk.Frame(parent)
        elev_frame.pack(fill='x', padx=8, pady=4)
        ttk.Label(elev_frame, text="phi =", width=8).pack(side='left')

        phi_slider = ttk.Scale(elev_frame,
                            from_=self.phi_min, to=self.phi_max,
                            orient='horizontal',
                            variable=self.phi_var,
                            length=200)
        phi_slider.pack(side='left', padx=4)

        phi_entry = ttk.Entry(elev_frame,
                            textvariable=self.phi_var,
                            width=8)
        phi_entry.pack(side='left', padx=4)

        # Snap to nearest phi
        def snap_phi(*_):
            try:
                val = self.phi_var.get()
            except tk.TclError:
                return
            nearest = min(self.phi_vals, key=lambda a: abs(a - val))
            self.phi_var.set(round(nearest, 4))

        phi_slider.bind('<ButtonRelease-1>', snap_phi)
        phi_entry.bind('<Return>', snap_phi)
        phi_entry.bind('<FocusOut>', snap_phi)

        # --- Hemisphere selector ---
        hemi_row = ttk.Frame(parent)
        hemi_row.pack(fill='x', padx=8, pady=4)
        ttk.Label(hemi_row, text="Hemisphere:").pack(side='left', padx=(0, 8))

        tk.Radiobutton(hemi_row, text="Upper (0°–90°)",
                    variable=self.hemisphere_var,
                    value='upper',
                    indicatoron=0,
                    font=self.fonts['ui'],
                    relief='raised',
                    bd=2,
                    padx=8, pady=2).pack(side='left', padx=6)

        self.full_hemi_btn = tk.Radiobutton(
            hemi_row, text="Full (0°–180°)",
            variable=self.hemisphere_var,
            value='full',
            indicatoron=0,
            font=self.fonts['ui'],
            relief='raised',
            bd=2,
            padx=8, pady=2
        )
        self.full_hemi_btn.pack(side='left', padx=6)

        # --- Plot button ---
        ttk.Button(parent, text="Plot Elevation",
                command=self._plot_elevation).pack(pady=6)


    def _build_options_3d_standard(self, parent):

        ttk.Label(parent, text="3D Standard Options",
                font=self.fonts['meta1']).pack(anchor='w', pady=4)

        self.topdown_var = tk.BooleanVar(value=False)

        # --- Surface shape radio buttons ---
        surf_row = tk.Frame(parent)
        surf_row.pack(anchor='w', pady=2)
        ttk.Label(surf_row, text="Surface:").pack(side='left', padx=(0,4))
        for lbl, val in [('Linear', 'linear'), ('ARRL', 'arrl')]:
            tk.Radiobutton(surf_row, text=lbl,
                           variable=self.surface_var, value=val,
                           font=self.fonts['meta2']).pack(side='left', padx=4)

        # --- Plot button ---
        ttk.Button(parent, text="Plot 3D",
                command=self._plot_3d).pack(pady=6)


    def _build_options_3d_topdown(self, parent):

        ttk.Label(parent, text="3D Top‑Down Options",
                font=self.fonts['meta1']).pack(anchor='w', pady=4)

        self.topdown_var = tk.BooleanVar(value=True)

        # --- Surface shape radio buttons ---
        surf_row = tk.Frame(parent)
        surf_row.pack(anchor='w', pady=2)
        ttk.Label(surf_row, text="Surface:").pack(side='left', padx=(0,4))
        for lbl, val in [('Linear', 'linear'), ('ARRL', 'arrl')]:
            tk.Radiobutton(surf_row, text=lbl,
                           variable=self.surface_var, value=val,
                           font=self.fonts['meta2']).pack(side='left', padx=4)

        # --- Plot button ---
        ttk.Button(parent, text="Plot 3D",
                command=self._plot_3d).pack(pady=6)

 
    def _build_options_map_overlay(self, parent):

        # ============================================================
        # MAIN HEADER
        # ============================================================
        ttk.Label(
            parent,
            text="Map Overlay Options",
            font=self.fonts['hdr2']
        ).pack(anchor='w', pady=(0, 6))

        # ============================================================
        # CONTENT FRAME — compact grid layout
        # ============================================================
        content = ttk.Frame(parent)
        content.pack(anchor='w', padx=20)

        # ── Row 0: Lat / Lon side-by-side ────────────────────────────
        self.lat_var = tk.DoubleVar(value=33.7490)
        self.lon_var = tk.DoubleVar(value=-84.3880)

        ttk.Label(content, text="Lat:", font=self.fonts['ui']).grid(
            row=0, column=0, sticky='w', padx=(0, 2), pady=4)
        ttk.Entry(content, textvariable=self.lat_var, width=10).grid(
            row=0, column=1, sticky='w', padx=(0, 16), pady=4)

        ttk.Label(content, text="Lon:", font=self.fonts['ui']).grid(
            row=0, column=2, sticky='w', padx=(0, 2), pady=4)
        ttk.Entry(content, textvariable=self.lon_var, width=10).grid(
            row=0, column=3, sticky='w', pady=4)

        # ── Row 1: Projection radio buttons horizontal ───────────────
        self.map_proj_var = tk.StringVar(value="World")

        proj_frame = ttk.Frame(content)
        proj_frame.grid(row=1, column=0, columnspan=4, sticky='w', pady=4)

        ttk.Label(proj_frame, text="Projection:", font=self.fonts['ui']).pack(
            side='left', padx=(0, 8))
        for label, value in [("Azimuthal World", "World"),
                              ("CONUS Map",       "CONUS"),
                              ("Local Footprint", "local")]:
            ttk.Radiobutton(proj_frame, text=label,
                            variable=self.map_proj_var,
                            value=value).pack(side='left', padx=(0, 12))

        # ── Row 2: Zoom + range hint + Rotation on same row ─────────
        self.zoom_var         = tk.DoubleVar(value=1.0)
        self.rotation_var     = tk.DoubleVar(value=0.0)
        self.footprint_km_var = tk.DoubleVar(value=3000.0)   # default for World
        self.compass_rose_var = tk.BooleanVar(value=True)

        zoom_rot_frame = ttk.Frame(content)
        zoom_rot_frame.grid(row=2, column=0, columnspan=4, sticky='w', pady=4)

        ttk.Label(zoom_rot_frame, text="Zoom:", font=self.fonts['ui']).pack(
            side='left', padx=(0, 2))

        def validate_zoom(new_value):
            try:
                float(new_value)
                return True
            except ValueError:
                return False

        vcmd = (parent.register(validate_zoom), "%P")
        zoom_entry = ttk.Entry(zoom_rot_frame, textvariable=self.zoom_var, width=6,
                               validate="key", validatecommand=vcmd)
        zoom_entry.pack(side='left', padx=(0, 4))

        self.zoom_range_label = ttk.Label(zoom_rot_frame, text="",
                                          font=self.fonts['ui'], foreground='#666666')
        self.zoom_range_label.pack(side='left', padx=(0, 20))

        ttk.Label(zoom_rot_frame, text="Rotation (°):", font=self.fonts['ui']).pack(
            side='left', padx=(0, 2))
        ttk.Entry(zoom_rot_frame, textvariable=self.rotation_var, width=6).pack(side='left')

        # Dynamic defaults: zoom limits and footprint radius both update
        # when the projection radio button changes.
        _PROJ_DEFAULTS = {
            "World": (1.0,  3.0,  3000.0, "(1.0 – 3.0)"),
            "CONUS": (0.3,  5.0,   500.0, "(0.3 – 5.0)"),
            "local": (0.1, 10.0,   400.0, "(0.1 – 10.0)"),
        }

        def update_projection_defaults(*args):
            proj = self.map_proj_var.get()
            zmin, zmax, fp_km, label_text = _PROJ_DEFAULTS.get(
                proj, (0.3, 5.0, 500.0, ""))
            self.zoom_min, self.zoom_max = zmin, zmax
            self.zoom_range_label.config(text=label_text)
            self.footprint_km_var.set(fp_km)
            z = self.zoom_var.get()
            if z < self.zoom_min:
                self.zoom_var.set(self.zoom_min)
            elif z > self.zoom_max:
                self.zoom_var.set(self.zoom_max)

        self.map_proj_var.trace_add("write", update_projection_defaults)
        update_projection_defaults()   # initialize

        # ── Row 3: Footprint radius + Compass rose on one line ───────
        fp_rose_frame = ttk.Frame(content)
        fp_rose_frame.grid(row=3, column=0, columnspan=4, sticky='w', pady=4)

        ttk.Label(fp_rose_frame, text="Footprint radius (km):",
                  font=self.fonts['ui']).pack(side='left', padx=(0, 4))

        def validate_fp(new_value):
            try:
                float(new_value)
                return True
            except ValueError:
                return False

        fp_vcmd = (parent.register(validate_fp), "%P")
        ttk.Entry(fp_rose_frame, textvariable=self.footprint_km_var, width=8,
                  validate="key", validatecommand=fp_vcmd).pack(side='left')

        ttk.Separator(fp_rose_frame, orient='vertical').pack(
            side='left', fill='y', padx=12)

        tk.Checkbutton(fp_rose_frame,
                       text="Compass rose  (World mode)",
                       variable=self.compass_rose_var,
                       font=self.fonts['ui']).pack(side='left')

        # ── Row 4: Plot button ────────────────────────────────────────
        ttk.Button(
            content,
            text="Plot Map Overlay",
            command=self.plot_map_overlay
        ).grid(row=4, column=0, columnspan=4, sticky='w', pady=(8, 4))

    # ---------------------------------------------------------
    # MAP OVERLAY ENGINE
    # ---------------------------------------------------------
    def _compute_pattern_topdown(self):
        import numpy as np

        # Use Etotal only
        comp = 'Etotal'
        out_df = self.out_dict[comp]

        # 1) Reshape into θ×φ grid
        theta_vals_full, phi_vals, grid_scaled_full = reshape_to_grid(out_df, self.meta)

        # 2) Hemisphere mask
        if self.hemisphere == 'upper':
            mask = theta_vals_full <= 90.0
            theta_vals = theta_vals_full[mask]
            grid_scaled = grid_scaled_full[mask, :]
        else:
            theta_vals = theta_vals_full
            grid_scaled = grid_scaled_full

        # 3) Extract E_mag grid
        theta_unique = np.sort(out_df['theta_deg'].unique())
        phi_unique   = np.sort(out_df['phi_deg'].unique())
        nTheta_full  = len(theta_unique)
        nPhi_full    = len(phi_unique)

        E_mag_full = out_df['E_mag'].values.reshape(nTheta_full, nPhi_full)

        if self.hemisphere == 'upper':
            E_mag = E_mag_full[mask, :]
        else:
            E_mag = E_mag_full

        # 4) Max radius per phi (this is the real 3D top‑down footprint)
        # Use gain (E²) so the footprint reflects radiated power density,
        # not raw E-field amplitude.
        _r = E_mag / np.max(E_mag)
        R  = _r ** 2
        r_norm = np.max(R, axis=0)

        # 5) Phi array
        phi_deg = phi_unique

        return phi_deg, r_norm

    
    def _apply_rotation(self, phi, rotation_deg):
        return (phi + rotation_deg) % 360

    def _overlay_pattern_polar(self, ax, lat, lon, lon0=None, lat0=None):
        import cartopy.crs as ccrs
        import numpy as np

        # Close the loop so the overlay renders as a ring, not an open arc
        lon_c = np.append(lon, lon[0])
        lat_c = np.append(lat, lat[0])

        # Semi-transparent fill so land/sea context shows through
        ax.fill(lon_c, lat_c,
                transform=ccrs.PlateCarree(),
                color='red', alpha=0.20, zorder=9)

        # Solid outline ring
        ax.plot(lon_c, lat_c,
                transform=ccrs.PlateCarree(),
                color='red', linewidth=2.0, zorder=10)

        # Antenna location marker
        if lon0 is not None and lat0 is not None:
            ax.plot(lon0, lat0,
                    transform=ccrs.PlateCarree(),
                    marker='+', color='red',
                    markersize=12, markeredgewidth=2.0,
                    linestyle='none', zorder=11)


    def plot_map_overlay(self):

        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs
        import cartopy
        import numpy as np
        import cartopy.feature as cfeature

        #print("Entered plot_map_overlay")

        # ---------------------------------------------------------
        # 1) Read GUI inputs
        # ---------------------------------------------------------
        lat0 = self.lat_var.get()
        lon0 = self.lon_var.get()
        proj_type = self.map_proj_var.get()
        rotation = self.rotation_var.get()
        zoom = self.zoom_var.get()

        # Map overlay always uses upper hemisphere — only upward radiation
        # (theta 0°–90°) propagates across the earth's surface.
        self.hemisphere = 'upper'

        # Enforce mode-specific limits
        zoom = max(self.zoom_min, min(self.zoom_max, zoom))

        #print('zoom = ', zoom , self.zoom_min, self.zoom_max )

        # ---------------------------------------------------------
        # 3) Compute antenna pattern (top‑down)
        # ---------------------------------------------------------
        phi, r = self._compute_pattern_topdown()
        phi_rot = self._apply_rotation(phi, rotation)

        # ---------------------------------------------------------
        # 4) Convert normalized radius r → geographic lat/lon
        # ---------------------------------------------------------
        # Footprint radius comes from the GUI entry; per-projection defaults
        # are set automatically when the projection radio button changes.
        max_range_km = self.footprint_km_var.get()

        # Geodetically accurate footprint using WGS-84 ellipsoid.
        # Replaces the flat-Earth km_per_deg approximation, which can be
        # 5-10 % off at high latitudes or for large (>500 km) footprints.
        from pyproj import Geod
        _geod      = Geod(ellps="WGS84")
        radius_m   = r * max_range_km * 1000.0   # element-wise, metres
        lon, lat, _ = _geod.fwd(
            np.full_like(phi_rot, lon0),   # origin longitude (deg)
            np.full_like(phi_rot, lat0),   # origin latitude  (deg)
            phi_rot,                        # forward azimuth CW from North (deg)
            radius_m                        # distance (m)
        )

        # ---------------------------------------------------------
        # 5) Compute bounding box + padding
        # ---------------------------------------------------------
        lat_min = lat.min()
        lat_max = lat.max()
        lon_min = lon.min()
        lon_max = lon.max()

        pad_lat = (lat_max - lat_min) * 0.10
        pad_lon = (lon_max - lon_min) * 0.10

        # ---------------------------------------------------------
        # 6) Create figure + axes
        # ---------------------------------------------------------

        if proj_type == "World":

            proj = ccrs.AzimuthalEquidistant(
                central_latitude=lat0,
                central_longitude=lon0
            )

            fig = plt.figure(figsize=(6, 6))
            fig.set_size_inches(6, 6, forward=True)

            # Leave margins so the title (top) and compass labels (sides/bottom)
            # are not clipped by the figure boundary.
            # 6% left/right/bottom for E/W/S labels; 12% top for N label + title.
            fig.subplots_adjust(left=0.06, right=0.94, bottom=0.06, top=0.88)
            ax = fig.add_subplot(111, projection=proj)

            R_default = 19_970_000

            # Compute zoomed radius
            R = R_default / zoom

            # Azimuthal Equal Distance: AEQD out to 1/2 earth circumference
            # from center point defined by lat/lon

            # Clamp R so it never exceeds the AEQD limit
            R = min(R, 19_970_000)

            ax.set_extent([-R, R, -R, R], crs=proj)

            # Clip to a clean circle so AEQD renders as a globe disc,
            # not a square frame with clipped corners.
            import matplotlib.path as mpath
            _theta = np.linspace(0, 2 * np.pi, 200)
            _verts = np.column_stack([np.sin(_theta), np.cos(_theta)]) * 0.5 + [0.5, 0.5]
            ax.set_boundary(mpath.Path(_verts), transform=ax.transAxes)

            ax.add_feature(cfeature.LAND.with_scale('110m'),  facecolor='#eae6df')
            ax.add_feature(cfeature.OCEAN.with_scale('110m'), facecolor='lightblue')
            ax.add_feature(cfeature.BORDERS.with_scale('110m'), linewidth=0.8)
            ax.add_feature(cfeature.COASTLINE.with_scale('110m'), linewidth=0.8)

            # Unlabeled gridlines — AEQD arcs don't support reliable labels
            ax.gridlines(draw_labels=False, linewidth=0.4, color='gray',
                         alpha=0.5, linestyle='--')


            # ── Optional compass rose around the AEQD circle boundary ──
            # All coordinates are in transAxes (0–1), where the boundary
            # circle has centre (0.5, 0.5) and radius 0.5.
            if self.compass_rose_var.get():
                import numpy as np
                _CR_COLOR  = '#333333'
                _CR_FONT   = dict(fontsize=9, fontweight='bold',
                                  color=_CR_COLOR, clip_on=False)
                # Cardinals: (label, x_axes, y_axes, ha, va)
                _cardinals = [
                    ('N', 0.500,  1.040, 'center', 'bottom'),
                    ('S', 0.500, -0.040, 'center', 'top'),
                    ('E', 1.040,  0.500, 'left',   'center'),
                    ('W', -0.040, 0.500, 'right',  'center'),
                ]
                for lbl, x, y, ha, va in _cardinals:
                    ax.text(x, y, lbl, transform=ax.transAxes,
                            ha=ha, va=va, **_CR_FONT)

                # Major tick marks at N/S/E/W, minor at 45° intervals
                _tick_major = 0.035
                _tick_minor = 0.020
                _directions = np.arange(0, 360, 45)
                for _az in _directions:
                    _rad = np.radians(_az)
                    _dx  = np.sin(_rad)
                    _dy  = np.cos(_rad)
                    _tl  = _tick_major if _az % 90 == 0 else _tick_minor
                    x1, y1 = 0.5 + _dx * 0.5, 0.5 + _dy * 0.5       # on boundary
                    x2, y2 = 0.5 + _dx * (0.5 - _tl), 0.5 + _dy * (0.5 - _tl)  # inward
                    ax.plot([x1, x2], [y1, y2],
                            transform=ax.transAxes,
                            color=_CR_COLOR, linewidth=1.4 if _az % 90 == 0 else 0.8,
                            clip_on=False)

            _map_title = (
                f"{self.meta.get('title', 'Antenna')}"
                f"  |  {self.meta.get('freq_str', '?')}"
                f"  |  Footprint: {max_range_km:.0f} km"
            )
            ax.set_title(_map_title, fontsize=9, pad=6)
            self._overlay_pattern_polar(ax, lat, lon, lon0, lat0)

            plt.show(block=False)
            plt.pause(0.05)
            return

        elif proj_type == "CONUS":

            proj = ccrs.LambertConformal(
                central_latitude=33.0,
                central_longitude=-95.0,
                standard_parallels=(33, 45)
            )

            fig = plt.figure(figsize=(6, 6))
            fig.set_size_inches(6, 6, forward=True)
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

            ax = fig.add_subplot(111, projection=proj)
            ax.set_position([0, 0, 1, 1])
            ax.set_aspect('equal', 'box')

            # CONUS extent (tight but safe)
            # CONUS zoom logic: apply zoom factor around fixed CONUS centre

            # Original CONUS bounding box
            lon_w, lon_e = -125.0, -66.5
            lat_s, lat_n = 24.0, 50.0

            # Fixed center of CONUS
            lon_center = (lon_w + lon_e) / 2.0
            lat_center = (lat_s + lat_n) / 2.0

            # Half‑ranges of the original box
            lon_half = (lon_e - lon_w) / 2
            lat_half = (lat_n - lat_s) / 2

            # Apply zoom (zoom > 1 = zoom in, zoom < 1 = zoom out)
            lon_half_zoomed = lon_half / zoom
            lat_half_zoomed = lat_half / zoom

            # New zoomed extent centered on antenna
            ax.set_extent(
                [lon_center - lon_half_zoomed,
                lon_center + lon_half_zoomed,
                lat_center - lat_half_zoomed,
                lat_center + lat_half_zoomed],
                crs=ccrs.PlateCarree()
            )

            ax.add_feature(cfeature.LAND.with_scale('110m'),     facecolor='#eae6df')
            ax.add_feature(cfeature.OCEAN.with_scale('110m'),    facecolor='lightblue')
            ax.add_feature(cfeature.COASTLINE.with_scale('110m'), linewidth=0.6)
            ax.add_feature(cfeature.BORDERS.with_scale('110m'),  linewidth=0.6)
            ax.add_feature(cfeature.STATES.with_scale('110m'),   linewidth=0.3)

            gl = ax.gridlines(draw_labels=True, linewidth=0.4, color='gray',
                              alpha=0.5, linestyle='--')
            gl.top_labels   = False
            gl.right_labels = False


            # Draw footprint
            _map_title = (
                f"{self.meta.get('title', 'Antenna')}"
                f"  |  {self.meta.get('freq_str', '?')}"
                f"  |  Footprint: {max_range_km:.0f} km"
            )
            ax.set_title(_map_title, fontsize=9, pad=6)
            self._overlay_pattern_polar(ax, lat, lon, lon0, lat0)

            plt.show(block=False)
            plt.pause(0.05)
            return

        elif proj_type == "local":

            proj = ccrs.PlateCarree()

             # Create figure + axes FIRST
            fig = plt.figure(figsize=(6, 6))
            fig.set_size_inches(6, 6, forward=True)
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

            ax = fig.add_subplot(111, projection=proj)
            ax.set_position([0, 0, 1, 1])
            ax.set_aspect('equal', 'box')

            # ---------------------------------------------------------
            # LOCAL ZOOM LOGIC (centered on antenna lat/lon)
            # ---------------------------------------------------------

            # Auto-zoom bounding box from footprint
            lon_min, lon_max = np.min(lon), np.max(lon)
            lat_min, lat_max = np.min(lat), np.max(lat)

            # Padding around footprint
            pad_lon = (lon_max - lon_min) * 0.25
            pad_lat = (lat_max - lat_min) * 0.25

            lon_center = lon0
            lat_center = lat0

            lon_half = (lon_max - lon_min)/2 + pad_lon
            lat_half = (lat_max - lat_min)/2 + pad_lat

            ax.set_extent(
                [lon_center - lon_half/zoom,
                lon_center + lon_half/zoom,
                lat_center - lat_half/zoom,
                lat_center + lat_half/zoom],
                crs=ccrs.PlateCarree()
            )

            # Draw base map
            ax.add_feature(cfeature.LAND.with_scale('110m'),     facecolor='#eae6df')
            ax.add_feature(cfeature.OCEAN.with_scale('110m'),    facecolor='lightblue')
            ax.add_feature(cfeature.BORDERS.with_scale('110m'),  linewidth=0.8)
            ax.add_feature(cfeature.COASTLINE.with_scale('110m'), linewidth=0.8)
            ax.add_feature(cfeature.STATES.with_scale('110m'),   linewidth=0.3)

            gl = ax.gridlines(draw_labels=True, linewidth=0.4, color='gray',
                              alpha=0.5, linestyle='--')
            gl.top_labels   = False
            gl.right_labels = False


            # Draw footprint
            _map_title = (
                f"{self.meta.get('title', 'Antenna')}"
                f"  |  {self.meta.get('freq_str', '?')}"
                f"  |  Footprint: {max_range_km:.0f} km"
            )
            ax.set_title(_map_title, fontsize=9, pad=6)
            self._overlay_pattern_polar(ax, lat, lon, lon0, lat0)

            plt.show(block=False)
            plt.pause(0.05)
            return

        # ---------------------------------------------------------
        # 9) Draw radial lines (optional)
        # ---------------------------------------------------------
        #self._draw_radial_lines(ax, lat0, lon0, proj)
        #self._draw_radial_lines(ax, lat0, lon0, proj_type)

        #print("Plotting footprint with", len(phi_rot), "points")

        # ---------------------------------------------------------
        # 10) Draw antenna footprint
        # ---------------------------------------------------------
        self._overlay_pattern_polar(ax, lat, lon)

        # ---------------------------------------------------------
        # 11) Show
        # ---------------------------------------------------------
        plt.show(block=False)
        plt.pause(0.05)
   
   
    def __init__(self, root, out_dict, meta, df):
        self.root = root
        self.out_dict = out_dict
        self.meta = meta
        self.df = df
        self.hemisphere = 'upper'


        # 1) Define spacing + fonts FIRST
        self.PADX_SECTION = 5
        self.PADY_SECTION = 12
        self.PADX_INDENT = 75
        self.PADY_ITEM = 4


        self.fonts = {
            'hdr1':  ('Segoe UI', 13, 'bold'),
            'hdr2':  ('Segoe UI', 12, 'bold'),
            'hdr3':  ('Segoe UI', 10, 'bold'),
            'ui':    ('Segoe UI', 11),
            'meta1': ('Segoe UI', 13, 'bold'),
            'meta2': ('Segoe UI', 12),
            'meta3': ('Segoe UI', 11),         
        }

        style = ttk.Style()
        style.configure("Bold.TLabelframe.Label", font=self.fonts['hdr2'])


        # Slider ranges from actual data
        self.phi_vals   = sorted(df['phi_deg'].unique())
        self.theta_vals = sorted(df['theta_deg'].unique())
        self.phi_min    = float(self.phi_vals[0])
        self.phi_max    = float(self.phi_vals[-1])
        self.theta_min  = float(self.theta_vals[0])
        self.theta_max  = float(self.theta_vals[-1])

        # Default cut angles from metadata
        peak_theta, peak_phi = meta.get('e_total_max', (25.0, 90.0))
        self.phi_var   = tk.DoubleVar(value=peak_phi)
        self.theta_var = tk.DoubleVar(value=peak_theta)

        # Scale and hemisphere
        self.scale_var      = tk.StringVar(value='ARRL')
        self.hemisphere_var  = tk.StringVar(value='upper')
        self.surface_var     = tk.StringVar(value='linear')  # 'linear' | 'arrl'

        # Component checkboxes — all on by default
        self.comp_vars = {c: tk.BooleanVar(value=True)
                          for c in self.COMPONENTS}

        #-------------April 30
        self.vis_mode = tk.StringVar(value="2D-Azimuth")  # default

        self.root.title("Antenna Pattern Viewer")
        self.root.resizable(False, False)

 
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        #-------------

    # ----------------------------------------------------------------
    # SECTION 3: UI construction
    # ----------------------------------------------------------------

    def _build_ui(self):

        PAD = dict(padx=8, pady=4)

        self.PADX_SECTION = 5
        self.PADY_SECTION = 10

        self.PADX_INDENT = 75
        self.PADY_ITEM = 4



        # -----------------------------------------
        # Antenna metadata panel (should be FIRST)
        # -----------------------------------------
        info_frame = _make_box(self.root, title='Antenna',
                            font=self.fonts['meta1'], pad=4)

        info_frame.pack(fill='x', padx=self.PADX_SECTION, pady=self.PADY_SECTION)


        title_str = self.meta.get('title', 'Unknown')
        freq_str  = self.meta.get('freq_str',  '?')
        gain      = self.meta.get('gain_peak_dbi', '?')
        gain_str  = f"{gain:.3g}" if isinstance(gain, float) else str(gain)
        imp_str   = self.meta.get('impedance_str', '?')
        swr_str   = self.meta.get('swr_str', '?')
        gnd_str   = self.meta.get('ground_type', '?')
        hgt_str   = self.meta.get('height_str', '?')
        _h  = self.meta.get('height_above_ground')
        _wl = self.meta.get('wavelength_m')
        if isinstance(_h, float) and isinstance(_wl, float) and _wl > 0:
            hgt_lam_str = f"{_h / _wl:.3f} \u03bb"
        else:
            hgt_lam_str = '?'

        ttk.Label(info_frame,
                text=f"{title_str}    {freq_str}    Peak gain: {gain_str} dBi",
                font=self.fonts['meta1']).pack(**PAD)
        
        #ttk.Label(info_frame, text=..., font=...).pack(anchor='w', pady=2)

        ttk.Label(info_frame,
                text=f"Z = {imp_str}    SWR = {swr_str}",
                font=self.fonts['meta2']).pack(anchor='center', pady=2)
                #font=self.fonts['meta_r2']).pack(**PAD)

        ttk.Label(info_frame,
                text=f"Ground: {gnd_str}    Height: {hgt_str}  ({hgt_lam_str})",
                font=self.fonts['meta3']).pack(**PAD)

        # -----------------------------------------
        # Control frame (mode selector + options panel)
        # -----------------------------------------
        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(fill='x', padx=8, pady=4)

        # Visualization Mode Selector
        mode_frame = ttk.LabelFrame(
            self.control_frame,
            #self.root,
            text="Visualization Mode",
            labelanchor='nw',
            padding=8,
            style="Bold.TLabelframe"
        )
    

        # Indented padded container
        mode_inner = ttk.Frame(mode_frame)
        mode_frame.pack(fill='x', padx=self.PADX_SECTION, pady=self.PADY_SECTION)
        mode_inner.pack(fill='x', padx=self.PADX_INDENT, pady=self.PADY_ITEM)

        modes = [
            ("2D – Azimuth",   "2D-Azimuth"),
            ("2D – Elevation", "2D-Elevation"),
            ("3D – Standard",  "3D-Standard"),
            ("3D – Top-Down",  "3D-TopDown"),
            ("Map Overlay",    "Map-Overlay"),
        ]

        for label, value in modes:
            ttk.Radiobutton(
                mode_inner,
                text=label,
                variable=self.vis_mode,
                value=value,
                command=self.on_mode_change
            ).pack(anchor="w", pady=4)   # more vertical spacing



        # -----------------------------------------
        # -----------------------------------------
        self.options_panel = ttk.Frame(self.control_frame)
        options_frame = ttk.LabelFrame(self.control_frame, text="Options")

        options_frame.pack(fill='x', padx=self.PADX_SECTION, pady=self.PADY_SECTION)
        self.options_panel.pack(fill='x', padx=self.PADX_INDENT, pady=self.PADY_ITEM)



        # Build initial panel for default mode
        self._build_options_panel()

        # -----------------------------------------
        # Bottom bar: Close All Plots + Status
        # Single row — button left, status text fills the rest.
        # Packing order: bottom bar first (side='bottom') so the
        # options panel above it never overlaps it.
        # -----------------------------------------
        self.status_var = tk.StringVar(value="Ready.")

        bottom_bar = tk.Frame(self.root, relief='sunken', bd=1)
        bottom_bar.pack(fill='x', side='bottom')

        ttk.Button(bottom_bar, text="Close All Plots",
                   command=self._close_plots).pack(side='left', padx=(4, 8), pady=2)

        ttk.Label(bottom_bar, textvariable=self.status_var,
                  anchor='w', padding=(0, 2)).pack(side='left', fill='x', expand=True)


        # -----------------------------------------
        # Ground-plane interlocks (unchanged)
        # -----------------------------------------
        self._apply_ground_plane_interlocks()

    # ----------------------------------------------------------------
    # Ground-plane interlock logic
    # ----------------------------------------------------------------

    def _apply_ground_plane_interlocks(self):
        """
        When ground is not FREE_SPACE, force upper hemisphere and
        disable full-sphere selection. Also guard against any attempt
        to set hemisphere to 'full'.
        """

        # If hemisphere widgets haven't been created yet, skip
        if not hasattr(self, "full_hemi_btn"):
            return

        gp = str(self.meta.get('ground_type', 'FREE_SPACE')).upper()

        if gp != "FREE_SPACE":
            # Force upper hemisphere
            self.hemisphere_var.set('upper')

            # Disable full hemisphere button in 2D Elevation panel
            self.full_hemi_btn.config(state='disabled')

            # Guard: if hemisphere somehow becomes 'full', pop up and reset
            def hemi_guard(*_):
                if self.hemisphere_var.get() == 'full':
                    messagebox.showinfo(
                        "Not allowed",
                        "Full-sphere plotting is disabled when a ground plane "
                        "is present."
                    )
                    self.hemisphere_var.set('upper')

            self.hemisphere_var.trace_add("write", hemi_guard)

        else:
            # Free space → allow full sphere
            self.full_hemi_btn.config(state='normal')

    # ----------------------------------------------------------------
    # Component + scale helper
    # ----------------------------------------------------------------

    def _get_out_dict(self):
        """Build out_dict from current checkbox + scale state."""
        scale      = self.scale_var.get()
        comp_flags = {c: v.get() for c, v in self.comp_vars.items()}
        out_dict   = compute_out_dicts(self.df, self.meta, scale, comp_flags)

        if not out_dict:
            messagebox.showwarning("No components selected",
                                   "Please check at least one component.")
            return None, None
        return out_dict, scale

    # ----------------------------------------------------------------
    # Plot actions
    # ----------------------------------------------------------------

    def _plot_elevation(self):
        out_dict, scale = self._get_out_dict()
        if out_dict is None:
            return
        phi        = self.phi_var.get()
        hemisphere = self.hemisphere_var.get()
        self.status_var.set(
            f"Plotting elevation at phi={phi:.1f}° [{hemisphere}]...")
        self.root.update()
        try:
            plot_elevation_polar_overlay(out_dict, self.meta, scale,
                                         phi, hemisphere=hemisphere)
            plt.pause(0.05)
            self.status_var.set(
                f"Elevation plotted  phi={phi:.1f}°  [{hemisphere}]")
        except Exception as e:
            messagebox.showerror("Plot error", str(e))
            self.status_var.set("Error — see dialog.")

    def _plot_azimuth(self):
        out_dict, scale = self._get_out_dict()
        if out_dict is None:
            return
        theta = self.theta_var.get()
        self.status_var.set(
            f"Plotting azimuth at theta={theta:.1f}°...")
        self.root.update()
        try:
            plot_azimuth_polar_overlay(out_dict, self.meta, scale, theta)
            plt.pause(0.05)
            self.status_var.set(f"Azimuth plotted  theta={theta:.1f}°")
        except Exception as e:
            messagebox.showerror("Plot error", str(e))
            self.status_var.set("Error — see dialog.")

    def _plot_both(self):
        out_dict, scale = self._get_out_dict()
        if out_dict is None:
            return
        phi        = self.phi_var.get()
        theta      = self.theta_var.get()
        hemisphere = self.hemisphere_var.get()
        self.status_var.set("Plotting both...")
        self.root.update()
        try:
            plot_elevation_polar_overlay(out_dict, self.meta, scale,
                                         phi, hemisphere=hemisphere)
            plot_azimuth_polar_overlay(out_dict, self.meta, scale, theta)
            plt.pause(0.05)
            self.status_var.set(
                f"Elevation phi={phi:.1f}° [{hemisphere}]  |  "
                f"Azimuth theta={theta:.1f}°")
        except Exception as e:
            messagebox.showerror("Plot error", str(e))
            self.status_var.set("Error — see dialog.")

    # ----------------------------------------------------------------
    # 3‑D plot with Etotal-only interlock
    # ----------------------------------------------------------------

    def _plot_3d(self):
        """
        3‑D far‑field patterns always use Etotal.
        Ev and Eh are silently disabled.
        """

        comp_flags = {c: v.get() for c, v in self.comp_vars.items()}

        # 3D plots always use Etotal
        self.comp_vars["Ev"].set(False)
        self.comp_vars["Eh"].set(False)
        self.comp_vars["Etotal"].set(True)



        # Now recompute with corrected flags
        out_dict, scale = self._get_out_dict()
        if out_dict is None:
            return

        hemisphere = self.hemisphere_var.get()
        self.status_var.set(f"Plotting 3D pattern [{hemisphere}]...")
        self.root.update()

        #---------------
        try:
            from plot_3d import plot_3d_pattern, plot_3d_pattern_topdown

            #print("META KEYS:", meta.keys())
            #print("gain_peak_dBi =", meta.get("gain_peak_dBi"))

            surface_mode = self.surface_var.get()
            if self.topdown_var.get():
                plot_3d_pattern_topdown(out_dict, self.meta, scale,
                                        hemisphere=hemisphere,
                                        annotation_mode='lobe',
                                        surface_mode=surface_mode)
            else:
                plot_3d_pattern(out_dict, self.meta, scale,
                                hemisphere=hemisphere,
                                annotation_mode='lobe',
                                surface_mode=surface_mode)

            plt.pause(0.05)
            self.status_var.set(f"3D pattern plotted [{hemisphere}].")



        except Exception as e:
            messagebox.showerror("Plot error", str(e))
            self.status_var.set("Error — see dialog.")

    def _close_plots(self):
        plt.close('all')
        self.status_var.set("All plot windows closed.")

    def _on_close(self):
        """Called when the main window is closed — destroy all plot windows first."""
        plt.close('all')
        self.root.destroy()


# ----------------------------------------------------------------
# SECTION 5: Entry point
# ----------------------------------------------------------------

if __name__ == '__main__':

    # ----------------------------------------------------------------
    # Resolve input file path:
    #   1) Use command-line argument if provided
    #   2) Otherwise open a file dialog to let the user pick a CSV
    # ----------------------------------------------------------------
    if len(sys.argv) >= 2:
        filepath = sys.argv[1]
    else:
        # Need a temporary root window to host the dialog,
        # then withdraw it so only the dialog appears.
        _prefs    = _load_prefs()
        _last_dir = _prefs.get('last_dir', str(Path.home()))

        _picker = tk.Tk()
        _picker.withdraw()
        _picker.attributes("-topmost", True)   # dialog appears on top
        filepath = filedialog.askopenfilename(
            title="Select antenna CSV file",
            initialdir=_last_dir,
            filetypes=[
                ("CSV files",  "*.csv"),
                ("All files",  "*.*"),
            ]
        )
        _picker.destroy()

        if not filepath:
            # User cancelled the dialog — exit cleanly
            sys.exit(0)

        # Remember this directory for next launch
        _save_prefs({'last_dir': str(Path(filepath).parent)})

    # 1. Load raw CSV
    meta, df = load_data(filepath)

    # 2. Build out_dict using the same logic as the 3D plotter
    #    Enable all components by default
    comp_flags = {'Ev': True, 'Eh': True, 'Etotal': True}
    scale = 'Linear'   # or your default scale
    out_dict = compute_out_dicts(df, meta, scale, comp_flags)

    #print('meta : ', meta)
    #print()
    #print('df : ', df)
    #print('')
    #print('out_dict :', out_dict)

    
    # 3. Launch GUI with all required data
    root = tk.Tk()
    app = AntennaGUI(root, out_dict, meta, df)
    root.mainloop()