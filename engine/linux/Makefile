# ============================================================
# NeoMOM Engine — Dispatcher Makefile
# Invoke from: engine/linux/
#
# Usage:
#   make                          → ifx Debug (default)
#   make COMPILER=gfortran        → gfortran Debug
#   make release                  → ifx Release
#   make release COMPILER=gfortran → gfortran Release
#   make clean                    → clean engine/build/
#   make distclean                → clean engine/build/ + top build exe
# ============================================================

COMPILER ?= ifx
BUILD    ?= Debug

# Forward all targets to the appropriate compiler-specific makefile.
# Note: 'release' and 'debug' targets set BUILD internally — do not
# forward BUILD for those or the default Debug value overrides them.
.PHONY: all debug release clean distclean install deps copy

all install deps clean distclean:
	$(MAKE) -f makefile_$(COMPILER) $@ BUILD=$(BUILD)

debug release:
	$(MAKE) -f makefile_$(COMPILER) $@

# Copy final executable to ~/bin/ for local use
copy:
	cp ../../build/neomom ~/bin/
	@echo "Copied neomom to ~/bin/"
