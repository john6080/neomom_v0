# run_sweep.py
#
# Two-pass driver for the Burke Fig 2.1.6 s/d sweep, parallelized across
# s/d values -- each s/d point is a fully independent engine run (its own
# .nml/.csv files, no shared state), and the engine's solver is pure
# Fortran LU (USE_MKL=.FALSE. in matrix_module.f90, no internal
# threading), so running several full engine instances side-by-side is
# safe and doesn't risk oversubscribing cores the way parallel MKL calls
# would.
#
# Per s/d point:
#   Pass 1: WIDE coarse sweep to locate the true Bin(f) zero-crossing
#           (antiresonance) nearest the nominal f0 = c/1.0m -- needed
#           because a real (non-ideal-thin-wire) antiresonance doesn't
#           sit at exactly f0; end effects shift it, and the shift grows
#           with s/d.
#   Pass 2: NARROW high-resolution window centered on that crossing for
#           the precise dBin/df slope, giving Z0 = 2*pi*l/c / (dBin/df).
#
# Geometry: true two-wire, two-port topology (see gen_burke_case.py) --
# two independent 10m wires, +1V/-1V driven at their centers, no
# physical connecting stub. This replaced an earlier stub-based
# approximation once it was confirmed the stub's electrical length
# became non-negligible at large s/d and biased the result.

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'neomom_Zin', 'src'))
from Zin_reader import read_Zin_file
import gen_burke_case as gbc
from extract_Z0 import extract_Z0, ideal_Z0

ENGINE = r"E:\Ant_neomom_to_git\neomom_v0\engine\windows\x64\Release\neomom.exe"
NBPL = 80
MAX_WORKERS = 8   # concurrent engine instances (24 logical cores available;
                   # engine solver is single-threaded pure-Fortran LU, no MKL)

SD_VALUES = [1.1, 1.3, 1.6, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0, 50.0, 70.0, 100.0]

COARSE_HALF_WIDTH_INIT = 5.0    # MHz around f0 to start the search
COARSE_HALF_WIDTH_MAX = 40.0    # MHz -- widen up to this before giving up
COARSE_FSTEP = 0.25             # MHz
NARROW_HALF_WIDTH = 0.5         # MHz around the located antiresonance
NARROW_FSTEP = 0.1              # MHz


def run_engine(nml_path):
    # plot=false suppresses the neomom_Zin GUI auto-launch after each run.
    subprocess.run([ENGINE, os.path.basename(nml_path), 'plot=false'],
                    cwd=os.path.dirname(nml_path) or '.',
                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)


def find_all_zero_crossings(freq_mhz, bin_vals):
    """All sign-change locations of Bin(f), linearly interpolated."""
    crossings = []
    for i in range(len(bin_vals) - 1):
        y0, y1 = bin_vals[i], bin_vals[i + 1]
        if y0 == 0.0:
            crossings.append(freq_mhz[i])
        elif y0 * y1 < 0.0:
            t = -y0 / (y1 - y0)
            crossings.append(freq_mhz[i] + t * (freq_mhz[i + 1] - freq_mhz[i]))
    return crossings


def find_nearest_crossing(freq_mhz, bin_vals, target_mhz):
    """Zero crossing of Bin(f) nearest to target_mhz, or None if none exist."""
    crossings = find_all_zero_crossings(freq_mhz, bin_vals)
    if not crossings:
        return None
    return min(crossings, key=lambda f: abs(f - target_mhz))


def process_sd(sd, outdir):
    """Full two-pass workflow for one s/d value. Runs entirely on its own
    uniquely-named files -- safe to call concurrently for different sd."""
    log = [f'=== s/d = {sd:g} ===']

    f_res = None
    half_width = COARSE_HALF_WIDTH_INIT
    while half_width <= COARSE_HALF_WIDTH_MAX:
        coarse_path, _ = gbc.gen_nml(
            sd, nbasisperlambda=NBPL, outdir=outdir,
            fmin=gbc.F0_MHZ - half_width,
            fmax=gbc.F0_MHZ + half_width,
            fstep=COARSE_FSTEP, suffix='_coarse')
        run_engine(coarse_path)
        coarse_csv = coarse_path.replace('.nml', '_Zin.csv')
        meta, data = read_Zin_file(coarse_csv)
        f_res = find_nearest_crossing(data['freq_mhz'], data['Bin'], gbc.F0_MHZ)
        if f_res is not None:
            break
        log.append(f'  no crossing in +/-{half_width:g} MHz, widening...')
        half_width *= 2.0

    if f_res is None:
        log.append(f'  WARNING: no antiresonance found up to +/-{COARSE_HALF_WIDTH_MAX} MHz -- skipping')
        print('\n'.join(log))
        return (sd, None, ideal_Z0(sd), None)

    log.append(f'  coarse antiresonance: f_res = {f_res:.4f} MHz (nominal f0 = {gbc.F0_MHZ:.4f} MHz)')

    narrow_path, _ = gbc.gen_nml(
        sd, nbasisperlambda=NBPL, outdir=outdir,
        fmin=f_res - NARROW_HALF_WIDTH,
        fmax=f_res + NARROW_HALF_WIDTH,
        fstep=NARROW_FSTEP, suffix='_narrow')
    run_engine(narrow_path)
    narrow_csv = narrow_path.replace('.nml', '_Zin.csv')

    Z0_neomom, slope = extract_Z0(narrow_csv)
    Z0_ideal = ideal_Z0(sd)
    delta_pct = 100.0 * (Z0_neomom - Z0_ideal) / Z0_ideal
    log.append(f'  Z0 (NeoMoM) = {Z0_neomom:.4f} Ohm   Z0 (ideal) = {Z0_ideal:.4f} Ohm   '
               f'delta = {delta_pct:+.2f}%')
    print('\n'.join(log))

    return (sd, Z0_neomom, Z0_ideal, f_res)


def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_sd, sd, outdir): sd for sd in SD_VALUES}
        for fut in as_completed(futures):
            sd = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f'=== s/d = {sd:g} === FAILED: {e}')
                results.append((sd, None, ideal_Z0(sd), None))

    results.sort(key=lambda r: r[0])

    results_path = os.path.join(outdir, 'results.csv')
    with open(results_path, 'w') as f:
        f.write('s_over_d,Z0_neomom_ohm,Z0_ideal_ohm,f_res_mhz\n')
        for sd, z0n, z0i, fres in results:
            z0n_s = f'{z0n:.4f}' if z0n is not None else ''
            fres_s = f'{fres:.4f}' if fres is not None else ''
            f.write(f'{sd:g},{z0n_s},{z0i:.4f},{fres_s}\n')

    print(f'\nDone. Results written to {results_path}')
    print(f'\n{"s/d":>8s} {"Z0_neomom":>12s} {"Z0_ideal":>12s} {"delta%":>8s} {"f_res_MHz":>10s}')
    for sd, z0n, z0i, fres in results:
        if z0n is None:
            print(f'{sd:8g} {"FAILED":>12s} {z0i:12.4f} {"":>8s} {"":>10s}')
        else:
            delta_pct = 100.0 * (z0n - z0i) / z0i
            print(f'{sd:8g} {z0n:12.4f} {z0i:12.4f} {delta_pct:7.2f}% {fres:10.4f}')


if __name__ == '__main__':
    main()
