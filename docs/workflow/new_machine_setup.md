# New Machine Setup — NeoMOM

## Overview

Setting up NeoMOM on a new Linux machine from scratch.
Covers Git, cloning the repo, prerequisites, and venv setup.

---

## Step 1 — Install Git

```bash
sudo apt install git
```

Verify:
```bash
git --version
```

---

## Step 2 — Set Git Identity (one time per machine)

```bash
git config --global user.name "john6080"
git config --global user.email "your@email.com"
```

---

## Step 3 — Clone the Repo

Choose a directory to work from, then clone:

```bash
cd ~
mkdir projects          # or wherever you prefer
cd projects
```

### Option A — HTTPS (quickest, uses Personal Access Token)

```bash
git clone https://github.com/john6080/neomom_v0.git
```

When prompted:
```
Username: john6080
Password: <paste PAT token>    (Ctrl+Shift+V to paste in terminal)
```

Then save credentials so you're never prompted again:
```bash
cd neomom_v0
git config --global credential.helper store
git pull                # enter token one final time to save it
```

### Option B — SSH (best for regular use, no token needed after setup)

Generate an SSH key on this machine:
```bash
ssh-keygen -t ed25519 -C "machine description"
# Press Enter for all defaults

# Display the public key
cat ~/.ssh/id_ed25519.pub
```

Add it to GitHub:
- GitHub → Settings → SSH and GPG keys → New SSH key
- Title: e.g. `cabin linux` or `home linux`
- Paste the key → Add SSH key

Then clone:
```bash
git clone git@github.com:john6080/neomom_v0.git
```

No token or password ever needed on this machine.

---

## Step 4 — Install System Prerequisites

```bash
sudo apt install makedepf90       # Fortran dependency generator
sudo apt install python3-tk       # tkinter for Python GUIs
sudo apt install upx              # optional: compresses PyInstaller exe
```

---

## Step 5 — Install Fortran Compiler

### ifx (Intel — preferred)
Download Intel oneAPI HPC Toolkit:
`https://www.intel.com/content/www/us/en/developer/tools/oneapi/hpc-toolkit.html`

Verify after install:
```bash
ifx --version
```

### gfortran (alternative)
```bash
sudo apt install gfortran
```

---

## Step 6 — Create Python Venvs

From the project root:

```bash
# Input GUI venv
python3 -m venv ~/venvs/neomom_input
source ~/venvs/neomom_input/bin/activate
pip install -r input_gui/requirements_input.txt
pip install pyinstaller
deactivate

# Plot GUI venv
python3 -m venv ~/venvs/neomom_plot
source ~/venvs/neomom_plot/bin/activate
pip install -r plot_gui/requirements_plot.txt
pip install pyinstaller
deactivate
```

**Note:** Venvs cannot be copied from another machine — always create fresh.

---

## Step 7 — VS Code Setup

Install VS Code if needed:
```bash
sudo snap install code --classic
```

Open the project:
```bash
cd neomom_v0
code .
```

### launch.json

`launch.json` is committed to the repo and will be present after cloning.
It lives at `.vscode/launch.json` — VS Code picks it up automatically.

If debug configurations are missing, verify the file exists:
```bash
ls .vscode/
```

---

## Step 8 — Verify the Build Works

Test the Fortran engine:
```bash
cd engine/linux
make
```

Test a GUI build:
```bash
cd ~/projects/neomom_v0
make input
```

---

## Personal Access Token (PAT) Storage

If using HTTPS, the token is saved in `~/.git-credentials` after
running `git config --global credential.helper store`.

To view it:
```bash
cat ~/.git-credentials
```

If token expires — generate a new one on GitHub:
- GitHub → Settings → Developer Settings → Personal Access Tokens
- → Tokens (classic) → Generate new token (classic)
- Check **repo** scope → Generate → copy token

Then delete the old credentials and re-enter:
```bash
rm ~/.git-credentials
git pull                # enter new token, it saves automatically
```

---

## Already Have the Project as a ZIP?

If you downloaded from GitHub as a ZIP instead of cloning:

```bash
# Rename the zip folder as backup
mv neomom_v0 neomom_v0_backup

# Clone fresh (connected to GitHub)
git clone https://github.com/john6080/neomom_v0.git
# or
git clone git@github.com:john6080/neomom_v0.git
```

Copy any changes you made in the backup into the fresh clone.
The ZIP folder has no `.git/` — it cannot push or pull.

---

## New Machine Checklist

```
[ ] git installed
[ ] git user.name and user.email configured
[ ] repo cloned (HTTPS or SSH)
[ ] credentials saved (HTTPS) or SSH key added to GitHub (SSH)
[ ] makedepf90 installed
[ ] python3-tk installed
[ ] ifx or gfortran installed
[ ] neomom_input venv created
[ ] neomom_plot venv created
[ ] VS Code installed and project opened
[ ] test build successful
```

---

## Quick Reference — After Setup

```bash
cd ~/projects/neomom_v0

git pull                          # get latest before starting work
# ... make changes ...
git add .
git status                        # review what changed
git commit -m "description"
git push                          # send to GitHub
```
