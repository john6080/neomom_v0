# NeoMoM Changelog

All notable changes to the NeoMoM project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Version numbering follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-07-27

### Initial public release

**NeoMoM Computational Engine (Fortran)**
- Wire Method of Moments solver using RWG rooftop basis functions
- Adaptive meshing: segments per wire recomputed at every frequency
  to maintain user-specified segments per wavelength (default 40/λ)
- Real ground via Fresnel reflection coefficients
- PEC ground via image theory
- Free-space operation
- Frequency sweep: pattern sweep and VNA sweep modes
- Command-line run control flags: `plot=`, `currents=`, `sweep=`
- Output: frequency-tagged CSV pattern files, text summary, current
  distribution files, and single-file Zin CSV for VNA sweeps
- NEC-5 card deck export (`nml_to_nec.py`) with mesh at fmax
- MMANA-GAL export (`nml_to_maa.py`)

**neomom_input (Python GUI)**
- Graphical antenna geometry creation: nodes, wires, excitations
- Live 3D geometry preview
- Pattern sweep and VNA sweep mode selection with live point count
- Ground type selection: free space, PEC, real
- Export to NEC-5 card deck and MMANA-GAL formats
- NEC deck includes full CM comment documentation of all cards

**neomom_plot (Python GUI)**
- 2D polar patterns: elevation and azimuth cuts
- Cartesian pattern plots
- 3D radiation pattern surface
- Pattern heatmap
- Geographic map overlay with cartopy (world, CONUS, regional)
- NEC5 pattern overlay for comparison

**neomom_Zin (Python GUI)**
- Impedance (R, X) vs frequency
- Admittance (G, B) vs frequency with resonance detection
- SWR vs frequency with user-selectable Z0 reference
- Multi-dataset overlay: NeoMoM and EZNEC/NEC5 results on same plot
- Ham band overlays (all ITU Region 2 bands, 160m–23cm)
- Auto-detects NeoMoM _Zin.csv and EZNEC .txt sweep file formats

**neomom_current (Python GUI)**
- 3D current magnitude visualization
- 3D current phase visualization
- 2D current vs position plots

**Platform support**
- Linux (primary development platform)
- Windows (tested on Windows 10/11 with 4K display)
- macOS: planned

---

## [Unreleased]

### Engine near-field quadrature: history and rationale

The original engine (`zfill_m`) used RTWK/Gibson closed-form math for
self terms and a single, fixed-order Gauss quadrature for every other
pair, with no distinction between near and far segment pairs at all.
That's accurate for ordinary, well-separated wire geometries (dipoles,
Yagis, verticals, loops), but under-resolves the rapidly-varying kernel
between two segments that pass close to each other without touching —
e.g. a closely-spaced parallel-wire transmission line. This was a latent
weakness of the original approach, not something introduced later; it
just hadn't been exercised by a test case that stressed it until now.

Steps taken to address it, each superseding the last:

1. **`zfill_nec_m` module added** (NEC-5-style Galerkin fill, selectable
   RTWK/ETWK/EXACT self-term and near-pair kernels, RTWK/Gibson by
   default). Reproduces the original engine's results essentially
   exactly for ordinary geometries — confirmed directly, identical
   impedance to 4 decimal places on a plain dipole — but introduced its
   own binary near/far split (4-point vs. 16-point quadrature) based
   purely on whether two segments *shared a node*. For closely-spaced,
   non-touching pairs this misclassified them as "far" and integrated
   the near-field kernel with only 4 points.
2. **First fix: centroid-distance thresholds** (`C1_lenMult`/
   `C2_lambda`, since removed). Elevated a pair to "near" treatment when
   segment centroids were close, in absolute or wavelength-relative
   terms. Improved accuracy near the top of a frequency sweep, but still
   degraded badly at the low end: centroid distance is a poor proxy for
   true proximity on a *long* antiparallel run (facing segments' true
   gap can be tiny while their centroids sit a full segment-length
   apart), and the wavelength-relative term compounded with — rather
   than compensated for — the mesh's own wavelength-relative coarsening
   at low frequency.
