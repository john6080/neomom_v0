# Licensing

NeoMoM is **dual-licensed** under a two-tier structure. Which license
applies depends on which part of the project a file belongs to.

| Part | Path | License | Full text |
|------|------|---------|-----------|
| Computational engine | `engine/` | **Apache-2.0** | [`LICENSE-APACHE`](LICENSE-APACHE), also [`engine/LICENSE`](engine/LICENSE) |
| GUI applications | `neomom_input/`, `neomom_plot/`, `neomom_Zin/`, `neomom_current/` | **MIT** | [`LICENSE-MIT`](LICENSE-MIT), also each component's `LICENSE` |
| Shared GUI support | `shared/` | **MIT** | [`LICENSE-MIT`](LICENSE-MIT) |

Copyright © 2026 John Shaeffer (KZ4TS).

## Why two licenses

- The **engine** is the original scientific/engineering contribution. It is
  released under **Apache-2.0**, which permits use, modification, and
  redistribution while preserving the copyright notice, requiring that
  changes be stated, and granting an explicit patent license.
- The **GUI applications** are provided as working examples and reference
  implementations. They are released under the **MIT License** so you can
  freely use, modify, and redistribute them — including as the starting
  point for your own antenna-analysis tools — with only the copyright
  notice preserved.

Both licenses permit modification and redistribution. If you only need the
GUIs, MIT imposes essentially no restrictions beyond keeping the notice.

## Per-file identification (SPDX)

Every source file carries an [SPDX](https://spdx.dev/) identifier in its
header so the license is unambiguous even for a single file copied out of
the repository:

```python
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 John Shaeffer (KZ4TS)
```

```fortran
! SPDX-License-Identifier: Apache-2.0
! Copyright (c) 2026 John Shaeffer (KZ4TS)
```

The SPDX tag is authoritative for an individual file. The table above
describes the default for each directory.

## Reusing NeoMoM

- **Using or modifying the GUIs (MIT):** keep the copyright notice and the
  MIT permission notice. That's it — fork, adapt, ship.
- **Using or modifying the engine (Apache-2.0):** keep the copyright and
  license, state any significant changes you make, and retain any `NOTICE`
  content. The patent grant protects downstream users.

## Contributing

By contributing you agree your contributions are licensed under the license
of the part you're changing — Apache-2.0 for `engine/`, MIT for the GUI
components and `shared/`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
