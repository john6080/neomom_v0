"""
cur_viewer.py  —  NeoMoM current distribution visualizer
=========================================================
Usage:
    python cur_viewer.py                        # opens file dialog
    python cur_viewer.py antenna.cur            # loads directly
    python cur_viewer.py antenna.cur --no-gui   # saves PNGs, no window

Column format:
    8-column (legacy):
        1 : basis function index
        2 : X  (m)
        3 : Y  (m)
        4 : Z  (m)
        5 : I_real (A)
        6 : I_imag (A)
        7 : |I|    (A)
        8 : phase  (deg)

    10-column (current — preferred):
        1-8 : same as above
        9   : wire tag, half(1) / anchor segment   (e.g. 'W1')
        10  : wire tag, half(2) / partner segment   (e.g. 'W1', or 'W2' at a junction)

    When columns 9-10 are present, wire identity comes directly from the
    solver (ground truth) instead of being inferred from geometry.  A row
    where col9 != col10 is a junction basis function whose two halves
    belong to different wire primitives.
"""

import sys
import os
import argparse

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker
import matplotlib.colors as mcolors
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401 — registers projection
from mpl_toolkits.mplot3d.art3d import Line3DCollection


def _cmap(name):
    """Matplotlib >=3.7 deprecates get_cmap; this wrapper stays compatible."""
    try:
        return matplotlib.colormaps[name]
    except AttributeError:
        return matplotlib.cm.get_cmap(name)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_cur_file(path: str) -> dict:
    """
    Read a NeoMoM .cur file and return arrays ready for plotting.

    Column layout (1-based, matching Fortran output):
        1  row index
        2  X (m)
        3  Y (m)
        4  Z (m)
        5  I_real (A)
        6  I_imag (A)
        7  |I|    (A)
        8  phase  (deg)

    Optional header lines (start with #, before data):
        # title      = My Antenna
        # frequency  = 14.2  MHz
        # n_basis    = 128
        # node    TAG  x  y  z
        # excite  TAG  voltage_mag  phase_deg

    Node positions are matched to the nearest basis function row by
    minimum Euclidean distance — exact by construction since every node
    is guaranteed to coincide with a rooftop center.

    Excitation lines reference a TAG already defined by a # node line —
    coordinates are looked up from that node rather than repeated.
    """
    nodes       = []   # list of dict: tag, x, y, z, row (matched after data load)
    excitations = []  # list of dict: tag, voltage, phase_deg (xyz/row filled later)
    meta        = {}   # title, frequency, n_basis etc.
    rows        = []
    wire_tag_pairs = []  # per-row (tag1, tag2) from cols 9-10, or None if absent

    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            # ── header lines ─────────────────────────────────────────────────
            if line.startswith("#"):
                inner = line[1:].strip()

                # node line:  node  TAG  x  y  z
                if inner.lower().startswith("node"):
                    parts = inner.split()
                    if len(parts) >= 5:
                        try:
                            nodes.append(dict(
                                tag = parts[1],
                                x   = float(parts[2]),
                                y   = float(parts[3]),
                                z   = float(parts[4]),
                                row = None,   # filled after data loaded
                            ))
                        except ValueError:
                            pass
                # excite line:  excite  TAG  voltage_mag  phase_deg
                elif inner.lower().startswith("excite"):
                    parts = inner.split()
                    if len(parts) >= 4:
                        try:
                            excitations.append(dict(
                                tag     = parts[1],
                                voltage = float(parts[2]),
                                phase   = float(parts[3]),
                            ))
                        except ValueError:
                            pass
                # key = value metadata
                elif "=" in inner:
                    k, _, v = inner.partition("=")
                    meta[k.strip().lower()] = v.strip()
                continue

            # ── data lines ───────────────────────────────────────────────────
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                rows.append([float(p) for p in parts[:8]])
            except ValueError:
                continue
            # Optional wire-tag columns 9-10 (ground truth from solver)
            if len(parts) >= 10:
                wire_tag_pairs.append((parts[8], parts[9]))
            else:
                wire_tag_pairs.append(None)

    if not rows:
        raise ValueError(f"No readable data found in '{path}'")

    data    = np.array(rows)

    seg_idx = data[:, 0].astype(int)
    x       = data[:, 1]
    y       = data[:, 2]
    z       = data[:, 3]
    i_real  = data[:, 4]
    i_imag  = data[:, 5]
    i_mag   = data[:, 6]
    i_phase = data[:, 7]

    # ── match nodes to nearest basis function row ─────────────────────────────
    pts = np.column_stack([x, y, z])
    for nd in nodes:
        nd_pt = np.array([nd["x"], nd["y"], nd["z"]])
        dists = np.linalg.norm(pts - nd_pt, axis=1)
        nd["row"] = int(np.argmin(dists))

    # ── resolve excitation coordinates/row from the referenced node tag ──────
    node_by_tag = {nd["tag"]: nd for nd in nodes}
    resolved_excitations = []
    for ex in excitations:
        nd = node_by_tag.get(ex["tag"])
        if nd is None:
            continue          # referenced tag not found — skip silently
        resolved_excitations.append(dict(
            tag     = ex["tag"],
            voltage = ex["voltage"],
            phase   = ex["phase"],
            x       = nd["x"],
            y       = nd["y"],
            z       = nd["z"],
            row     = nd["row"],
        ))
    excitations = resolved_excitations

    # ── cumulative arc-length ─────────────────────────────────────────────────
    step_dist = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    steps     = np.concatenate([[0.0], step_dist])
    cum_arc   = np.cumsum(steps)

    # ── wire grouping ──────────────────────────────────────────────────────────
    has_wire_tags = all(p is not None for p in wire_tag_pairs) and len(wire_tag_pairs) > 0

    if has_wire_tags:
        # ── Ground-truth grouping from solver-supplied wire tags (cols 9-10) ──
        # Each row's "home" wire is its anchor tag (col 9).  A row whose two
        # tags differ (col9 != col10) is a junction basis function — its
        # second half belongs to a different wire primitive; record that
        # separately so it can be associated with both wires for rendering.
        anchor_tags = [p[0] for p in wire_tag_pairs]
        partner_tags = [p[1] for p in wire_tag_pairs]

        unique_tags = sorted(set(anchor_tags) | set(partner_tags))
        tag_to_id   = {tag: i for i, tag in enumerate(unique_tags)}

        wire_id  = np.array([tag_to_id[t] for t in anchor_tags], dtype=int)
        n_wires  = len(unique_tags)
        wire_tag_names = unique_tags   # wire_id -> real Fortran tag string

        # A wire group is a "hub" group only if every row in it is itself a
        # junction row (anchor != partner) AND those rows are not the bulk of
        # any ordinary wire — in practice with ground-truth tags every row
        # belongs to a genuine wire primitive, so nothing is flagged as hub.
        # Junction rows still get a separate "secondary wire" association so
        # the 2D plot / Zin fade logic can recognise them on both wires.
        is_hub = np.zeros(n_wires, dtype=bool)

        # secondary_wire_id[row] = wire_id of the partner tag, or -1 if row is
        # not a junction row (anchor == partner)
        secondary_wire_id = np.full(len(seg_idx), -1, dtype=int)
        for i, (a, p) in enumerate(wire_tag_pairs):
            if a != p:
                secondary_wire_id[i] = tag_to_id[p]

    else:
        # ── Fallback: geometric heuristic (legacy 8-column files) ───────────
        ZERO_TOL  = 1e-9
        nonzero   = step_dist[step_dist > ZERO_TOL]
        median_nz = np.median(nonzero) if len(nonzero) > 0 else 1.0
        threshold = 5.0 * median_nz

        wire_id   = np.zeros(len(seg_idx), dtype=int)
        w         = 0
        prev_zero = step_dist[0] < ZERO_TOL if len(step_dist) > 0 else False

        for k in range(len(step_dist)):
            s       = step_dist[k]
            is_zero = s < ZERO_TOL
            if s > threshold:
                w += 1
            elif is_zero != prev_zero:
                w += 1
            wire_id[k + 1] = w
            prev_zero = is_zero

        n_wires = int(wire_id.max()) + 1

        # Flag hub groups
        is_hub = np.zeros(n_wires, dtype=bool)
        for w_id in range(n_wires):
            mask    = wire_id == w_id
            idx     = np.where(mask)[0]
            if len(idx) < 2:
                is_hub[w_id] = True
                continue
            w_steps = step_dist[idx[:-1]]
            if np.all(w_steps < ZERO_TOL):
                is_hub[w_id] = True

        wire_tag_names    = [f"W{i+1}" for i in range(n_wires)]
        secondary_wire_id = np.full(len(seg_idx), -1, dtype=int)

    # Pull title from header meta if present
    title = meta.get("title",
                     os.path.splitext(os.path.basename(path))[0])

    return dict(
        path        = path,
        title       = title,
        meta        = meta,
        nodes       = nodes,          # list of {tag, x, y, z, row}
        excitations = excitations,    # list of {tag, voltage, phase, x, y, z, row}
        seg_idx = seg_idx,
        x       = x,
        y       = y,
        z       = z,
        i_real  = i_real,
        i_imag  = i_imag,
        i_mag   = i_mag,
        i_phase = i_phase,
        cum_arc = cum_arc,
        wire_id = wire_id,
        n_wires = n_wires,
        is_hub  = is_hub,
        wire_tag_names    = wire_tag_names,    # wire_id -> display name (real tag or W1,W2,...)
        secondary_wire_id = secondary_wire_id, # per-row partner wire_id, or -1
        has_wire_tags     = has_wire_tags,      # True if cols 9-10 were present
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot builders
# ─────────────────────────────────────────────────────────────────────────────

def build_3d_figure(d: dict, quantity: str = "magnitude", dpi: int = 100) -> plt.Figure:
    """
    3-D wire geometry coloured by |I| or phase.
    Each wire primitive is drawn as its own Line3DCollection.
    """
    fig = plt.figure(figsize=(8, 7), dpi=dpi)
    ax  = fig.add_subplot(111, projection="3d")

    if quantity == "magnitude":
        values = d["i_mag"]
        label  = "|I| (A)"
        cname  = "jet"
    else:
        values = d["i_phase"]
        label  = "Phase (°)"
        cname  = "hsv"

    cmap_ = _cmap(cname)
    norm  = mcolors.Normalize(vmin=values.min(), vmax=values.max())

    for w_id in range(d["n_wires"]):
        mask = d["wire_id"] == w_id
        wx, wy, wz = d["x"][mask], d["y"][mask], d["z"][mask]
        wv = values[mask]
        if len(wx) < 2:
            continue
        pts    = np.column_stack([wx, wy, wz])
        segs   = [[pts[i], pts[i + 1]] for i in range(len(pts) - 1)]
        colors = [(wv[i] + wv[i + 1]) / 2.0 for i in range(len(wv) - 1)]
        lc     = Line3DCollection(segs, colors=cmap_(norm(colors)), linewidth=2.5)
        ax.add_collection3d(lc)

    # Mark the global current maximum
    peak = int(np.argmax(d["i_mag"]))
    ax.scatter(d["x"][peak], d["y"][peak], d["z"][peak],
               color="red", s=60, zorder=5,
               label=f"|I|_max = {d['i_mag'][peak]:.4e} A\nseg {d['seg_idx'][peak]}")

    def padded(v, frac=0.05):
        lo, hi = v.min(), v.max()
        pad = max((hi - lo) * frac, 0.1)
        return lo - pad, hi + pad

    ax.set_xlim(*padded(d["x"]))
    ax.set_ylim(*padded(d["y"]))
    ax.set_zlim(*padded(d["z"]))
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(f"{d['title']}\n3-D  —  {label}")
    ax.legend(fontsize=8, loc="upper left")

    sm = matplotlib.cm.ScalarMappable(cmap=cmap_, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.1, label=label)

    # ── node markers ─────────────────────────────────────────────────────────
    for nd in d.get("nodes", []):
        ax.scatter(nd["x"], nd["y"], nd["z"],
                   color="white", edgecolors="black",
                   s=70, zorder=10, linewidths=1.4)
        ax.text(nd["x"], nd["y"], nd["z"], f"  {nd['tag']}",
                fontsize=12, fontweight="bold", color="black", zorder=11,
                bbox=dict(boxstyle="round,pad=0.15",
                         facecolor="white", edgecolor="none", alpha=0.75))

    # ── excitation markers — red star at the feed point; label offset to the
    # side so it doesn't sit on top of the wire/node marker.  Tag is already
    # shown by the node marker, so the label here is just the drive values.
    z_span = d["z"].max() - d["z"].min()
    z_off  = max(z_span * 0.08, 0.3)   # offset above the point, scaled to geometry

    for ex in d.get("excitations", []):
        ax.scatter(ex["x"], ex["y"], ex["z"],
                   marker="*", color="red", edgecolors="black",
                   s=260, zorder=12, linewidths=1.0)
        label_z = ex["z"] + z_off
        ax.plot([ex["x"], ex["x"]], [ex["y"], ex["y"]], [ex["z"], label_z],
                color="red", linewidth=0.8, linestyle=":", zorder=11)
        ax.text(ex["x"], ex["y"], label_z,
                f"{ex['voltage']:.2f}∠{ex['phase']:.0f}°",
                fontsize=11, fontweight="bold", color="darkred", zorder=13,
                ha="center", va="bottom",
                bbox=dict(boxstyle="round,pad=0.15",
                         facecolor="white", edgecolor="red", alpha=0.85))

    fig.tight_layout()
    return fig


def build_2d_figure(d: dict,
                    y_min: float = -500.0, y_max: float = 500.0,
                    wavelength: float = None,
                    dpi: int = 100) -> plt.Figure:
    """
    2-D plot: |I|, phase, and Zin vs arc-length, one curve per wire.
    Each wire's arc-length starts at 0.

    Zin(s) is derived directly from the complex current assuming a 1V excitation:
        Zin(s) = 1 / I_complex(s)  =>  R(s) =  I_real / |I|²
                                        X(s) = -I_imag / |I|²
                                       |Z(s)| = 1 / |I|
    Where current → 0 (wire tips) Zin → ∞ and is clipped for display.

    Zin scale (Ω) — R and X share one Y axis:
        y_min, y_max  — Y axis limits (default ±500 Ω)
    """
    # ── wavelength scaling ────────────────────────────────────────────────────
    # If wavelength supplied, express all arc-lengths in λ; else use metres.
    lam    = wavelength if (wavelength and wavelength > 0) else None
    s_scale = (1.0 / lam) if lam else 1.0
    x_label = "Position from wire midpoint (λ)" if lam else "Position from wire midpoint (m)"

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10),
                                        sharex=True, dpi=dpi)
    fig.suptitle(f"{d['title']}\nCurrent & Impedance vs Arc-Length — per wire",
                 fontsize=12)

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    global_peak    = int(np.argmax(d["i_mag"]))
    peak_annotated = False
    vis_num        = 0

    # Identify which wire(s) carry an actual excitation — only there is
    # R(s)/X(s) a physically meaningful driving-point impedance.
    excited_wire_ids = set()
    for ex in d.get("excitations", []):
        row = ex.get("row")
        if row is not None:
            excited_wire_ids.add(int(d["wire_id"][row]))

    def _wire_arc_length(mask):
        """
        Return (s_w, is_loop) for the basis functions selected by mask.

        Open wire  -> zero at the wire's own geometric midpoint, so the
                      two tips sit at roughly ±half-length (symmetric,
                      physically meaningful reference point).
        Closed loop (first and last basis function nearly coincide) ->
                      zero stays at the first basis function (mesh order);
                      a loop has no natural "two ends" to centre between.
        """
        pts   = np.column_stack([d["x"][mask], d["y"][mask], d["z"][mask]])
        steps = np.concatenate([[0.0],
                np.linalg.norm(np.diff(pts, axis=0), axis=1)])
        s_raw = np.cumsum(steps)

        if len(pts) < 2:
            return s_raw * s_scale, False

        end_to_end_gap = np.linalg.norm(pts[-1] - pts[0])
        # Typical segment spacing on this wire, for a relative tolerance
        typical_step = np.median(steps[steps > 1e-9]) if np.any(steps > 1e-9) else 1.0
        is_loop = end_to_end_gap < 0.5 * typical_step

        if is_loop:
            s_w = s_raw                      # mesh order, zero at first basis fn
        else:
            s_w = s_raw - 0.5 * s_raw[-1]    # centre on the wire's own midpoint

        return s_w * s_scale, is_loop

    for w_id in range(d["n_wires"]):
        if d["is_hub"][w_id]:
            continue
        vis_num += 1
        mask  = d["wire_id"] == w_id
        s_w, _is_loop = _wire_arc_length(mask)

        i_re  = d["i_real"][mask]
        i_im  = d["i_imag"][mask]
        mag   = d["i_mag"][mask]
        phi   = d["i_phase"][mask]
        col   = colors[vis_num % len(colors)]
        lbl   = d["wire_tag_names"][w_id]

        # ── Zin: clip where |I| is very small (within 1% of wire's own peak)
        # to avoid infinity at free tips swamping the scale
        i_mag2    = mag ** 2
        threshold = 0.01 * mag.max()
        valid     = mag > threshold

        R = np.full_like(mag, np.nan)
        X = np.full_like(mag, np.nan)
        R[valid] =  i_re[valid] / i_mag2[valid]
        X[valid] = -i_im[valid] / i_mag2[valid]

        # Zin is only a true driving-point impedance on the excited wire(s);
        # elsewhere it's a reciprocal-of-current artifact — fade it out.
        zin_alpha = 1.0 if (w_id in excited_wire_ids or not excited_wire_ids) else 0.25

        ax1.plot(s_w, mag * 1e3, color=col, linewidth=1.8, label=lbl)
        ax2.plot(s_w, phi,       color=col, linewidth=1.8, label=lbl)
        ax3.plot(s_w, R,         color=col, linewidth=1.8, label=lbl, alpha=zin_alpha)
        ax3.plot(s_w, X,         color=col, linewidth=1.8, linestyle="--", alpha=zin_alpha)

        # Annotate global |I| peak
        if not peak_annotated and np.any(mask):
            wire_indices = np.where(mask)[0]
            if global_peak in wire_indices:
                local_pos = int(np.where(wire_indices == global_peak)[0][0])
                ax1.annotate(
                    f"|I|_max\n{d['i_mag'][global_peak]*1e3:.3f} mA\n"
                    f"{lbl} seg {d['seg_idx'][global_peak]}",
                    xy=(s_w[local_pos], mag[local_pos] * 1e3),
                    xytext=(s_w[local_pos] + s_w[-1] * 0.06,
                            mag[local_pos] * 1e3 * 0.84),
                    fontsize=8, color="darkred",
                    arrowprops=dict(arrowstyle="->", color="darkred"),
                )
                peak_annotated = True

    n_visible = sum(1 for w in range(d["n_wires"]) if not d["is_hub"][w])
    ncol      = max(1, n_visible // 8)

    def _local_arc_pos(row):
        """Return (wire_id, scaled local arc-length) for a basis-function row,
        or (None, None) if the row sits on a junction hub."""
        w_id = int(d["wire_id"][row])
        if d["is_hub"][w_id]:
            return None, None
        mask      = d["wire_id"] == w_id
        idx       = np.where(mask)[0]
        s_w, _    = _wire_arc_length(mask)
        local_pos = int(np.where(idx == row)[0][0])
        return w_id, s_w[local_pos]

    # ── node markers on all three subplots ────────────────────────────────────
    for nd in d.get("nodes", []):
        row = nd.get("row")
        if row is None:
            continue
        w_id, s_node = _local_arc_pos(row)
        if w_id is None:
            continue                      # junction hub — skip 2D annotation

        for ax in (ax1, ax2, ax3):
            ax.axvline(s_node, color="dimgray", linewidth=1.1,
                       linestyle="-.", alpha=0.85)
        # Label just above the x-axis on the phase panel
        ax2.text(s_node, 165, nd["tag"],
                 fontsize=12, fontweight="bold", color="black",
                 ha="center", va="top", rotation=90,
                 bbox=dict(boxstyle="round,pad=0.15",
                          facecolor="white", edgecolor="none", alpha=0.75))

    # ── excitation markers — red, drawn after nodes so they take visual priority
    for ex in d.get("excitations", []):
        row = ex.get("row")
        if row is None:
            continue
        w_id, s_ex = _local_arc_pos(row)
        if w_id is None:
            continue

        for ax in (ax1, ax2, ax3):
            ax.axvline(s_ex, color="red", linewidth=1.6,
                       linestyle="-.", alpha=0.9, zorder=9)
        ax2.text(s_ex, -165, f"{ex['tag']}\n{ex['voltage']:.2f}∠{ex['phase']:.0f}°",
                 fontsize=11, fontweight="bold", color="darkred",
                 ha="center", va="bottom", rotation=90,
                 bbox=dict(boxstyle="round,pad=0.15",
                          facecolor="white", edgecolor="red", alpha=0.9))

        # ── Zin at the feed point — the one place on this plot where Zin is
        # an exact, physically meaningful driving-point impedance:
        #   V_feed = voltage∠phase  (as applied)
        #   I_feed = I_real[row] + j·I_imag[row]  (as solved)
        #   Zin_feed = V_feed / I_feed
        v_re = ex["voltage"] * np.cos(np.radians(ex["phase"]))
        v_im = ex["voltage"] * np.sin(np.radians(ex["phase"]))
        i_re_feed = d["i_real"][row]
        i_im_feed = d["i_imag"][row]
        i_mag_feed2 = i_re_feed**2 + i_im_feed**2

        if i_mag_feed2 > 0:
            # (v_re + j v_im) / (i_re + j i_im)
            r_feed = (v_re * i_re_feed + v_im * i_im_feed) / i_mag_feed2
            x_feed = (v_im * i_re_feed - v_re * i_im_feed) / i_mag_feed2

            ex_mask = d["wire_id"] == w_id
            s_ex_wire, _ = _wire_arc_length(ex_mask)
            span = s_ex_wire[-1] - s_ex_wire[0] if len(s_ex_wire) > 1 else 1.0

            ax3.annotate(
                f"Zin @ {ex['tag']}\n{r_feed:+.1f} {'+' if x_feed >= 0 else '-'} j{abs(x_feed):.1f} Ω",
                xy=(s_ex, max(min(r_feed, y_max), y_min)),
                xytext=(s_ex + span * 0.06, y_max * 0.7),
                fontsize=9, fontweight="bold", color="darkred",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color="darkred", linewidth=1.3),
                bbox=dict(boxstyle="round,pad=0.3",
                         facecolor="white", edgecolor="darkred", alpha=0.95),
                zorder=14,
            )

    ax1.set_ylabel("|I| (mA)")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
    ax1.legend(fontsize=8, loc="upper right", ncol=ncol)

    ax2.set_ylabel("Phase (°)")
    ax2.set_ylim(-180, 180)
    ax2.axhline(0, color="k", linewidth=0.7, linestyle="--")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
    ax2.legend(fontsize=8, loc="upper right", ncol=ncol)

    ax3.set_ylabel("Zin  (Ω)")
    ax3.set_xlabel(x_label)
    ax3.axhline(0,  color="k",      linewidth=0.7, linestyle="--")
    ax3.axhline(50, color="gray",   linewidth=0.8, linestyle=":",
                label="50 Ω ref")
    ax3.grid(True, linestyle="--", alpha=0.5)
    ax3.yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
    # Solid = R, dashed = X — add a clarifying note in the legend
    ax3.plot([], [], color="k", linewidth=1.5,               label="R (solid)")
    ax3.plot([], [], color="k", linewidth=1.5, linestyle="--", label="X (dash)")
    ax3.legend(fontsize=8, loc="upper right", ncol=ncol + 1)

    # Explanatory note — Zin away from the excitation is a reciprocal-of-
    # current artifact (can go negative), not a physical driving-point Z.
    note = ("Zin = 1/I(s), V_feed = 1∠0°.  Physically meaningful only at the\n"
           "excitation (solid lines below); elsewhere it is a reference\n"
           "artifact and may show negative R — curves there are faded.")
    ax3.text(0.01, 0.02, note, transform=ax3.transAxes,
             fontsize=7.5, color="dimgray", style="italic",
             ha="left", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3",
                      facecolor="lightyellow", edgecolor="gray", alpha=0.85))

    # ── Zin axis limits ───────────────────────────────────────────────────────
    # R and X share one Y axis.
    ax3.set_ylim(y_min, y_max)

    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Headless PNG export
