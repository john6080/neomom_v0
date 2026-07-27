# NeoMoM — Antenna Modeling Suite for Amateur Radio

**NeoMoM** is a modern, open-source wire Method of Moments (MoM) antenna
modeling suite designed for amateur radio operators.

Created by **John Shaeffer (KZ4TS)**  
North Fulton Amateur Radio League (NFARL), Georgia, USA

---

## Vision

NeoMoM was developed to give amateur radio operators a modern, accurate,
and genuinely easy-to-use antenna modeling tool — one that does not require
learning 1970s-era card deck input formats or navigating software designed
for a different era of computing.

The first version is specifically designed for new users: hams who want to
understand their antennas without the friction of legacy tools. The
computational engine captures the same physics as NEC5 and produces results
that have been validated against that gold standard. For hams who need
detailed engineering analysis, tools like EZNEC remain available. But for
the large majority of amateur antenna modeling tasks — pattern visualization,
multiband impedance sweeps, resonance identification, geographic coverage
analysis — NeoMoM provides an accessible, accurate, and integrated workflow.

NeoMoM is intended to remain freely available to all hams, students,
educators, and experimenters, and to continue improving through community
contributions. Because it is open source and developed with AI assistance,
it will never go out of date — anyone can extend it as technology and
expectations evolve.

---
## Downloads

Pre-built executables for Linux and Windows are available on the
[Releases page](https://github.com/john6080/neomom_v0/releases).

No installation required — download, unzip, and run.

---------
## The NeoMoM Suite

NeoMoM consists of five integrated components:

| Component | Language | Purpose |
|---|---|---|
| **neomom** (engine) | Fortran | Wire MoM solver — the computational core |
| **neomom_input** | Python | Graphical geometry creation and run control |
| **neomom_plot** | Python | 2D/3D pattern visualization, map overlay |
| **neomom_Zin** | Python | Impedance, admittance, SWR vs frequency |
| **neomom_current** | Python | Current distribution viewer |

### neomom (Computational Engine)

The engine is written in modern Fortran and uses
Rao–Wilton–Glisson (RWG) rooftop basis functions — the same mathematical
foundation as NEC-5. Key features:

- Adaptive meshing: segments per wire recomputed at every frequency
  to maintain 40 segments per wavelength
- Real ground via Fresnel reflection coefficients
- PEC ground via image theory; free-space operation
- Pattern sweep: full 3D far-field pattern at each frequency
- VNA sweep: feed impedance, admittance, and SWR vs frequency
- Command-line flags: `plot=`, `currents=`, `sweep=`
- NEC-5 card deck export; MMANA-GAL export

### neomom_input

Graphical antenna geometry editor. Define nodes, wires, and excitations
on screen. Live 3D preview updates as you work. Run the solver directly
from the GUI. Exports to NEC-5 and MMANA-GAL formats.

### neomom_plot

Radiation pattern visualization: 2D polar (elevation and azimuth),
Cartesian, 3D surface, and heatmap. Geographic map overlay using
cartopy — view your antenna's pattern on a world map, CONUS, or
regional map centered on your location.

### neomom_Zin

Impedance sweep viewer. Shows R, X, G, B, and SWR vs frequency.
Supports multi-dataset overlay — compare NeoMoM results directly
with EZNEC/NEC5 sweep exports on the same plot. Ham band overlays
for all ITU Region 2 bands (160m–23cm). User-selectable Z₀ reference
for SWR computation.

### neomom_current

Current distribution viewer. Shows current magnitude and phase along
wire segments in 3D and 2D views.

---

## Validation

NeoMoM has been validated against NEC-5 (the accepted gold standard for
wire antenna analysis) on a multiband HF loop antenna swept from 2 to 32 MHz.
Both codes use identical RWG basis functions. Results show excellent
agreement across the full frequency range for impedance, admittance, SWR,
and radiation patterns. See `docs/` for the validation report.

---

## Platform Support

| Platform | Status |
|---|---|
| Linux | Fully supported (primary development platform) |
| Windows | Supported (tested on Windows 10/11) |
| macOS | Planned |

---

## Building from Source

### Prerequisites

**Engine:**
- Intel Fortran (ifx) or gfortran
- makedepf90: `sudo apt install makedepf90`

**Python GUIs:**
- Python 3.10+
- See `requirements_input.txt`, `requirements_plot.txt`, `requirements_Zin.txt`,
  `requirements_current.txt`

### Build (Linux)

```bash
# Engine only
cd engine/linux
make release COMPILER=ifx       # or COMPILER=gfortran

# Full build (engine + all GUIs) and package
./scripts/build_all_linux.sh

# Install to ~/bin
make copy
```

### Build (Windows)

1. Build the engine in Visual Studio (Release configuration)
2. Run `build_all_windows.ps1` from PowerShell

See `docs/dev_guides/` for detailed build instructions.

---

## Quick Start

```bash
# Run from source
cd neomom_input/src
python3 neomom_input.py

# Or if installed to ~/bin
neomom_input
```

1. Open **neomom_input**, define your antenna geometry, set frequency
2. Click **Run** — the engine solves in seconds
3. **neomom_plot** launches automatically showing the radiation pattern
4. For impedance sweeps, switch to **VNA Sweep** mode and open
   **neomom_Zin** to view R, X, G, B, and SWR vs frequency

---

## Citation

If NeoMoM contributes to your research, publication, QST article,
club presentation, or antenna design, please cite this project and
acknowledge the original author:

> John Shaeffer (KZ4TS), *NeoMoM Antenna Modeling Suite*,
> https://github.com/john6080/neomom_v0, 2026.

GitHub users can click the **"Cite this repository"** button
(powered by `CITATION.cff`) to get a formatted citation automatically.

---

## Licensing

NeoMoM uses a two-tier licensing structure:

**NeoMoM Computational Engine (`engine/`) — Apache License 2.0**

The engine is the original scientific and engineering contribution of
John Shaeffer. You may use, modify, and redistribute it freely provided
you preserve the copyright notice, include the license, and note any
modifications. See `engine/LICENSE`.

**GUI Components — MIT License**

The Python GUI applications are provided as working examples and reference
implementations. You are encouraged to use them as starting points for
your own antenna analysis tools. Preserve the copyright notice.
See individual component `LICENSE` files.

---

## Contributing

Contributions are welcome. See `CONTRIBUTING.md` for guidelines.
All contributors are acknowledged in `AUTHORS`.

---

## Acknowledgments

NeoMoM builds on:

- S. M. Rao, D. R. Wilton, and A. W. Glisson (1982) — RWG basis functions
- The NEC development team at Lawrence Livermore National Laboratory
- Roy Lewallen (W7EL) — EZNEC, which made antenna modeling accessible
  to the ham community for decades
- The worldwide amateur radio community
