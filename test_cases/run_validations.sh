#!/usr/bin/env bash
# ============================================================
# run_validations.sh
# Runs neomom on every *.nml file found recursively under
# the 'validations' directory.
#
# Usage:
#   ./run_validations.sh [validations_dir] [neomom_path_or_name]
#
# Defaults:
#   validations_dir       = ./validation_cases
#   neomom_path_or_name   = neomom   (resolved via $PATH)
#
# neomom_path_or_name may be:
#   - a bare command name, e.g. "neomom"      -> looked up on $PATH
#   - a relative/absolute path, e.g. "./bin/neomom" or "/opt/neomom/neomom"
# ============================================================

set -u

VALIDATIONS_DIR="${1:-./validation_cases}"
NEOMOM="${2:-neomom}"

# ── Sanity checks ────────────────────────────────────────────
if [ ! -d "$VALIDATIONS_DIR" ]; then
    echo "ERROR: validations directory not found: $VALIDATIONS_DIR"
    exit 1
fi

# Resolve NEOMOM: if it's a bare name (no slash), look it up on $PATH first;
# otherwise treat it as a direct file path as before.
if [[ "$NEOMOM" != */* ]]; then
    RESOLVED="$(command -v "$NEOMOM" 2>/dev/null || true)"
    if [ -n "$RESOLVED" ]; then
        NEOMOM="$RESOLVED"
    fi
fi

if [ ! -x "$NEOMOM" ]; then
    if [ -f "$NEOMOM" ]; then
        echo "ERROR: neomom executable found but not executable: $NEOMOM"
        echo "       try: chmod +x \"$NEOMOM\""
    else
        echo "ERROR: neomom executable not found: $NEOMOM"
        echo "       (looked on \$PATH and as a direct file path)"
    fi
    exit 1
fi

# Absolute path to neomom (resolve before any 'cd' below)
NEOMOM_ABS="$(cd "$(dirname "$NEOMOM")" && pwd)/$(basename "$NEOMOM")"

# ── Find all .nml files, sorted ──────────────────────────────
mapfile -t NML_FILES < <(find "$VALIDATIONS_DIR" -type f -name "*.nml" | sort)

TOTAL=${#NML_FILES[@]}
PASSED=0
FAILED=0
FAILED_LIST=()

if [ "$TOTAL" -eq 0 ]; then
    echo "No .nml files found under $VALIDATIONS_DIR"
    exit 0
fi

echo "============================================================"
echo "  neomom validation run"
echo "  Executable : $NEOMOM_ABS"
echo "  Search dir : $VALIDATIONS_DIR"
echo "  Found      : $TOTAL .nml file(s)"
echo "============================================================"
echo ""

# ── Run neomom on each .nml file ─────────────────────────────
for NML_PATH in "${NML_FILES[@]}"; do
    NML_DIR="$(cd "$(dirname "$NML_PATH")" && pwd)"
    NML_NAME="$(basename "$NML_PATH")"

    echo "--------------------------------------------------------------"
    echo "  Running : $NML_PATH"

    # Run from the directory containing the .nml file
    pushd "$NML_DIR" > /dev/null
    "$NEOMOM_ABS" "$NML_NAME"
    STATUS=$?
    popd > /dev/null

    if [ "$STATUS" -eq 0 ]; then
        echo "  Result  : PASSED"
        PASSED=$((PASSED + 1))
    else
        echo "  Result  : FAILED (exit code $STATUS)"
        FAILED=$((FAILED + 1))
        FAILED_LIST+=("$NML_PATH")
    fi
done

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  SUMMARY"
echo "  Total  : $TOTAL"
echo "  Passed : $PASSED"
echo "  Failed : $FAILED"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "  Failed cases:"
    for F in "${FAILED_LIST[@]}"; do
        echo "    - $F"
    done
    echo "============================================================"
    exit 1
else
    echo "============================================================"
    exit 0
fi
