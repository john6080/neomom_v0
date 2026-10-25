================================================================================
  NeoMoM — a Method-of-Moments wire-antenna modeling suite
  Version 0.1.0  |  October 2026
  Author: John Shaeffer (KZ4TS)  |  NFARL
  GitHub: https://github.com/john6080/neomom_v0
================================================================================


WHAT IS NEOMOM?
---------------
NeoMoM is a modern, open-source wire antenna modeling suite for amateur radio
operators.  It uses the Method of Moments (MoM) to compute antenna patterns,
feed impedance, and current distribution.  Results have been validated against
NEC5, the accepted gold standard for wire antenna analysis.

NeoMoM is designed to be easy to use.  You describe your antenna graphically,
run the solver, and view results — all without editing card decks or text files.


CONTENTS OF THIS ZIP
--------------------
  neomom              Engine — the MoM solver (run by the GUI, not directly)
  neomom_input        Antenna geometry editor and run control
  neomom_plot         Radiation pattern viewer (2D, 3D, map overlay)
  neomom_Zin          Impedance and SWR sweep viewer
  neomom_current      Current distribution viewer
  README.txt          This file

Linux note: make the executables runnable before first use:
  chmod +x neomom neomom_input neomom_plot neomom_Zin neomom_current


QUICK START
-----------
All five programs can live in the same directory.  neomom (the engine) must
be in the same directory as neomom_input, or on your system PATH.

1. Launch neomom_input

   Linux:    ./neomom_input
   Windows:  double-click neomom_input.exe

2. Define your antenna

   - Globals tab:  set frequency, ground type, and sweep mode
   - Nodes tab:    enter node coordinates (x, y, z) and choose units
   - Wires tab:    connect nodes into wires, set wire radius (always in metres)
   - Excitations:  set the feed point wire and node

3. Run the solver

   Click the Run button.  The engine solves in seconds for most HF antennas.
   neomom_plot opens automatically when the run finishes.

4. View results

   neomom_plot    Opens automatically — shows radiation patterns
   neomom_Zin     Open manually — shows R, X, G, B, SWR vs frequency
                  (run a VNA sweep first to generate the Zin data)
   neomom_current Open manually — shows current distribution on the wires


SWEEP MODES
-----------
Pattern sweep   One radiation pattern per frequency step.
                neomom_plot opens automatically after each run.

VNA sweep       Feed impedance (Zin) vs frequency — no pattern computed.
                Open neomom_Zin to view the results.
                Set step size (default 0.020 MHz) and frequency range.


WIRE RADIUS
-----------
Wire radius is always entered in METRES regardless of the coordinate units
selected for nodes.  Common values:

  AWG 12  (2.05 mm diameter)  ->  0.001028 m
  AWG 14  (1.63 mm diameter)  ->  0.000815 m
  AWG 16  (1.29 mm diameter)  ->  0.000645 m
  1 mm wire                   ->  0.001000 m
  Formula: radius_m = wire_diameter_mm / 2000


OUTPUT FILES
------------
All output files are written to the same directory as the input .nml file.

  antenna_name.txt        Text summary: geometry, ground, impedance, gain
  antenna_name_xxxMHz.csv Pattern data for neomom_plot  (pattern sweep)
  antenna_name_Zin.csv    Impedance data for neomom_Zin (VNA sweep)
  antenna_name_xxxMHz.cur Current distribution data for neomom_current


A SIMPLE TEST
-------------
To verify the installation is working, model a half-wave dipole:

  Nodes (units = metres):
    A:  x=0  y=0  z=10
    B:  x=10 y=0  z=10
    C:  x=20 y=0  z=10

  Wire:
    W1:  nodes A-B-C,  radius = 0.001 m

  Excitation:
    Wire W1,  node B  (centre of the dipole)

  Globals:
    Frequency: 7.2 MHz (single frequency, pattern sweep)
    Ground: real  (epsilon=13, sigma=0.005)

Expected results:
  Feed impedance Zin ~ 73 + j42 ohms at resonance
  Peak gain ~ 7.8 dBi
  Figure-8 azimuth pattern
  Single elevated main lobe in elevation pattern


KNOWN LIMITATIONS (v0.1.0)
---------------------------
  - macOS not yet supported
  - Transmission lines and matching networks not modeled
  - Ground model uses Fresnel reflection (not full Sommerfeld)
  - Smith chart not yet implemented in neomom_Zin


FEEDBACK
--------
Your feedback is valuable.  Please report:
  - Platform (Linux distro / Windows version)
  - Display resolution and scaling setting
  - Any errors on launch or during a run
  - Workflow steps that were confusing
  - Results that looked unexpected

Report issues at: https://github.com/john6080/neomom_v0/issues
Or email:         John Shaeffer, KZ4TS  <john_f_shaeffer@yahoo.com>


================================================================================
  NeoMoM is free and open source.
  Engine: Apache License 2.0  |  GUIs: MIT License
  Copyright (c) 2026 John Shaeffer (KZ4TS)
================================================================================
