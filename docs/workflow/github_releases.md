# GitHub Releases — NeoMOM Distribution

## Overview

GitHub Releases is how distributable packages are published.
The repo contains source code — Releases contain the built binaries for end users.

```
Source code  →  git push  →  GitHub repo       (developers)
Built zips   →  Release   →  GitHub Releases   (end users)
```

Releases page: `https://github.com/john6080/neomom_v0/releases`

---

## When to create a Release

Not every commit — only when you have a stable milestone worth distributing:
- Bug fix that affects usability
- New feature complete and tested
- Both Linux and Windows builds verified

---

## Step 1 — Build both platforms

**Linux** (from project root):
```bash
make -f Makefile clean
./scripts/build_all_linux.sh
# produces: packages/neomom_linux.zip
```

**Windows** (from project root):
- Do a clean Release build in Visual Studio first
- Then run `build_windows.bat`
- Produces: `packages\neomom_windows.zip`

---

## Step 2 — Create the Release on GitHub

1. Go to `https://github.com/john6080/neomom_v0`
2. Click **Releases** (right sidebar) → **Create a new release**
3. Click **Choose a tag** → type `v0.1` → click **Create new tag: v0.1**
4. **Release title:** `NeoMOM v0.1`
5. **Description:** brief notes on what's in this version
6. Drag and drop into the **Attach binaries** area:
   - `packages/neomom_linux.zip`
   - `packages/neomom_windows.zip`
7. Click **Publish release**

---

## Version numbering

Use semantic versioning: `vMAJOR.MINOR.PATCH`

| Change | Example | Version bump |
|---|---|---|
| Bug fix | Fix pattern plot scaling | v0.1 → v0.1.1 |
| New feature | Add frequency sweep plot | v0.1 → v0.2 |
| Major rewrite | New engine interface | v0.x → v1.0 |

---

## What users download

From the Releases page users see:
```
neomom_linux.zip    ← Linux executable package
neomom_windows.zip  ← Windows executable package
```

Each zip contains:
```
neomom/          ← Fortran engine exe
neomom_input/    ← Input GUI exe
neomom_plot/     ← Plot GUI exe
models/          ← Example/validation cases
```

---

## Release notes template

```
## NeoMOM v0.x

### What's new
- 

### Bug fixes
-

### Known issues
-

### Installation
Unzip the appropriate package for your platform.
No installation required — run the executables directly.

Linux:   chmod +x neomom/neomom neomom_input/neomom_input neomom_plot/neomom_plot
Windows: run .exe files directly
```
