# ==============================================================
# NeoMOM — Root Makefile
# Run from: project root (AntennaModeling_neoMoM/)
#
# Usage:
#   make clean        → wipe all build artifacts (force full rebuild)
#   make distclean    → clean + wipe packages (back to pure source)
#   make engine       → build Fortran engine only
#   make input        → build neomom_input GUI only
#   make plot         → build neomom_plot GUI only
#   make all          → full build (calls build_all_linux.sh)
#
# Engine compiler selection (passed through to engine/linux/Makefile):
#   make engine COMPILER=gfortran
#   make all    COMPILER=gfortran
# ==============================================================

COMPILER ?= ifx
SCRIPTS  := scripts/build_all_linux.sh

# --------------------------------------------------------------
# CLEAN TARGETS
# --------------------------------------------------------------

.PHONY: clean distclean

clean:
	@echo "Cleaning all build artifacts..."
	rm -rf engine/build/
	rm -rf build/
	rm -rf input_gui/build/
	rm -rf plot_gui/build/
	@echo "Clean complete."

distclean: clean
	@echo "Removing packages..."
	rm -rf packages/linux/
	rm -rf packages/windows/
	rm -rf packages/macos/
	rm -f  packages/neomom_linux.zip
	rm -f  packages/neomom_windows.zip
	rm -f  packages/neomom_macos.zip
	@echo "Distclean complete."

# --------------------------------------------------------------
# BUILD TARGETS
# --------------------------------------------------------------

.PHONY: all engine input plot

all:
	@bash $(SCRIPTS) $(COMPILER)

engine:
	$(MAKE) -C engine/linux release COMPILER=$(COMPILER)

input:
	@mkdir -p input_gui/build/dist input_gui/build/work
	$$HOME/venvs/neomom_input/bin/pyinstaller \
	    input_gui/linux/neomom_input.spec \
	    --distpath input_gui/build/dist \
	    --workpath input_gui/build/work

plot:
	@mkdir -p plot_gui/build/dist plot_gui/build/work
	$$HOME/venvs/neomom_plot/bin/pyinstaller \
	    plot_gui/linux/neomom_plot.spec \
	    --distpath plot_gui/build/dist \
	    --workpath plot_gui/build/work
