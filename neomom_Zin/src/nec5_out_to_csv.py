# nec5_out_to_csv.py
#
# Purpose: Parse a NEC5.exe console-output (.out) file's per-frequency
#          "ANTENNA INPUT PARAMETERS" blocks into the same _Zin.csv
#          format neomom_Zin reads, for direct overlay against a
#          NeoMoM run and/or closed-form theory.
#
# Usage:
#   python3 nec5_out_to_csv.py <nec5_run.out> <output_Zin.csv>

import re
import sys
import numpy as np

sys.path.insert(0, '.')
from Zin_reader import compute_swr

FREQ_RE = re.compile(r'FREQUENCY=\s*([\d.Ee+-]+)\s*MHZ')
# Antenna input parameters data row: TAG SEG.NO [[extra index]] then 9 floats
# (VOLTAGE re/im, CURRENT re/im, IMPEDANCE re/im, ADMITTANCE re/im, POWER)
NUM_RE = re.compile(r'[-+]?\d+\.\d+[Ee][-+]?\d+')


def parse_nec5_out(path, Z0_ref=50.0):
    with open(path, 'r', errors='ignore') as f:
        lines = f.readlines()

    freqs, Rin, Xin = [], [], []
    current_freq = None

    for i, line in enumerate(lines):
        m = FREQ_RE.search(line)
        if m:
            current_freq = float(m.group(1))
            continue

        if 'ANTENNA INPUT PARAMETERS' in line:
            # Data row(s) follow after two header lines
            j = i + 3
            while j < len(lines) and lines[j].strip():
                nums = NUM_RE.findall(lines[j])
                if len(nums) >= 9 and current_freq is not None:
                    vals = [float(x) for x in nums[-9:]]
                    # order: V_re,V_im, I_re,I_im, Z_re,Z_im, Y_re,Y_im, P
                    freqs.append(current_freq)
                    Rin.append(vals[4])
                    Xin.append(vals[5])
                j += 1
            current_freq = None  # consumed

    freqs = np.array(freqs)
    Rin = np.array(Rin)
    Xin = np.array(Xin)

    Zin_cpx = Rin + 1j * Xin
    Zin_mag = np.abs(Zin_cpx)
    with np.errstate(divide='ignore', invalid='ignore'):
        Yin_cpx = np.where(Zin_mag > 0, 1.0 / Zin_cpx, np.inf + 0j)
    Gin = np.real(Yin_cpx)
    Bin = np.imag(Yin_cpx)
    Yin_mag = np.abs(Yin_cpx)
    SWR = compute_swr(Rin, Xin, Z0=Z0_ref)

    return freqs, dict(Rin=Rin, Xin=Xin, Zin_mag=Zin_mag,
                        Gin=Gin, Bin=Bin, Yin_mag=Yin_mag, SWR=SWR)


def write_csv(path, freq_mhz, d, title, Z0_ref=50.0):
    fstep = float(freq_mhz[1] - freq_mhz[0]) if len(freq_mhz) > 1 else 0.0
    with open(path, 'w') as f:
        f.write('# NeoMOM Impedance Sweep -- NEC5 REFERENCE (not MoM output)\n')
        f.write(f'# title       : {title}\n')
        f.write('# source      : NEC5.exe console engine, parsed from .out\n')
        f.write('# ground      : free_space (see NEC5 GN=2/sigma=0 Sommerfeld note)\n')
        f.write('# nports      : 1\n')
        f.write(f'# nfreq       : {len(freq_mhz)}\n')
        f.write(f'# fstart_MHz  : {freq_mhz[0]:.4f}\n')
        f.write(f'# fstop_MHz   : {freq_mhz[-1]:.4f}\n')
        f.write(f'# fstep_MHz   : {fstep:.4f}\n')
        f.write(f'# z0_ref_Ohm  : {Z0_ref}\n')
        f.write('#\n')
        f.write('# freq_MHz    Rin_Ohm    Xin_Ohm    Zin_Ohm    Gin_S      Bin_S      Yin_S      SWR\n')
        for i in range(len(freq_mhz)):
            row = [freq_mhz[i], d['Rin'][i], d['Xin'][i], d['Zin_mag'][i],
                   d['Gin'][i], d['Bin'][i], d['Yin_mag'][i], d['SWR'][i]]
            f.write('   ' + '   '.join(f'{v:.6E}' for v in row) + '\n')


def main():
    if len(sys.argv) != 3:
        print('Usage: python3 nec5_out_to_csv.py <nec5_run.out> <output_Zin.csv>')
        sys.exit(1)

    out_path, csv_path = sys.argv[1], sys.argv[2]
    freqs, d = parse_nec5_out(out_path)
    write_csv(csv_path, freqs, d, title=f'NEC5 run: {out_path}')
    print(f'Parsed {len(freqs)} frequency points -> {csv_path}')


if __name__ == '__main__':
    main()
