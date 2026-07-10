#!/usr/bin/env python3
"""
nml_to_nec.py  —  NeoMoM *.nml  →  NEC-5 input file translator
================================================================

Usage:
    python nml_to_nec.py  disk_8_spoke_8_wire.nml
    → writes disk_8_spoke_8_wire.nec  (same directory)

The generated .nec file can be used two ways:

  1. EZNEC Pro+
       File > Open → change file-type filter to "NEC files (*.nec)"
       Select the .nec file.  EZNEC reads the GW geometry cards and
       builds its internal wire model.  Verify wires in the wire table
       before running.

  2. NEC-5 console engine directly
       NEC5CL_x13.exe < disk_8_spoke_8_wire.nec > disk_8_spoke_8_wire.out

Supported NeoMoM features
  ✓ Straight 2-node wire primitives (any number)
  ✓ Multiple wire radii
  ✓ Single voltage excitation (wire-end or interior node)
  ✓ Single frequency
  ✓ Free space, perfect ground (PEC), or real ground plane
  ✓ Automatic segment count matching NeoMoM's even-number formula
  ✓ All length units (meters, cm, mm, feet, inches)

NEC-5 cards generated
  CM  comments
  CE  comment end
  GW  wire geometry   (one per wire_primitive)
  GE  geometry end    (0=free-space, 1=ground-plane image — used for both PEC and real)
  GN  ground params   (IPERF=1 → perfect PEC;  IPERF=2 → real Sommerfeld + epsilon, sigma)
  EX  voltage source  (type 0, delta-gap)
  FR  frequency
  RP  radiation pattern  (full sphere or upper hemisphere, 5° steps)
  EN  end
"""

import re
import sys
import os
import math

# ── physical constants ─────────────────────────────────────────────────────────
SPEED_OF_LIGHT = 299_792_458.0          # m/s  (exact SI definition)

# ── unit conversion table: input-unit → metres ────────────────────────────────
UNITS = {
    'm'          : 1.0,
    'meter'      : 1.0,   'meters'      : 1.0,
    'metre'      : 1.0,   'metres'      : 1.0,
    'cm'         : 1e-2,
    'centimeter' : 1e-2,  'centimeters' : 1e-2,
    'mm'         : 1e-3,
    'millimeter' : 1e-3,  'millimeters' : 1e-3,
    'ft'         : 0.3048,'foot'        : 0.3048, 'feet': 0.3048,
    'in'         : 0.0254,'inch'        : 0.0254, 'inches': 0.0254,
}


# ══════════════════════════════════════════════════════════════════════════════
# Namelist parser
# ══════════════════════════════════════════════════════════════════════════════

def parse_nml(path):
    """
    Minimal Fortran namelist parser.
    Returns list of (block_name_lowercase, {key_lowercase: raw_value_string}).
    Multiple blocks with the same name (e.g. &wire_primitive) are preserved
    in order.
    """
    with open(path) as fh:
        text = fh.read()

    blocks = []
    for m in re.finditer(r'&(\w+)(.*?)/', text, re.DOTALL):
        bname = m.group(1).strip().lower()
        body  = m.group(2)
        kv    = {}

        for line in body.splitlines():
            # strip whitespace and trailing Fortran list-separator comma
            line = line.strip().rstrip(',')
            # skip blank lines and comment-only lines
            if not line or line.startswith('!'):
                continue
            # strip inline comment
            if '!' in line:
                line = line[:line.index('!')].rstrip()
            if '=' not in line:
                continue

            eq_pos = line.index('=')
            key    = line[:eq_pos].strip().lower()
            val    = line[eq_pos + 1:].strip().rstrip(',')
            kv[key] = val

        blocks.append((bname, kv))

    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# Segment count — matches NeoMoM's wireprimitive_segment formula
# ══════════════════════════════════════════════════════════════════════════════

def neomom_nsegs(length, seg_len_desired):
    """
    NeoMoM always uses an even number of segments per wire section:
        nSeg = max(1, round(length / seg_len_desired))
        nSeg = nSeg + 1
        nSeg = nSeg - mod(nSeg, 2)        ! force even
    """
    ns = max(1, round(length / seg_len_desired))
    ns = ns + 1
    ns = ns - (ns % 2)
    return max(2, ns)


