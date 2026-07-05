# Git Workflow — NeoMOM Development

## Overview

GitHub repo: `https://github.com/john6080/neomom_v0`

Primary development machine: **Linux (Ubuntu)**
Secondary machine: **Windows**

---

## Daily Linux Workflow

### Start of day — always pull first
```bash
cd ~/Ant_neomom_to_git/AntennaModeling_neoMoM
git pull
```

### End of day — commit and push
```bash
git add .
git status                        # review what changed before committing
git commit -m "brief description of what changed"
git push
```

### Good commit message examples
```
git commit -m "excitation_m: fix unused variable warning"
git commit -m "neomom_plot: add polar scale selector"
git commit -m "build: update harvest script for new model paths"
git commit -m "docs: update build instructions"
```

---

## Switching to Windows

Always pull before starting work on Windows:
```powershell
cd path\to\AntennaModeling_neoMoM
git pull
# ... do your work ...
git add .
git commit -m "windows: description of change"
git push
```

Then when returning to Linux:
```bash
git pull    # get the Windows changes
```

---

## Useful Commands

```bash
git status           # what has changed since last commit
git diff             # see exact line-by-line changes
git log --oneline    # see commit history, compact view
git pull             # get latest from GitHub
git push             # send commits to GitHub
git remote -v        # confirm where push/pull points to
```

---

## Safety Rules

1. **Always pull before starting work** — especially after working on the other machine
2. **Commit before pulling** — if you have local changes, commit them first
3. **Never edit the same file on both machines** without pushing/pulling in between
4. **Build artifacts are gitignored** — exes, .o files, packages, zips are never committed

---

## Authentication

GitHub requires a Personal Access Token (PAT) — not your password.

- Token is stored in `~/.git-credentials` on Linux (set up with `credential.helper store`)
- If token expires: generate a new one on GitHub → Settings → Developer Settings →
  Personal Access Tokens → Tokens (classic) → Generate new token (classic)
- Check **repo** scope, copy token, delete `~/.git-credentials`, do a push and enter new token

---

## What git pull does

- Fetches latest commits from GitHub
- Updates only files that changed on GitHub
- Never touches build artifacts (gitignored)
- Refuses to overwrite uncommitted local changes (Git protects you)

## What git push does

- Sends your local commits to GitHub
- Only source files are ever pushed (build artifacts are gitignored)
- Requires authentication (PAT)