3. **`select_nQ`** (current). Uses the true minimum distance between the
   two segments as finite 3-D line segments (not centroids, not
   infinite lines), and a four-rung graduated ladder (4/16/64/128-point
   quadrature) instead of a binary split, chosen by how large the
   segment length is relative to that true gap. Purely geometric — no
   wavelength dependence — which was the actual fix: a fixed physical
   gap needs the same resolution regardless of frequency.

Net effect: no change for ordinary antennas (still matches the original
engine exactly). For closely-spaced parallel-wire geometries, median
reactance error on a 50m/2cm-gap open transmission line at the
low-frequency end of a sweep dropped from ~31 Ω (centroid-fix era) to
~0.2 Ω (`select_nQ`), with no manual tuning required. ETWK/EXACT self-
and near-pair kernels remain available as selectable alternatives but
are not the default; re-tested and re-confirmed as *not* an improvement
for ordinary geometries (swapping to EXACT self-term made agreement with
NEC-5 worse, not better, on a well-conditioned dipole) — RTWK/Gibson,
the original choice, remains correct and stays the default.

A separate, unrelated robustness bug was found and fixed during this
work: see "NaN input impedance" under Fixed below.

### Added
- `select_nQ` in the engine's NEC-style Z-fill (`zfill_nec_m_15.f90`): a
  graduated Gauss-Legendre quadrature ladder (4/16/64/128-point) chosen
  from the true minimum axis-to-axis distance between segment pairs, not
  centroid distance. Replaces the old centroid-based `classify_near`
  (`C1_lenMult`/`C2_lambda`), which under-resolved long, closely-spaced
  antiparallel runs (e.g. a two-wire transmission line) and required
  manual per-case threshold tuning. See "Engine near-field quadrature:
  history and rationale" above for the full story.
- Active geometry warning in neomom_input's Validate menu for conductors
  closer than ~2x wire diameter (e.g. folded dipoles, hairpin matches,
  closely-run ladder line) — thin-wire MoM isn't reliable there for
  either NeoMoM or NEC5, per Burke's NEC-5 validation manual.
- Per-tab Y-axis range controls in neomom_Zin (R/X, G/B, and SWR plots).
- `nec5_out_to_csv.py`: parses NEC5 console `.out` sweep output into the
  same `_Zin.csv` format NeoMoM produces, for direct overlay/comparison
  in neomom_Zin.

### Fixed
- Engine: a node-merge tolerance based on the wavelength-relative target
  segment length (rather than the shortest segment actually realized by
  the mesh) could merge away a short stub wire's node at low frequency
  or coarse `NBASISPERLAMBDA`, collapsing a segment to zero length and
  producing NaN input impedance via a divide-by-zero in the self-term
  formula. Tolerance is now based on the true shortest realized segment.
- `nml_to_nec.py`: NEC-5 export failed on compact single-line `.nml`
  blocks with more than one `key = value` pair per line (the namelist
  parser only recognized the first assignment per line).
- neomom_input: 3D geometry preview scaled differently on Windows vs.
  Linux due to an oversized ground-plane surface dragging axis
  autoscale; axis limits are now pinned to the actual antenna geometry.
- neomom_Zin: setting a custom Y-axis range shrank the whole plot,
  because the ham-band overlay read the axis limits before the custom
  range was applied.

### Validated
- Engine Z-matrix fill cross-checked against NEC-5/EZNEC for a center-fed
  dipole and a folded dipole (patterns agree to <0.05 dB RMS; resistance
  agrees to <1%; reactance carries a consistent, bounded ~7-11% offset
  traced to NeoMoM's whole-rooftop delta-gap excitation convention vs.
  NEC-5's narrower segment-end convention) and for an open-circuit
  two-wire transmission line across a range of conductor spacings
  (agreement degrades below ~2x wire diameter separation, consistent
  with the known thin-wire modeling limit documented in Burke's NEC-5
  validation manual, not a NeoMoM-specific defect).

### Planned
- Smith chart tab in neomom_Zin
- L/λ and f/f_res x-axis options in neomom_Zin
- Sommerfeld ground model option in engine
- Antenna geometry optimizer
- Touchstone .s1p import for NanoVNA comparison
- macOS build and packaging
