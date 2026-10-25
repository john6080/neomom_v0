# NeoMoM v0.1.0 — first public release

NeoMoM is a free, open-source **wire-antenna modeling suite** for amateur radio,
using the **Method of Moments**. Describe an antenna graphically, run the solver,
and view radiation patterns, feed impedance, and current distribution — with
results validated against NEC5.

## Download
- **Windows:** `neomom_windows.zip` — unzip, double-click `neomom_input.exe`
- **Linux:** `neomom_linux.zip` — unzip, `chmod +x neomom*`, run `./neomom_input`

Each zip is **self-contained** — no Python or external libraries to install.
macOS is not yet supported.

## What's included
- **neomom** — Method-of-Moments engine (launched by the GUI)
- **neomom_input** — geometry editor + run control
- **neomom_plot** — 2D/3D patterns, map overlay
- **neomom_Zin** — impedance / SWR sweep viewer
- **neomom_current** — current-distribution viewer
- `examples/` — six ready-to-open antennas (dipole, vertical, delta loop, EFHW, Yagi)
- `quick_start/` (HTML guides) and `README.txt` (quick start + dipole sanity test)
- `nec_reference_decks/` — NEC decks used for validation

## Highlights
- Validated against NEC5 across dipole, monopole, EFHW, J-pole, loop, folded-dipole,
  disk-cone, and Yagi cases.
- HiDPI / 4K aware on Windows and Linux, with a persistent per-user **UI Scale** setting.
- Fully self-contained binaries — nothing to install.

## Known limitations
- macOS not yet supported
- Transmission lines / matching networks not modeled
- Ground model uses Fresnel reflection (not full Sommerfeld)
- Smith chart not yet in neomom_Zin

## Licensing
Dual, permissive: **engine Apache-2.0, GUIs MIT** — use, modify, and redistribute
freely. See `LICENSE-APACHE`, `LICENSE-MIT`, `LICENSING.md`.

## Feedback
Issues: https://github.com/john6080/neomom_v0/issues · Email: john_f_shaeffer@yahoo.com
