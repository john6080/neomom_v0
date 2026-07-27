# Contributing to NeoMoM

Thank you for your interest in NeoMoM. Contributions from the amateur radio
community are welcome and encouraged.

## What kinds of contributions are most useful?

- **Bug reports** — if something doesn't work correctly, open a GitHub Issue
  with a description of what happened and what you expected.

- **Test cases** — `.nml` files for antennas with known behavior (dipoles,
  loops, Yagis) help validate new changes.

- **Documentation** — corrections, clarifications, examples.

- **New features** — discuss first by opening an Issue before writing code.
  This avoids duplicated effort and ensures the feature fits the project's
  direction.

- **Validation data** — measured antenna data to compare against modeled
  results, or comparisons against NEC5/EZNEC.

## Licensing of contributions

By submitting a contribution you agree that:

- Contributions to the `engine/` directory are licensed under the
  **Apache License 2.0**.

- Contributions to the GUI components (`neomom_input/`, `neomom_plot/`,
  `neomom_Zin/`, `neomom_current/`) are licensed under the **MIT License**.

This keeps the project's licensing structure consistent.

## How to contribute

1. Fork the repository on GitHub.
2. Create a branch for your change.
3. Make your changes with clear commit messages.
4. Open a Pull Request describing what you changed and why.

## Code style

- **Fortran**: follow the style of existing source files — modern
  Fortran (2003+), explicit `implicit none`, meaningful variable names.

- **Python**: follow PEP 8. Keep GUI logic and plot logic separated
  (as in the existing `plot_panel.py` / `neomom_plot.py` split).

## Recognition

All contributors will be acknowledged in the `AUTHORS` file.

## Questions?

Open a GitHub Issue or contact the original author via the NFARL club.
