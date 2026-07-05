# Local Git Server — NeoMOM / Private Projects

## Overview

A bare Git repository on your LAN server gives you full version control
without GitHub. Useful for private projects you don't want to publish.

```
Linux workstation  ←→  LAN server (bare repo)  ←→  Windows laptop
```

Your machines push and pull from the server exactly like GitHub.

---

## Concepts

**Local `.git/` folder** — a complete repository on your own machine.
No remote needed. Full history, diffs, commits — everything works locally.

**Bare repository** — a `.git/` database on the server with no working files.
This is what your machines push to and pull from. Convention: named `projectname.git`.

**Remote** — a named pointer to another repository (GitHub, LAN server, etc.).
A project can have multiple remotes.

---

## One-Time Server Setup

SSH into your server and create the bare repo:

```bash
ssh john@server
mkdir -p ~/repos/myproject.git
cd ~/repos/myproject.git
git init --bare
exit
```

---

## On Your Linux Workstation

### New project — push existing local repo to server:
```bash
cd ~/myproject
git remote add origin john@server:~/repos/myproject.git
git push -u origin main
```

### Daily workflow — identical to GitHub:
```bash
git pull                          # get latest from server
# ... work ...
git add .
git commit -m "description"
git push                          # send to server
```

---

## On Windows Laptop

### Clone from server (new machine setup):
```powershell
git clone john@server:~/repos/myproject.git
cd myproject
```

### Or connect existing project to server:
```powershell
git remote add origin john@server:~/repos/myproject.git
git push -u origin main
```

---

## SSH Authentication (no password prompts)

Uses SSH keys — same keys you use to SSH into the server normally.

### Set up SSH keys (one time per machine):
```bash
# Generate key if you don't have one
ssh-keygen -t ed25519

# Copy key to server — enables passwordless access
ssh-copy-id john@server
```

After this, `git push` and `git pull` require no password.

---

## Allowing Others to Pull

Anyone with SSH access to your server can clone and pull:
```bash
git clone john@server:~/repos/myproject.git
```

### Access control options:

**Read-only for others** — set repo permissions on server:
```bash
chmod -R 755 ~/repos/myproject.git
```

**Full control** — add SSH accounts on the server for each person.
Remove their account to revoke access.

**Fine-grained control** — Gitolite tool manages multiple users and repos
with per-repo, per-branch permissions. Overkill for small teams.

---

## Accessing Outside Your LAN

By default the server repo is LAN-only. Options:

| Method | Effort | Security |
|---|---|---|
| VPN | Medium setup, easy use | Best — recommended |
| SSH tunnel | Technical | Good |
| Router port forwarding | Easy | Use with caution |

VPN is the best option for personal use — connect to home network
remotely, then access server as if you were on LAN.

---

## Local-Only (No Server)

If you don't need sharing or backup to server, local `.git/` alone is enough:

```bash
git init
git add .
git commit -m "initial commit"
# no git remote add needed
```

Daily workflow:
```bash
git add .
git commit -m "description"
# no git push needed
```

**Risk:** `.git/` lives on same drive as project — drive failure loses everything.

**Backup solution:**
```bash
# Periodically back up entire project including .git/ to external drive
rsync -av ~/myproject/ /media/backup/myproject/
```

---

## Using Both Server and GitHub

Nothing prevents having two remotes — local server for daily work,
GitHub for publishing releases:

```bash
git remote add origin john@server:~/repos/myproject.git   # primary
git remote add github https://github.com/john6080/repo.git # secondary
```

Push to both when ready:
```bash
git push origin main    # → local server (daily)
git push github main    # → GitHub (when publishing)
```

Verify your remotes anytime:
```bash
git remote -v
```

---

## Summary

| Need | Solution |
|---|---|
| Private, local only | `git init` + commit, no remote |
| Private, backed up, shareable on LAN | Bare repo on LAN server |
| Private, accessible remotely | LAN server + VPN |
| Public distribution | GitHub (public repo or Releases) |
| Private + publish selectively | LAN server (primary) + GitHub (secondary) |

---

## Quick Reference — Server Repo Commands

```bash
# Create new bare repo on server
ssh john@server "mkdir -p ~/repos/PROJECT.git && git -C ~/repos/PROJECT.git init --bare"

# Add server as remote (on workstation)
git remote add origin john@server:~/repos/PROJECT.git

# Push to server
git push -u origin main

# Pull from server
git pull

# Clone from server (on another machine)
git clone john@server:~/repos/PROJECT.git

# List all remotes
git remote -v

# Remove a remote
git remote remove origin
```
