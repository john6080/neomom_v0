# gen_burke_case.py
#
# Purpose: Generate a NeoMoM .nml for one point of Burke's NEC-5
#          Validation Manual Fig. 2.1.6 two-wire transmission-line Z0
#          test (Sec. 2.1, "A test for modeling closely spaced wires").
#
# Burke's setup, reproduced directly (no approximation): two parallel
# wires, length 10 m, radius 0.001 m, driven with +1V and -1V AT THEIR
# CENTERS -- two independent ports, no physical connecting wire between
# them. By antisymmetry this is electrically equivalent to cutting the
# structure in half with a PEC plane, giving a single open-circuited
# line of length l=5m with a net 1V source -- Burke uses that
# equivalence explicitly to derive Yin = (j/Z0)*tan(2*pi*f*l/c).
#
# First attempt at this used the SAME topology as ../parallel_tl_open.nml
# (two 5m open wires joined by a short physical stub at the near end,
# fed at the stub's midpoint) as an approximation of the PEC-plane cut.
# That's fine when the stub is negligible relative to L (true for the
# original 50m/2cm case), but here the stub length IS s -- as s/d grows
# from 1.1 to 100, s grows from 2.2mm to 200mm, and at L=5m that stub
# stopped being negligible: it added real electrical path length,
# measurably shifting the antiresonant frequency away from the assumed
# f0 (confirmed empirically -- shifted by several MHz at s/d=50-100,
# and introduced a growing systematic bias in the extracted Z0 that
# Burke's own Fig 2.1.6 doesn't show).
#
# NeoMoM's engine supports this directly: apply_excitations() sums ALL
# &excitation_input sources into one RHS and solves once, then EACH
# excitation reports its own Zin = zVolts/I_hub independently
# (excitation_m.f90); the swept/CSV-reported Zin is excitations(1)%Zin
# (MAIN_NEO_WIRE_MOM.f90) -- so putting the +1V port first and driving
# the -1V port simultaneously reproduces Burke's true setup with no
# stub and no electrical-length approximation at all.
#
# Usage:
#   python3 gen_burke_case.py <s_over_d> [nbasisperlambda]

import sys
import os

C_LIGHT = 299792458.0

HALF_L = 5.0      # each wire's half-length [m] -- full wire is 2*HALF_L = 10m
A_RAD = 0.001     # wire radius [m]
D = 2.0 * A_RAD   # wire diameter [m]
F0_MHZ = C_LIGHT / 1.0e6   # f where lambda = 1.0m exactly -> half-length = 5*lambda
DF_HALF_MHZ = 0.5          # sweep window half-width around f0
FSTEP_MHZ = 0.1            # -> 11 points across the window


def gen_nml(s_over_d, nbasisperlambda=80, outdir='.', fmin=None, fmax=None,
            fstep=FSTEP_MHZ, suffix=''):
    s = s_over_d * D
    if fmin is None:
        fmin = F0_MHZ - DF_HALF_MHZ
    if fmax is None:
        fmax = F0_MHZ + DF_HALF_MHZ

    title = f'Burke Fig 2.1.6 TL, s/d={s_over_d:g}, l={HALF_L}m, a={A_RAD}m'
    fname = f'burke_sd_{s_over_d:g}{suffix}.nml'
    path = os.path.join(outdir, fname)

    # W1: (-5,0,0) -> (0,0,0) -> (5,0,0), fed +1V at center (M1)
    # W2: (-5,s,0) -> (0,s,0) -> (5,s,0), fed 1V @ 180deg (= -1V) at center (M2)
    # No connection between W1 and W2 at all.
    nml = f"""&RunTitle title = '{title}' /

&Frequency_MHz fmin = {fmin:.6f} fmax = {fmax:.6f} fstep = {fstep} nFreq = 0 /

&Ground Ground_Plane = 'free_space' epsilon = 1.0 sigma = 0.0 /

&OPTIONS NBASISPERLAMBDA = {nbasisperlambda} Output_Currents = .FALSE. sweep_mode = 'vna_sweep' /

&node_input zHeight = 0.0 nNodes = 6 units = 'meters'
 node_list(1) = 'A1', -{HALF_L:.6f}, 0.000000, 0.000000
 node_list(2) = 'M1',  0.000000, 0.000000, 0.000000
 node_list(3) = 'B1',  {HALF_L:.6f}, 0.000000, 0.000000
 node_list(4) = 'A2', -{HALF_L:.6f}, {s:.8f}, 0.000000
 node_list(5) = 'M2',  0.000000, {s:.8f}, 0.000000
 node_list(6) = 'B2',  {HALF_L:.6f}, {s:.8f}, 0.000000
/

&wire_primitive tag = 'W1' nNodes = 3 nodeTags = 'A1' 'M1' 'B1'     radius = {A_RAD} /

&wire_primitive tag = 'W2' nNodes = 3 nodeTags = 'A2' 'M2' 'B2'     radius = {A_RAD} /

&excitation_input wireTag = 'W1' nodeTag = 'M1' voltage = 1.0 phase_deg = 0.0 /

&excitation_input wireTag = 'W2' nodeTag = 'M2' voltage = 1.0 phase_deg = 180.0 /
"""
    with open(path, 'w') as f:
        f.write(nml)
    return path, s


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 gen_burke_case.py <s_over_d> [nbasisperlambda]')
        sys.exit(1)
    s_over_d = float(sys.argv[1])
    nbpl = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    path, s = gen_nml(s_over_d, nbpl)
    print(f's/d={s_over_d:g}  s={s*1000:.4f} mm  d={D*1000:.4f} mm  -> {path}')


if __name__ == '__main__':
    main()