# ─────────────────────────────────────────────────────────────────────────────

def save_figures(d: dict, out_dir: str = None):
    out_dir = out_dir or os.path.dirname(d["path"]) or "."
    stem    = os.path.basename(os.path.splitext(d["path"])[0])
    plots = [
        (f"{stem}_3d_magnitude.png", build_3d_figure(d, "magnitude")),
        (f"{stem}_3d_phase.png",     build_3d_figure(d, "phase")),
        (f"{stem}_2d_arclength.png", build_2d_figure(d)),
    ]
    for fname, fig in plots:
        fpath = os.path.join(out_dir, fname)
        fig.savefig(fpath, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved: {fpath}")


# ─────────────────────────────────────────────────────────────────────────────
# Tkinter GUI
# ─────────────────────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class CurViewerApp(tk.Tk):

    TABS = [
        ("3D  |I|",  "3d_mag"),
        ("3D Phase", "3d_phase"),
        ("2D Plot",  "2d"),
    ]

    def __init__(self, initial_file: str = None):
        super().__init__()

        # --------------------------------------------------------
        # HiDPI / DPI scaling — same approach as neomom_input.py
        # Windows: OS handles geometry scaling; we set tk scaling=1.0
        # and scale fonts/widgets separately via font_scale.
        # Linux/macOS: winfo_screenwidth/height report physical pixels,
        # so we scale tk directly based on detected resolution.
        # --------------------------------------------------------
        import platform
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        if platform.system() == "Windows":
            scale      = 1.0
            font_scale = 2.0
            self.tk.call('tk', 'scaling', scale)
        else:
            if sw >= 3500 and sh >= 2000:
                scale = 1.5         # 4K physical (was 3.0 — too large)
            elif sw >= 2500 and sh >= 1400:
                scale = 1.3         # 1440p physical (was 1.75)
            else:
                scale = 1.1         # 1080p baseline (was 1.2)
            font_scale = scale
            self.tk.call('tk', 'scaling', scale)

        self._font_scale = font_scale
        # Matplotlib figure DPI — keeps embedded plot text legible at the
        # same physical size as the surrounding Tk widgets.
        self._fig_dpi = int(100 * font_scale)

        style = ttk.Style(self)
        style.theme_use("default")
        base_size = 9
        ui_font   = ("TkDefaultFont", int(base_size * font_scale))
        style.configure(".", font=ui_font)
        style.configure("TNotebook.Tab",
                        font=(ui_font[0], ui_font[1], "bold"),
                        padding=[int(14 * font_scale), int(8 * font_scale)])
        self.option_add("*Font", ui_font)
        self.option_add("*Menu.font", ui_font)

        self.title("NeoMoM Current Viewer")
        if platform.system() == "Windows":
            self.geometry("700x550")     # logical px — OS scales up on 4K
        else:
            self.geometry(f"{int(1050*min(font_scale,1.6)/1.2)}x"
                          f"{int(800*min(font_scale,1.6)/1.2)}")

        self.data = None
        self._build_menu()
        self._build_toolbar()
        self._build_notebook()
        if initial_file:
            self.after(0, lambda: self._load(initial_file))

    # ── menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="Open .cur file…", command=self._open_dialog)
        fm.add_separator()
        fm.add_command(label="Save all plots as PNG…", command=self._save_pngs)
        fm.add_separator()
        fm.add_command(label="Quit", command=self.quit)
        mb.add_cascade(label="File", menu=fm)
        self.config(menu=mb)

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=6, pady=4)
        ttk.Button(bar, text="Open…",
                   command=self._open_dialog).pack(side="left", padx=4)
        self.file_label = ttk.Label(bar, text="No file loaded",
                                    foreground="#555555")
        self.file_label.pack(side="left", padx=8)

        # ── Zin scale controls ────────────────────────────────────────────────
        ttk.Separator(bar, orient="vertical").pack(side="left",
                                                   fill="y", padx=8, pady=2)

        ttk.Label(bar, text="Zin axis (Ω)  min:").pack(side="left")
        self.y_min_var = tk.StringVar(value="-500")
        ttk.Entry(bar, textvariable=self.y_min_var,
                  width=6).pack(side="left", padx=(2, 4))
        ttk.Label(bar, text="max:").pack(side="left")
        self.y_max_var = tk.StringVar(value="500")
        ttk.Entry(bar, textvariable=self.y_max_var,
                  width=6).pack(side="left", padx=(2, 8))

        ttk.Button(bar, text="Redraw Zin",
                   command=self._refresh_2d).pack(side="left", padx=4)

    # ── notebook ──────────────────────────────────────────────────────────────

    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=4, pady=4)
        self.tab_frames   = {}
        self.tab_canvases = {}
        self.tab_toolbars = {}
        self.tab_plot_holders = {}   # sub-frame inside each tab that holds the canvas

        for label, key in self.TABS:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=label)
            self.tab_frames[key] = frame

            if key == "2d":
                # Persistent control row, lives above the plot canvas and
                # survives figure redraws (only the canvas below is destroyed).
                ctrl = ttk.Frame(frame)
                ctrl.pack(side="top", fill="x", padx=4, pady=(4, 0))
                self.use_lambda_var = tk.BooleanVar(value=False)
                ttk.Checkbutton(ctrl, text="Scale x-axis by wavelength (λ)",
                                variable=self.use_lambda_var,
                                command=self._refresh_2d).pack(side="left")

                holder = ttk.Frame(frame)
                holder.pack(side="top", fill="both", expand=True)
                self.tab_plot_holders[key] = holder
            else:
                self.tab_plot_holders[key] = frame

            ttk.Label(self.tab_plot_holders[key],
                      text="Open a .cur file to view plots.",
                      foreground="#888888").pack(expand=True)

    # ── loading ───────────────────────────────────────────────────────────────

    def _open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open current file",
            filetypes=[("Current files", "*.cur"), ("All files", "*.*")],
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        try:
            self.data = parse_cur_file(path)
        except Exception as e:
            messagebox.showerror("Load Error", str(e))
            return
        self.file_label.config(text=os.path.basename(path))
        self.title(f"NeoMoM Current Viewer — {os.path.basename(path)}")
        self._render_all()

    # ── rendering ─────────────────────────────────────────────────────────────

    def _get_2d_kwargs(self) -> dict:
        """Parse toolbar entries into keyword args for build_2d_figure."""
        def _f(var, fallback):
            s = var.get().strip()
            return float(s) if s else fallback

        kw = {
            "y_min": _f(self.y_min_var, -500.0),
            "y_max": _f(self.y_max_var,  500.0),
        }

        # Wavelength scaling — read from loaded file metadata if checkbox ticked
        if self.use_lambda_var.get() and self.data is not None:
            lam = None
            wl  = self.data["meta"].get("wavelength", "")
            # strip trailing unit word if present e.g. "2.0818  m"
            try:
                lam = float(str(wl).split()[0])
            except (ValueError, IndexError):
                pass
            if lam:
                kw["wavelength"] = lam

        return kw

    def _render_all(self):
        if self.data is None:
            return
        kw = self._get_2d_kwargs()
        plots = {
            "3d_mag":   build_3d_figure(self.data, "magnitude", dpi=self._fig_dpi),
            "3d_phase": build_3d_figure(self.data, "phase",     dpi=self._fig_dpi),
            "2d":       build_2d_figure(self.data, dpi=self._fig_dpi, **kw),
        }
        for key, fig in plots.items():
            self._embed_figure(key, fig)

    def _refresh_2d(self):
        """Redraw only the 2D tab with updated scale settings — fast."""
        if self.data is None:
            return
        try:
            kw = self._get_2d_kwargs()
        except ValueError:
            messagebox.showerror("Scale Error",
                                 "Invalid scale value — please enter numbers only.")
            return
        self._embed_figure("2d", build_2d_figure(self.data, dpi=self._fig_dpi, **kw))

    def _embed_figure(self, key: str, fig: plt.Figure):
        frame = self.tab_plot_holders[key]
        if key in self.tab_canvases:
            self.tab_canvases[key].get_tk_widget().destroy()
            del self.tab_canvases[key]
        if key in self.tab_toolbars:
            self.tab_toolbars[key].destroy()
            del self.tab_toolbars[key]
        for w in frame.winfo_children():
            w.destroy()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(canvas, frame)
        toolbar.update()
        self.tab_canvases[key] = canvas
        self.tab_toolbars[key] = toolbar
        plt.close(fig)

    # ── PNG export ────────────────────────────────────────────────────────────

    def _save_pngs(self):
        if self.data is None:
            messagebox.showwarning("No data", "Load a .cur file first.")
            return
        out_dir = filedialog.askdirectory(title="Choose output folder")
        if not out_dir:
            return
        try:
            save_figures(self.data, out_dir)
            messagebox.showinfo("Done", f"4 PNG files saved to:\n{out_dir}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="NeoMoM .cur file viewer")
    ap.add_argument("file", nargs="?", help=".cur file to open")
    ap.add_argument("--no-gui", action="store_true",
                    help="Save PNG files without opening a window")
    args = ap.parse_args()

    if args.no_gui:
        if not args.file:
            ap.error("--no-gui requires a filename")
        matplotlib.use("Agg")
        print(f"Loading {args.file} …")
        d = parse_cur_file(args.file)
        save_figures(d)
        print("Done.")
        return

    initial = None
    if args.file:
        if os.path.isfile(args.file):
            initial = args.file
        else:
            print(f"Warning: file not found: {args.file}", file=sys.stderr)

    app = CurViewerApp(initial_file=initial)
    app.mainloop()


if __name__ == "__main__":
    main()