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

- Smith chart tab in neomom_Zin
- L/λ and f/f_res x-axis options in neomom_Zin
- Sommerfeld ground model option in engine
- Antenna geometry optimizer
- Touchstone .s1p import for NanoVNA comparison
- macOS build and packaging
