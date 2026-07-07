# ==============================================================
# NeoMOM — Root Makefile
# Run from: project root
#
# Usage:
#   make clean        → wipe all build artifacts (force full rebuild)
#   make distclean    → clean + wipe packages (back to pure source)
#   make engine       → build Fortran engine only
#   make input        → build neomom_input GUI only
#   make plot         → build neomom_plot GUI only
#   make Zin          → build neomom_Zin GUI only
#   make all          → full build (calls build_all_linux.sh)
#   make copy         → copy all executables to ~/bin
#   make deploy       → full build then copy to ~/bin
#
# Engine compiler selection:
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
	rm -rf neomom_input/build/
	rm -rf neomom_plot/build/
	rm -rf neomom_current/build/
	rm -rf neomom_Zin/build/
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

.PHONY: all engine input plot Zin

all:
	@bash $(SCRIPTS) $(COMPILER)

engine:
	$(MAKE) -C engine/linux release COMPILER=$(COMPILER)

input:
	@mkdir -p neomom_input/build/dist neomom_input/build/work
	$$HOME/venvs/neomom_input/bin/pyinstaller \
	    neomom_input/linux/neomom_input.spec \
	    --distpath neomom_input/build/dist \
	    --workpath neomom_input/build/work

plot:
	@mkdir -p neomom_plot/build/dist neomom_plot/build/work
	$$HOME/venvs/neomom_plot/bin/pyinstaller \
	    neomom_plot/linux/neomom_plot.spec \
	    --distpath neomom_plot/build/dist \
	    --workpath neomom_plot/build/work

Zin:
	@mkdir -p neomom_Zin/build/dist neomom_Zin/build/work
	$$HOME/venvs/neomom_plot/bin/pyinstaller \
	    neomom_Zin/linux/neomom_Zin.spec \
	    --distpath neomom_Zin/build/dist \
	    --workpath neomom_Zin/build/work

# --------------------------------------------------------------
# COPY TO ~/bin — Linux local install
# --------------------------------------------------------------

.PHONY: copy deploy

copy:
	@echo "Copying executables to ~/bin..."
	@mkdir -p $$HOME/bin
	cp build/neomom                            $$HOME/bin/neomom
	cp neomom_input/build/dist/neomom_input    $$HOME/bin/neomom_input
	cp neomom_plot/build/dist/neomom_plot      $$HOME/bin/neomom_plot
	cp neomom_Zin/build/dist/neomom_Zin        $$HOME/bin/neomom_Zin
	@echo "Installed:"
	@echo "  ~/bin/neomom"
	@echo "  ~/bin/neomom_input"
	@echo "  ~/bin/neomom_plot"
	@echo "  ~/bin/neomom_Zin"

deploy: all copy
	@echo "Deploy complete."
