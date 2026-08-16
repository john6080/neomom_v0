# gen_tl_theory_csv.py
#
# Purpose: Generate a closed-form transmission-line theory reference
#          CSV, in the same format neomom_Zin reads (_Zin.csv), for
#          the parallel_tl_open.nml validation case -- so it can be
#          overlaid against the NeoMoM MoM run and a NEC5 run in
#          neomom_Zin for validation.
#
# Model: lossless, open-circuited two-wire transmission line.
#   Zin(f) = -j * Z0 * cot(beta * L)      -- standard textbook sign
#   Z0 = (eta0/pi) * acosh(D / (2a))      -- exact twin-lead Z0, round wires
#   beta = 2*pi*f / (vf * c)              -- vf = 1.0 (bare wire, free space)
#
# Sign history: an earlier version of this file negated X to match what
# turned out to be a real bug in NeoMoM's Z-fill near-field pair
# classification (purely topological NEAR/FAR split, no geometric-
# distance check -- misclassified the closely-spaced antiparallel runs
# of this TL as FAR pairs, using only 4-point quadrature). NEC5,
# independently, agreed with the standard (unflipped) sign here, which
# is what exposed the NeoMoM bug rather than a feed-convention
# difference. NeoMoM has since been fixed (mesh_m.f90: C1_lenMult=1.5 +
# NBASISPERLAMBDA=160) and now matches this standard sign directly --
# no flip needed. Rin is identically 0 in this model -- ideal TL theory
# is lossless and does not include radiation. Any nonzero Rin in the
# NeoMoM/NEC5 runs is real physics (radiation resistance) that this
# reference deliberately excludes, so it can be seen as the delta
# between theory and full-wave.
#
# Usage:
#   python3 gen_tl_theory_csv.py <reference_Zin.csv> <output_Zin.csv>
#
# <reference_Zin.csv> supplies the frequency grid (so the theory curve
# lines up point-for-point with an existing NeoMoM run for overlay).

import sys
import numpy as np
from Zin_reader import read_Zin_file, compute_swr

# ------------------------------------------------------------------
# Geometry -- parallel_tl_open.nml
# ------------------------------------------------------------------
L  = 50.0        # line length [m]
D  = 0.02         # wire center-to-center spacing [m]  (s = 2 cm)
A  = 0.001        # wire radius [m]
VF = 1.0          # velocity factor -- bare two-wire line in free space
Z0_REF = 50.0     # SWR reference impedance [Ohm], matches the .nml sweep


def compute_theory(freq_mhz):
    c = 299792458.0
    mu0 = 4.0 * np.pi * 1e-7
    eta0 = mu0 * c

    # Exact twin-lead characteristic impedance, round conductors,
    # valid at any D/a ratio (not just D >> a).
    Z0 = (eta0 / np.pi) * np.arccosh(D / (2.0 * A))

    f_hz = freq_mhz * 1.0e6
    beta = 2.0 * np.pi * f_hz / (VF * c)

    # Standard textbook open-stub sign: Xin = -Z0*cot(beta*L). Matches
    # NEC5 and the (now-fixed) NeoMoM engine directly -- no sign flip.
    with np.errstate(divide='ignore', invalid='ignore'):
        Xin = -Z0 / np.tan(beta * L)
    Rin = np.zeros_like(Xin)

    Zin_cpx = Rin + 1j * Xin
    Zin_mag = np.abs(Zin_cpx)

    with np.errstate(divide='ignore', invalid='ignore'):
        Yin_cpx = np.where(Zin_mag > 0, 1.0 / Zin_cpx, np.inf + 0j)
    Gin = np.real(Yin_cpx)
    Bin = np.imag(Yin_cpx)
    Yin_mag = np.abs(Yin_cpx)

    SWR = compute_swr(Rin, Xin, Z0=Z0_REF)

    return Z0, dict(Rin=Rin, Xin=Xin, Zin_mag=Zin_mag,
                     Gin=Gin, Bin=Bin, Yin_mag=Yin_mag, SWR=SWR)


def write_csv(path, freq_mhz, d, Z0_TL):
    fstep = float(freq_mhz[1] - freq_mhz[0]) if len(freq_mhz) > 1 else 0.0
    with open(path, 'w') as f:
        f.write('# NeoMOM Impedance Sweep -- THEORY REFERENCE (not MoM output)\n')
        f.write('# title       : TL, Open, 50m long, s = 2 cm, a = 0.001 -- closed-form theory\n')
        f.write('# model       : lossless open-circuited twin-lead, Zin = -j*Z0*cot(beta*L)\n')
        f.write('#               (standard textbook sign; matches NEC5 and the fixed NeoMoM\n')
        f.write('#               engine directly -- see gen_tl_theory_csv.py header for history)\n')
        f.write(f'# Z0_line_Ohm : {Z0_TL:.4f}   (twin-lead, D={D} m, a={A} m)\n')
        f.write('# velocity_factor : 1.0 (bare two-wire line, free space)\n')
        f.write('# note        : Rin = 0 identically -- ideal TL theory excludes radiation;\n')
        f.write('#               nonzero Rin in MoM/NEC5 runs is real radiation resistance.\n')
        f.write('# ground      : N/A (circuit-theory model)\n')
        f.write('# nports      : 1\n')
        f.write(f'# nfreq       : {len(freq_mhz)}\n')
        f.write(f'# fstart_MHz  : {freq_mhz[0]:.4f}\n')
        f.write(f'# fstop_MHz   : {freq_mhz[-1]:.4f}\n')
        f.write(f'# fstep_MHz   : {fstep:.4f}\n')
        f.write(f'# z0_ref_Ohm  : {Z0_REF}\n')
        f.write('#\n')
        f.write('# freq_MHz    Rin_Ohm    Xin_Ohm    Zin_Ohm    Gin_S      Bin_S      Yin_S      SWR\n')
        for i in range(len(freq_mhz)):
            row = [freq_mhz[i], d['Rin'][i], d['Xin'][i], d['Zin_mag'][i],
                   d['Gin'][i], d['Bin'][i], d['Yin_mag'][i], d['SWR'][i]]
            f.write('   ' + '   '.join(f'{v:.6E}' for v in row) + '\n')


def main():
    if len(sys.argv) != 3:
        print('Usage: python3 gen_tl_theory_csv.py <reference_Zin.csv> <output_Zin.csv>')
        sys.exit(1)

    ref_path, out_path = sys.argv[1], sys.argv[2]
    _, ref_data = read_Zin_file(ref_path)
    freq_mhz = ref_data['freq_mhz']

    Z0_TL, d = compute_theory(freq_mhz)
    write_csv(out_path, freq_mhz, d, Z0_TL)

    print(f'Z0 (twin-lead) = {Z0_TL:.4f} Ohm')
    print(f'Wrote {len(freq_mhz)} points -> {out_path}')


if __name__ == '__main__':
    main()
