#!/usr/bin/env python3
"""
nml_to_maa.py  --  NeoMoM *.nml  ->  MMANA-GAL *.maa translator
=================================================================

Usage:
    python nml_to_maa.py  dipole.nml
    -> writes dipole.maa  (same directory)

The generated .maa file can be opened directly in MMANA-GAL:
    File > Open -> select the .maa file.

MMANA-GAL file structure generated
    Line 0          : title
    Line 1          : *
    Line 2          : frequency (MHz)
    ***Wires***     : wire geometry section
    <nwires>
    x1, y1, z1, x2, y2, z2, radius_m, -1     (comma+tab, segs=-1 = auto)
    ...
    *** Source ***  : excitation section
    <nsrc>, 1
    w<n>c, 0.0, 1.0                           (w<num>c = wire N at centre)
    *** Load ***    : loads section (empty)
    0, 1
    *** Segmentation ***
    400, <nBasisPerLambda>, 2.0, 1
    *** G/H/M/R/AzEl/X ***
    <gflag>, 0, 0, 50.0, 120, 60, 0.0

Supported NeoMoM features
    All length units (meters, cm, mm, feet, inches) -> converted to metres
    zHeight offset added to all node z-coordinates
    Free space, perfect ground (PEC), or real ground plane
    Single voltage excitation, any number of wires
"""

import re
import sys
import os
import math

# -- unit conversion table: input-unit -> metres --
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

SEP = ',\t'   # MMANA-GAL data separator: comma + tab


# ================================================================
# Namelist parser  (identical to nml_to_nec.py)
# ================================================================

def parse_nml(path):
    with open(path) as fh:
        text = fh.read()

    blocks = []
    for m in re.finditer(r'&(\w+)(.*?)/', text, re.DOTALL):
        bname = m.group(1).strip().lower()
        body  = m.group(2)
        kv    = {}

        for line in body.splitlines():
            line = line.strip().rstrip(',')
            if not line or line.startswith('!'):
                continue
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


# ================================================================
# Main translator
# ================================================================