# ══════════════════════════════════════════════════════════════════════════════
# Main translator
# ══════════════════════════════════════════════════════════════════════════════

def nml_to_nec(nml_path):

    blocks = parse_nml(nml_path)

    # ── defaults ──────────────────────────────────────────────────────────────
    title           = 'NeoMoM antenna'
    freq_mhz        = 145.0    # fmin
    fmax_mhz        = 145.0    # fmax — mesh reference and sweep end
    fstep_mhz       = 0.0      # > 0 = fstep mode, else nFreq mode
    nFreq           = 1
    ground_type     = 'free_space'
    epsilon         = 1.0
    sigma           = 0.0
    n_per_lambda    = 20
    scale           = 1.0          # metres per input length unit
    z_height_raw    = 0.0          # zHeight in input units, before scaling
    nodes           = {}           # uppercase tag → (x, y, z) in metres
    wires           = []           # list of wire dicts
    excit           = {}

    # ── first pass: determine length unit (needed for all other quantities) ───
    for bname, kv in blocks:
        if bname == 'node_input':
            units_str  = kv.get('units', 'meters').strip("'\"").lower()
            scale      = UNITS.get(units_str, 1.0)
            z_height_raw = float(kv.get('zheight', '0.0'))

    z_offset = z_height_raw * scale   # z offset in metres

    # ── second pass: collect everything ───────────────────────────────────────
    for bname, kv in blocks:

        # -- run title --
        if bname == 'runtitle':
            title = kv.get('title', title).strip("'\"")

        # -- frequency --
        elif bname == 'frequency_mhz':
            freq_mhz  = float(kv.get('fmin',  freq_mhz))
            fmax_mhz  = float(kv.get('fmax',  freq_mhz))
            fstep_mhz = float(kv.get('fstep', 0.0))
            try:
                nFreq = int(kv.get('nfreq', 1))
            except (ValueError, TypeError):
                nFreq = 1

        # -- ground --
        elif bname == 'ground':
            ground_type = kv.get('ground_plane', ground_type).strip("'\"").lower()
            epsilon     = float(kv.get('epsilon', epsilon))
            sigma       = float(kv.get('sigma',   sigma))

        # -- options --
        elif bname == 'options':
            n_per_lambda = int(float(kv.get('nbasisperlambda', n_per_lambda)))

        # -- nodes --
        elif bname == 'node_input':
            for key, val in kv.items():
                m = re.match(r'node_list\s*\(\s*(\d+)\s*\)', key)
                if m:
                    parts = [p.strip().strip("'\"") for p in val.split(',')]
                    if len(parts) >= 4:
                        tag = parts[0].upper()
                        x   = float(parts[1]) * scale
                        y   = float(parts[2]) * scale
                        z   = float(parts[3]) * scale + z_offset
                        nodes[tag] = (x, y, z)

        # -- wire primitives (may appear many times) --
        elif bname == 'wire_primitive':
            tag    = kv.get('tag', '').strip("'\" ,").upper()
            ntstr  = kv.get('nodetags', '')
            # Strip quotes from each individual tag — write_nml writes
            # nodeTags = 'A' 'B' 'C' so each token may have quotes
            ntags  = [t.strip("'\"").upper() for t in ntstr.split() if t.strip()]
            # Wire radius is always stored in metres in the .nml —
            # independent of node coordinate units. Do NOT apply scale.
            radius = float(kv.get('radius', '0.001'))
            # Expand polyline into N-1 two-node segments.
            # Wire (A,B,C,D,E) -> A->B, B->C, C->D, D->E
            # Each segment tagged as W1_s1, W1_s2, etc. for N>2 nodes.
            if len(ntags) >= 2:
                n_segs = len(ntags) - 1
                for si in range(n_segs):
                    # Skip degenerate zero-length segments
                    if ntags[si] == ntags[si + 1]:
                        continue
                    seg_tag = tag if n_segs == 1 else f'{tag}_s{si+1}'
                    wires.append({
                        'tag'      : seg_tag,
                        'wire_tag' : tag,      # parent wire tag for excitation matching
                        'n1'       : ntags[si],
                        'n2'       : ntags[si + 1],
                        'radius'   : radius,
                        'ntags'    : ntags,    # full node list for excitation lookup
                        'seg_idx'  : si,       # 0-based segment index
                    })

        # -- excitation --
        elif bname == 'excitation_input':
            excit = {
                'wireTag'   : kv.get('wiretag',   '').strip("'\" ").upper(),
                'nodeTag'   : kv.get('nodetag',   '').strip("'\" ").upper(),
                'voltage'   : float(kv.get('voltage',   '1.0')),
                'phase_deg' : float(kv.get('phase_deg', '0.0')),
            }

    # ── derived geometry quantities ───────────────────────────────────────────
    # Mesh at fmax — ensures segment density adequate at highest frequency.
    # Over-meshes at low frequencies but ensures all resonances resolved.
    mesh_freq_mhz = fmax_mhz if fmax_mhz > freq_mhz else freq_mhz
    lambda_m      = SPEED_OF_LIGHT / (mesh_freq_mhz * 1e6)
    seg_desired   = lambda_m / n_per_lambda
    lambda_fmin_m = SPEED_OF_LIGHT / (freq_mhz * 1e6)   # for CM comments

    # ── wire ordering: feed wire first, then alphabetical ────────────────────
    feed_tag = excit.get('wireTag', '')
    wires.sort(key=lambda w: (0 if w.get('wire_tag', w['tag']) == feed_tag else 1, w['tag']))

    # ── GW cards ─────────────────────────────────────────────────────────────
    gw_lines    = []
    exc_nec_tag = 1
    exc_seg     = 1

    for i, w in enumerate(wires):
        nec_tag = i + 1
        n1      = nodes[w['n1']]
        n2      = nodes[w['n2']]
        length  = math.dist(n1, n2)
        ns      = neomom_nsegs(length, seg_desired)

        gw_lines.append(
            f"GW {nec_tag:3d} {ns:4d}"
            f"  {n1[0]:11.6f} {n1[1]:11.6f} {n1[2]:11.6f}"
            f"  {n2[0]:11.6f} {n2[1]:11.6f} {n2[2]:11.6f}"
            f"  {w['radius']:10.7f}"
            f"   ! {w['tag']}  ({w['n1']}->{w['n2']}  L={length:.4f}m  {ns} segs)"
        )

        # Excitation: match on parent wire tag and nodeTag position
        parent_match = w.get('wire_tag', w['tag']) == feed_tag
        if parent_match:
            exc_nec_tag = nec_tag
            feed_node   = excit.get('nodeTag', '')
            # source on segment 1 (near n1/start) or last segment (near n2/end)
            if   feed_node == w['n1']:
                exc_seg = 1
            elif feed_node == w['n2']:
                exc_seg = ns
            else:
                exc_seg = 1        # default to segment 1

    # ── GE / GN cards ────────────────────────────────────────────────────────
    # NEC-5 GE card  (I1 field)
    #   0 = no image plane (free space)
    #   1 = activate image plane at z=0 (required for any ground-plane run,
    #       both perfect and real — handles near-field coupling via image theory)
    #
    # NEC-5 GN card  (IPERF / I1 field) — ground parameters
    #  -1 = nullify any previously entered ground, set free-space conditions
    #       (any F1..F4 values on the same card are ignored)
    #   0 = (not used as standalone — see GE card)
    #   1 = perfectly conducting ground (PEC)
    #       epsilon and sigma fields are present but ignored by NEC
    #   2 = real finitely conducting ground, Sommerfeld/Norton method
    #         F1 = relative permittivity epsilon_r (dimensionless)
    #              typical values: dry soil=3, average soil=13, wet soil=20, sea=80
    #         F2 = conductivity sigma (S/m)
    #              typical values: dry=0.001, average=0.005, wet=0.02, sea=4.0
    #
    # Correct GE + GN combinations:
    #   Free space  : GE  0              — no GN card needed
    #   Free space  : GN -1              — explicit free space (overrides prior GN)
    #   Perfect PEC : GE  1 + GN  1      — image plane + perfect conductor
    #   Real ground : GE  1 + GN  2 ...  — image plane + Sommerfeld parameters
    #
    # Note: using GE 0 with GN 2 is a common error — it suppresses the
    # image plane so near-field ground coupling is missed.
    gt = ground_type
    if 'perfect' in gt or gt == 'pec':
        ge_card  = 'GE  1'                           # activate image plane
        gn_cards = ['GN  1  0  0  0  0.  0.'   # IPERF=1: perfect PEC ground
                    '   ! GN IPERF I2 I3 I4 epsr sigma  (epsr/sigma ignored for PEC)']
    elif 'real' in gt:
        ge_card  = 'GE  1'                           # activate image plane
        gn_cards = [f'GN  2  0  0  0  {epsilon:.4f}  {sigma:.6f}'
                    f'   ! GN IPERF=2: real ground  epsr={epsilon:.4f}  sigma={sigma:.6f} S/m']
    else:                                             # free_space
        ge_card  = 'GE  0'                           # no image plane
        gn_cards = []                                 # no GN card for free space

    # ── RP card ───────────────────────────────────────────────────────────────
    # EZNEC does not support simultaneous az+el sweeps (full 3D sphere).
    # Generate an azimuth cut at theta=90° (horizon) — the most useful single
    # cut for checking Eh on a horizontal antenna above ground.
    # EZNEC can produce additional cuts interactively from its GUI after import.
    #
    # RP card column meanings:
    # RP  IOPT  NTHETA  NPHI  XNDA  THETA0  PHI0  DTHETA  DPHI
    #     |     |       |     |     |       |     |       |
    #     |     |       |     |     |       |     |       +-- PHI step size (deg)
    #     |     |       |     |     |       |     +---------- THETA step size (deg)
    #     |     |       |     |     |       +---------------- PHI start angle (deg)
    #     |     |       |     |     +------------------------ THETA start angle (deg)
    #     |     |       |     |       (90° = horizon; 0° = zenith/overhead)
    #     |     |       |     +------------------------------ XNDA output format:
    #     |     |       |       1000 = power gain (dBi), no normalisation
    #     |     |       |       0000 = normalised to max gain
    #     |     |       +------------------------------------ NPHI: number of PHI steps
    #     |     |         73 steps × 5° = 0° to 360° azimuth sweep
    #     |     +------------------------------------------- NTHETA: number of THETA steps
    #     |       1 = single elevation angle (azimuth cut)
    #     +------------------------------------------------- IOPT output type:
    #       0 = far-field (electric field + gain)
    #       1 = near-field
    #
    # This card produces: azimuth pattern at theta=90° (horizon), 0°→360°, 5° steps
    # To get elevation pattern instead: NTHETA=37, NPHI=1, THETA0=0, DTHETA=5, DPHI=0
    rp_card = ('RP  0    1  73  1000  90.  0.  0.  5.'
               '   ! azimuth cut: theta=90(horizon) phi=0-360 step=5deg power_gain')

    # ── EX card ──────────────────────────────────────────────────────────────
    v_rad  = math.radians(excit.get('phase_deg', 0.0))
    v_re   = excit.get('voltage', 1.0) * math.cos(v_rad)
    v_im   = excit.get('voltage', 1.0) * math.sin(v_rad)
    ex_card = (f'EX  0  {exc_nec_tag:3d}  {exc_seg:3d}  0'
               f'  {v_re:.6f}  {v_im:.6f}')

    # ── FR card ──────────────────────────────────────────────────────────────
    is_sweep = fmax_mhz > freq_mhz
    if is_sweep:
        if fstep_mhz > 0.0:
            fr_npts = int(round((fmax_mhz - freq_mhz) / fstep_mhz)) + 1
            fr_step = fstep_mhz
        else:
            fr_npts = max(nFreq, 2)
            fr_step = (fmax_mhz - freq_mhz) / (fr_npts - 1)
        fr_card = (f'FR  0  {fr_npts}  0  0  {freq_mhz:.6f}  {fr_step:.6f}'
                   f'   ! sweep {freq_mhz} to {fmax_mhz} MHz  {fr_npts} pts')
    else:
        fr_card = f'FR  0  1  0  0  {freq_mhz:.6f}'

    # ── summary stats for comments ────────────────────────────────────────────
    total_segs = sum(
        neomom_nsegs(
            math.dist(nodes[w['n1']], nodes[w['n2']]),
            seg_desired)
        for w in wires)

    # ── GN CM comment block ───────────────────────────────────────────────────
    gn_cm = [
        'CM',
        'CM GE card — image plane control:',
        'CM   GE 0 : no image plane (free space)',
        'CM   GE 1 : activate image plane at z=0 (required for any ground run)',
        'CM',
        'CM GN card — ground parameters (IPERF field):',
        'CM   GN -1 : nullify prior ground, set free space (all other fields ignored)',
        'CM   GN  1 : perfectly conducting PEC (epsilon/sigma fields ignored)',
        'CM   GN  2 : real ground, Sommerfeld/Norton',
        'CM            F1 = relative permittivity epsilon_r',
        'CM                 dry soil=3  average=13  wet=20  sea water=80',
        'CM            F2 = conductivity sigma [S/m]',
        'CM                 dry=0.001   average=0.005  wet=0.02  sea=4.0',
        'CM',
        'CM Correct GE+GN combinations:',
        'CM   Free space  : GE 0        (no GN card)',
        'CM   Perfect PEC : GE 1 + GN 1',
        'CM   Real ground : GE 1 + GN 2 epsilon_r sigma',
        'CM   Note: GE 0 + GN 2 is a common error — misses near-field ground coupling',
    ]

    # ── RP CM comment block ───────────────────────────────────────────────────
    rp_cm = [
        'CM',
        'CM RP card — radiation pattern request:',
        'CM   RP  IOPT  NTHETA  NPHI  XNDA  THETA0  PHI0  DTHETA  DPHI',
        'CM       |     |       |     |     |       |     |       |',
        'CM       |     |       |     |     |       |     |       +-- PHI increment (deg)',
        'CM       |     |       |     |     |       |     +---------- THETA increment (deg)',
        'CM       |     |       |     |     |       +---------------- PHI start (deg)',
        'CM       |     |       |     |     +------------------------ THETA start (deg)',
        'CM       |     |       |     |       0=zenith  90=horizon',
        'CM       |     |       |     +------------------------------ XNDA output format',
        'CM       |     |       |       1000=power gain dBi no norm  0000=normalised',
        'CM       |     |       +------------------------------------ NPHI: phi steps',
        'CM       |     +------------------------------------------- NTHETA: theta steps',
        'CM       +------------------------------------------------- IOPT: 0=far-field',
        'CM',
        'CM   This card: azimuth cut at theta=90 (horizon), phi=0 to 360, step=5 deg',
        'CM   Elevation cut instead: NTHETA=19 NPHI=1 THETA0=0 PHI0=0 DTHETA=5 DPHI=0',
    ]

    # ── assemble file ─────────────────────────────────────────────────────────
    out_lines = [
        f'CM {title}',
        f'CM Generated by nml_to_nec.py  from: {os.path.basename(nml_path)}',
        (f'CM Frequency : {freq_mhz} to {fmax_mhz} MHz'
         f'   lambda(fmax)={lambda_m:.5f} m  lambda(fmin)={lambda_fmin_m:.5f} m'
         if is_sweep else
         f'CM Frequency : {freq_mhz} MHz    lambda = {lambda_m:.5f} m'),
        f'CM Mesh      : {n_per_lambda} segs/lambda at fmax   seg_len = {seg_desired:.5f} m',
        f'CM Ground    : {ground_type}',
        f'CM Wires     : {len(wires)}    total segments = {total_segs}',
        (f'CM Excitation: {feed_tag} node {excit.get("nodeTag","")} '
         f'-> NEC wire {exc_nec_tag} seg {exc_seg}'),
        *gn_cm,
        *rp_cm,
        'CE',
        *gw_lines,
        ge_card,
        *gn_cards,
        ex_card,
        fr_card,
        rp_card,
        'EN',
    ]

    return '\n'.join(out_lines) + '\n'


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    nml_path = sys.argv[1]
    if not os.path.exists(nml_path):
        print(f'Error: file not found: {nml_path}', file=sys.stderr)
        sys.exit(1)

    nec_text = nml_to_nec(nml_path)
    out_path = os.path.splitext(nml_path)[0] + '.nec'

    with open(out_path, 'w') as fh:
        fh.write(nec_text)

    print(nec_text)
    print(f'─── Written to: {out_path} ───')


if __name__ == '__main__':
    main()