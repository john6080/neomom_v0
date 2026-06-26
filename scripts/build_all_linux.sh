#!/bin/bash
# ==============================================================
# build_all_linux.sh
# NeoMOM — full Linux build + package
#
# Builds all three components in order, then harvests into
# packages/linux/ and creates neomom_linux.zip.
# Stops immediately on any failure (set -e).
#
# Usage (from project root):
#   ./scripts/build_all_linux.sh              # ifx Release (default)
#   ./scripts/build_all_linux.sh gfortran     # gfortran Release
#
# Prerequisites:
#   - ifx or gfortran installed and on PATH
#   - makedepf90 installed: sudo apt install makedepf90
#   - python3-tk installed: sudo apt install python3-tk
#   - ~/venvs/neomom_input venv populated from requirements_input.txt
#   - ~/venvs/neomom_plot  venv populated from requirements_plot.txt
#   - upx installed (optional): sudo apt install upx
# ==============================================================

set -e          # stop on any error
set -o pipefail # catch errors inside pipes

# --------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------

COMPILER=${1:-ifx}                          # first arg or default ifx

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ENGINE_DIR="$PROJECT_ROOT/engine/linux"
INPUT_SPEC="$PROJECT_ROOT/input_gui/linux/neomom_input.spec"
PLOT_SPEC="$PROJECT_ROOT/plot_gui/linux/neomom_plot.spec"

INPUT_DIST="$PROJECT_ROOT/input_gui/build/dist"
INPUT_WORK="$PROJECT_ROOT/input_gui/build/work"
PLOT_DIST="$PROJECT_ROOT/plot_gui/build/dist"
PLOT_WORK="$PROJECT_ROOT/plot_gui/build/work"

ENGINE_EXE="$PROJECT_ROOT/build/neomom"

PYINST_INPUT=~/venvs/neomom_input/bin/pyinstaller
PYINST_PLOT=~/venvs/neomom_plot/bin/pyinstaller

PACKAGE_DIR="$PROJECT_ROOT/packages/linux"
PACKAGE_ZIP="$PROJECT_ROOT/packages/neomom_linux.zip"
MODELS_DIR="$PROJECT_ROOT/test_cases/validation_cases"

# --------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;91m'
CYAN='\033[0;36m'
NC='\033[0m'   # no colour

step()  { echo -e "\n${CYAN}==>${NC} $*"; }
ok()    { echo -e "${GREEN}  OK:${NC} $*"; }
die()   { echo -e "${RED}  FAILED:${NC} $*" >&2; exit 1; }

# --------------------------------------------------------------
# PREFLIGHT CHECKS
# --------------------------------------------------------------

step "Preflight checks"

[[ -f "$INPUT_SPEC" ]]  || die "Input spec not found: $INPUT_SPEC"
[[ -f "$PLOT_SPEC"  ]]  || die "Plot spec not found:  $PLOT_SPEC"
[[ -x "$PYINST_INPUT" ]] || die "PyInstaller not found: $PYINST_INPUT"
[[ -x "$PYINST_PLOT"  ]] || die "PyInstaller not found: $PYINST_PLOT"

command -v "$COMPILER" >/dev/null 2>&1 || die "Compiler not found: $COMPILER"
command -v makedepf90  >/dev/null 2>&1 || die "makedepf90 not found. Run: sudo apt install makedepf90"

ok "All preflight checks passed (compiler=$COMPILER)"

# --------------------------------------------------------------
# STEP 1 — Fortran engine
# --------------------------------------------------------------

step "Building Fortran engine (COMPILER=$COMPILER, BUILD=Release)"

cd "$ENGINE_DIR"
make release COMPILER="$COMPILER"

[[ -f "$ENGINE_EXE" ]] || die "Engine build succeeded but exe not found: $ENGINE_EXE"
ok "Engine built: $ENGINE_EXE"

# --------------------------------------------------------------
# STEP 2 — neomom_input GUI
# --------------------------------------------------------------

step "Building neomom_input (PyInstaller)"

mkdir -p "$INPUT_DIST" "$INPUT_WORK"

"$PYINST_INPUT" "$INPUT_SPEC" \
    --distpath "$INPUT_DIST" \
    --workpath "$INPUT_WORK"

[[ -f "$INPUT_DIST/neomom_input" ]] || die "neomom_input exe not found after build"
ok "neomom_input built: $INPUT_DIST/neomom_input"

# --------------------------------------------------------------
# STEP 3 — neomom_plot GUI
# --------------------------------------------------------------

step "Building neomom_plot (PyInstaller)"

mkdir -p "$PLOT_DIST" "$PLOT_WORK"

"$PYINST_PLOT" "$PLOT_SPEC" \
    --distpath "$PLOT_DIST" \
    --workpath "$PLOT_WORK"

[[ -f "$PLOT_DIST/neomom_plot" ]] || die "neomom_plot exe not found after build"
ok "neomom_plot built: $PLOT_DIST/neomom_plot"

# --------------------------------------------------------------
# STEP 4 — Harvest into packages/linux/
# --------------------------------------------------------------

step "Harvesting package"

# Clean and recreate package tree
rm -rf "$PACKAGE_DIR"
mkdir -p \
    "$PACKAGE_DIR/neomom" \
    "$PACKAGE_DIR/neomom_input" \
    "$PACKAGE_DIR/neomom_plot" \
    "$PACKAGE_DIR/models"

cp "$ENGINE_EXE"               "$PACKAGE_DIR/neomom/"
cp "$INPUT_DIST/neomom_input"  "$PACKAGE_DIR/neomom_input/"
cp "$PLOT_DIST/neomom_plot"    "$PACKAGE_DIR/neomom_plot/"

if [[ -d "$MODELS_DIR" ]]; then
    cp -r "$MODELS_DIR"/. "$PACKAGE_DIR/models/"
    ok "Models copied from $MODELS_DIR"
else
    echo "  WARNING: models dir not found, skipping: $MODELS_DIR"
fi

ok "Package tree assembled: $PACKAGE_DIR"

# --------------------------------------------------------------
# STEP 5 — Zip
# --------------------------------------------------------------

step "Creating zip archive"

rm -f "$PACKAGE_ZIP"
cd "$PROJECT_ROOT/packages"
zip -r "neomom_linux.zip" linux/

ok "Package ready: $PACKAGE_ZIP"

# --------------------------------------------------------------
# DONE
# --------------------------------------------------------------

echo ""
echo -e "${GREEN}Build complete.${NC}"
echo "  Engine  : $PACKAGE_DIR/neomom/neomom"
echo "  Input   : $PACKAGE_DIR/neomom_input/neomom_input"
echo "  Plot    : $PACKAGE_DIR/neomom_plot/neomom_plot"
echo "  Archive : $PACKAGE_ZIP"
echo ""