def nml_to_maa(nml_path):
    blocks = parse_nml(nml_path)

    # -- defaults --
    title        = 'NeoMoM antenna'
    freq_mhz     = 14.0
    ground_type  = 'free_space'
    n_per_lambda = 20
    scale        = 1.0
    z_offset     = 0.0
    nodes        = {}       # uppercase tag -> (x_m, y_m, z_m)
    wires        = []
    excit        = {}

    # -- first pass: units and zHeight --
    for bname, kv in blocks:
        if bname == 'node_input':
            units_str = kv.get('units', 'meters').strip("'\"").lower()
            scale     = UNITS.get(units_str, 1.0)
            z_offset  = float(kv.get('zheight', '0.0')) * scale

    # -- second pass: everything else --
    for bname, kv in blocks:

        if bname == 'runtitle':
            title = kv.get('title', title).strip("'\"")

        elif bname == 'frequency_mhz':
            freq_mhz = float(kv.get('fmin', freq_mhz))
            # MMANA handles its own sweep internally — fmin used for display

        elif bname == 'ground':
            ground_type = kv.get('ground_plane', ground_type).strip("'\"").lower()

        elif bname == 'options':
            n_per_lambda = int(float(kv.get('nbasisperlambda', n_per_lambda)))

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

        elif bname == 'wire_primitive':
            tag    = kv.get('tag', '').strip("'\" ,").upper()
            ntstr  = kv.get('nodetags', '')
            # Strip quotes from each tag — write_nml writes 'A' 'B' 'C'
            ntags  = [t.strip("'\"").upper() for t in ntstr.split() if t.strip()]
            radius = float(kv.get('radius', '0.001')) * scale
            # Expand polyline into N-1 two-node segments
            # Wire (A,B,C,D,E) -> A->B, B->C, C->D, D->E
            if len(ntags) >= 2:
                n_segs = len(ntags) - 1
                for si in range(n_segs):
                    # Skip degenerate zero-length segments
                    if ntags[si] == ntags[si + 1]:
                        continue
                    seg_tag = tag if n_segs == 1 else f'{tag}_s{si+1}'
                    wires.append({
                        'tag'      : seg_tag,
                        'wire_tag' : tag,
                        'n1'       : ntags[si],
                        'n2'       : ntags[si + 1],
                        'radius'   : radius,
                    })

        elif bname == 'excitation_input':
            excit = {
                'wireTag'  : kv.get('wiretag',   '').strip("'\" ").upper(),
                'nodeTag'  : kv.get('nodetag',   '').strip("'\" ").upper(),
                'voltage'  : float(kv.get('voltage',   '1.0')),
                'phase_deg': float(kv.get('phase_deg', '0.0')),
            }

    # -- wire ordering: feed wire first, then alphabetical --
    feed_tag = excit.get('wireTag', '')
    wires.sort(key=lambda w: (0 if w.get('wire_tag', w['tag']) == feed_tag else 1, w['tag']))
    wire_index = {w['tag']: i + 1 for i, w in enumerate(wires)}

    # ================================================================
    # Build MMANA-GAL file text
    # ================================================================
    out = []

    # -- Header: title, *, frequency --
    out.append(title)
    out.append('*')
    out.append(f'{freq_mhz:.6f}')

    # -- Wire geometry section --
    out.append('***Wires***')
    out.append(str(len(wires)))

    for w in wires:
        n1 = nodes.get(w['n1'])
        n2 = nodes.get(w['n2'])
        if n1 is None or n2 is None:
            continue
        # segs = -1: let MMANA-GAL auto-calculate segment count
        out.append(
            f'{n1[0]:.6f}{SEP}{n1[1]:.6f}{SEP}{n1[2]:.6f}{SEP}'
            f'{n2[0]:.6f}{SEP}{n2[1]:.6f}{SEP}{n2[2]:.6f}{SEP}'
            f'{w["radius"]:.8f}{SEP}-1'
        )

    # -- Excitation (source) section --
    out.append('*** Source ***')
    n_excit = 1 if excit else 0
    out.append(f'{n_excit}{SEP}1')

    if excit:
        wire_num  = wire_index.get(excit['wireTag'], 1)
        feed_wire = next((w for w in wires if w.get('wire_tag', w['tag']) == excit['wireTag']), None)

        # Map NeoMoM node tag to MMANA position suffix:
        #   b = near start node (n1),  e = near end node (n2),  c = centre (default)
        if feed_wire:
            if excit['nodeTag'] == feed_wire['n1']:
                pos_char = 'b'
            elif excit['nodeTag'] == feed_wire['n2']:
                pos_char = 'e'
            else:
                pos_char = 'c'
        else:
            pos_char = 'c'

        # MMANA voltage source: magnitude only (imaginary handled by phase)
        v_mag = excit['voltage']
        out.append(f'w{wire_num}{pos_char}{SEP}0.0{SEP}{v_mag:.6f}')

    # -- Loads section (empty) --
    out.append('*** Load ***')
    out.append(f'0{SEP}1')

    # -- Segmentation section --
    out.append('*** Segmentation ***')
    out.append(f'400{SEP}{n_per_lambda}{SEP}2.0{SEP}1')

    # -- Ground / pattern parameters --
    out.append('*** G/H/M/R/AzEl/X ***')
    gt = ground_type.lower()
    if 'perfect' in gt or 'pec' in gt:
        gflag = 1
    elif 'real' in gt:
        gflag = 2
    else:                           # free_space
        gflag = 0
    # H=0 (zHeight already baked into wire coordinates), M=0 (default material)
    out.append(f'{gflag}{SEP}0{SEP}0{SEP}50.0{SEP}120{SEP}60{SEP}0.0')

    return '\n'.join(out) + '\n'


# ================================================================
# Entry point
# ================================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    nml_path = sys.argv[1]
    if not os.path.exists(nml_path):
        print(f'Error: file not found: {nml_path}', file=sys.stderr)
        sys.exit(1)

    maa_text = nml_to_maa(nml_path)
    out_path = os.path.splitext(nml_path)[0] + '.maa'

    with open(out_path, 'w', encoding='ascii', errors='replace') as fh:
        fh.write(maa_text)

    print(f'Written: {out_path}')


if __name__ == '__main__':
    main()