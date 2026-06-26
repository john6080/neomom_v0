# Windows to Linux: File Cleanup Reference
## for Fortran source files (.f90)

---

## Step 1 — Check file types with `file`

```bash
file src/*.f90
```

### What to look for in the output:

| Output contains | Meaning | Action needed |
|---|---|---|
| `ASCII text` | Pure ASCII, clean | None |
| `UTF-8 text` | Unicode, no BOM, LF endings | None |
| `UTF-8 (with BOM) text` | Has BOM marker from Windows | Run dos2unix |
| `with CRLF` | Windows line endings | Run dos2unix |
| `with CRLF, LF line terminators` | Mixed line endings | Run dos2unix |
| `Ruby script` | Harmless misdetection — check with cat -A | Usually fine |

### Example of a problematic file listing:
```
src/Angle_Cut_Module.f90:    Unicode text, UTF-8 (with BOM) text
src/matrix_module.f90:       Ruby script, Unicode text, UTF-8 (with BOM) text, with CRLF, LF line terminators
src/fresnel_reflection_m.f90 Ruby script, Unicode text, UTF-8 text, with CRLF, LF line terminators
```

---

## Step 2 — Inspect a suspicious file with `cat -A`

```bash
cat -A src/antenna_system_m.f90 | head -5
```

### What to look for:

| Symptom | Meaning |
|---|---|
| `M-oM-;M-?` at start of line 1 | UTF-8 BOM — makedepf90 will misparse module name |
| `^M` at end of lines | CRLF line ending — compiler sees `modulename\r` |
| `$` at end of lines | Clean LF ending — fine |

### Example of a dirty file:
```
M-oM-;M-?Module Antenna_System$     ← BOM on line 1
$
!=============================$
```

### Example of a clean file:
```
module basic_header_m$
$
  implicit none$
```

---

## Step 3 — Fix with `dos2unix`

### Install if needed:
```bash
sudo apt install dos2unix
```

### Fix all source files at once:
```bash
dos2unix src/*.f90
```

`dos2unix` in one pass:
- Strips UTF-8 BOM
- Converts CRLF → LF
- Fixes mixed CRLF/LF files

### Verify the fix:
```bash
file src/*.f90
```
All files should now show `ASCII text` or `UTF-8 text` with no mention of BOM or CRLF.

---

## Prevention — VS Code settings on Windows

Add this to your project's `.vscode/settings.json` to prevent the problem at the source:

```json
{
    "files.encoding": "utf8",
    "files.eol": "\n",
    "files.trimTrailingWhitespace": true
}
```

---

## Quick reference — every time you move files from Windows to Linux

```bash
# 1. Check
file src/*.f90

# 2. Fix
dos2unix src/*.f90

# 3. Verify
file src/*.f90

# 4. Build
make clean && make
```

Or just use the Makefile target:
```bash
make fixwin
```
#===================================================
Windows Visual Studio file save settings

Create:  .editorconfig   ! for VS and vs code

# .editorconfig
# Ensures all source files are written clean for Linux

root = true

[*.f90]
charset              = utf-8
end_of_line          = lf
insert_final_newline = true
trim_trailing_whitespace = true


It should live in the project root directory — the same folder that contains your .sln (solution file) and src/ directory:
neomom_AI/
├── .editorconfig        ← goes here
├── neomom.sln
├── src/
│   ├── antenna_system_m.f90
│   ├── mesh_m.f90
│   └── ...
├── build/
├── bin/
└── makefile

Visual Studio automatically searches upward from each source file looking for .editorconfig files, so placing it at the project root covers all files underneath it.

Verify it's working in Visual Studio
After adding the file:
Tools → Options → Text Editor → General
→ "Follow project coding conventions"  ← make sure this is checked
Then when you save any .f90 file, Visual Studio will apply the .editorconfig rules automatically.

Also good practice — add to git
bashgit add .editorconfig
git commit -m "Add editorconfig to enforce LF and UTF-8 without BOM"
That way if anyone else ever works on the project — or you clone it fresh on another Windows machine — the settings travel with the repo automatically. From that point on, dos2unix should never be needed again.
