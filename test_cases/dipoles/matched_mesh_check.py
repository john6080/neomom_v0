# matched_mesh_check.py
#
# For a handful of single frequencies, generate a matched pair of inputs --
# a NeoMoM .nml and a NEC5 .nec meshed AT THAT SAME FREQUENCY (not at a
# swept fmax like the vna_sweep .nec did) -- run both engines, and compare
# Zin directly. This isolates whether the divergence seen in specific bands
# of the 5-30 MHz sweep (12.5-17.5, 20-23, 27.5-30 MHz) is a real Zfill
# accuracy gap or an artifact of NEC5's sweep using one mesh (sized for
# fmax=30MHz) across the whole 5-30MHz range while NeoMoM remeshes at
# every point.
#
# Usage: python matched_mesh_check.py

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'neomom_input', 'src'))
import nml_to_nec as ntn

ENGINE = r"E:\Ant_neomom_to_git\neomom_v0\engine\windows\x64\Release\neomom.exe"
NEC5   = "nec5"

TEST_FREQS_MHZ = [17.5, 27.5]   # off-peak replacements for the 14.8/29.7 antiresonance-adjacent points

NML_TEMPLATE = """&RunTitle title = '40m center fed' /

&Frequency_MHz fmin = {f} fmax = {f} nFreq = 1 /

&Ground Ground_Plane = 'free_space' epsilon = 1.0 sigma = 0.0 /

&OPTIONS NBASISPERLAMBDA = 40 Output_Currents = .TRUE. /

&node_input zHeight = 0.0 nNodes = 3 units = 'feet'
 node_list(1) = 'A',  0.000000, 0.000000, 0.000000
 node_list(2) = 'B', 65.000000, 0.000000, 0.000000
 node_list(3) = 'C', 32.500000, 0.000000, 0.000000
/

&wire_primitive tag = 'W1' nNodes = 3 nodeTags = 'A' 'C' 'B' radius = 0.001 /

&excitation_input wireTag = 'W1' nodeTag = 'C' voltage = 1.0 phase_deg = 0.0 /
"""


def run_neomom(nml_path):
    subprocess.run([ENGINE, os.path.basename(nml_path), 'plot=false'],
                    cwd=os.path.dirname(nml_path), stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT, check=True)


def parse_neomom_zin(csv_path):
    with open(csv_path) as f:
        text = f.read()
    m = re.search(r'input impedance\s*:\s*\(([-\d.]+),([-\d.]+)\)', text)
    return complex(float(m.group(1)), float(m.group(2)))


def run_nec5(nec_path, out_path):
    subprocess.run([NEC5, os.path.basename(nec_path), os.path.basename(out_path)],
                    cwd=os.path.dirname(nec_path), check=True)


def parse_nec5_zin(out_path):
    with open(out_path) as f:
        text = f.read()
    m = re.search(r'\d+\s+\d+\s+\d+\s+([-\d.E+]+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s+'
                  r'([-\d.E+]+)\s+([-\d.E+]+)', text[text.index('ANTENNA INPUT PARAMETERS'):])
    v_re, v_im, i_re, i_im, z_re, z_im = map(float, m.groups())
    return complex(z_re, z_im)


def main():
    results = []
    for f in TEST_FREQS_MHZ:
        tag = f'matched_f{f:g}'.replace('.', 'p')
        nml_path = os.path.join(HERE, tag + '.nml')
        with open(nml_path, 'w') as fh:
            fh.write(NML_TEMPLATE.format(f=f))

        print(f'=== f = {f} MHz ===')
        run_neomom(nml_path)
        csv_path = nml_path.replace('.nml', '.csv')
        neo_Zin = parse_neomom_zin(csv_path)

        nec_text = ntn.nml_to_nec(nml_path)
        nec_path = nml_path.replace('.nml', '.nec')
        with open(nec_path, 'w') as fh:
            fh.write(nec_text)
        out_path = nml_path.replace('.nml', '.nec.out')
        run_nec5(nec_path, out_path)
        nec_Zin = parse_nec5_zin(out_path)

        dR = neo_Zin.real - nec_Zin.real
        dX = neo_Zin.imag - nec_Zin.imag
        print(f'  NeoMoM Zin = {neo_Zin.real:.4f} {neo_Zin.imag:+.4f}j   '
              f'NEC5 Zin = {nec_Zin.real:.4f} {nec_Zin.imag:+.4f}j   '
              f'dR={dR:+.4f} dX={dX:+.4f}')
        results.append((f, neo_Zin, nec_Zin, dR, dX))

    print(f"\n{'f_MHz':>7} {'NeoMoM_R':>10} {'NeoMoM_X':>10} {'NEC5_R':>10} {'NEC5_X':>10} {'dR':>8} {'dX':>8}")
    for f, neo_Zin, nec_Zin, dR, dX in results:
        print(f'{f:7.2f} {neo_Zin.real:10.4f} {neo_Zin.imag:10.4f} '
              f'{nec_Zin.real:10.4f} {nec_Zin.imag:10.4f} {dR:8.4f} {dX:8.4f}')


if __name__ == '__main__':
    main()
