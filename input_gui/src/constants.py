# constants.py
# Canonical schema + labels + defaults for NeoMoM Studio

# ------------------------------------------------------------
# BLOCK NAMES (Fortran NAMELIST-style)
# ------------------------------------------------------------

FREQ_BLOCK      = "frequency"
GROUND_BLOCK    = "ground"
OPTIONS_BLOCK   = "options"
NODE_BLOCK      = "node"
WIRE_BLOCK      = "wire"
EXCIT_BLOCK     = "excitation"


# ------------------------------------------------------------
# FREQUENCY BLOCK SCHEMA
# ------------------------------------------------------------

FREQ_FIELDS = {
    "fmhz": {
        "label": "Frequency (MHz)",
        "unit": "MHz",
        "default": 7.0,
    },
    "sweep": {
        "label": "Enable Sweep",
        "unit": None,
        "default": False,
    },
    "fstart": {
        "label": "Start Freq",
        "unit": "MHz",
        "default": 7.0,
    },
    "fstop": {
        "label": "Stop Freq",
        "unit": "MHz",
        "default": 7.3,
    },
    "nsteps": {
        "label": "Steps",
        "unit": None,
        "default": 1,
    },
}


# ------------------------------------------------------------
# GROUND BLOCK SCHEMA
# ------------------------------------------------------------

GROUND_TYPES = ["FREE", "PERFECT", "REAL"]

GROUND_FIELDS = {
    "ground_type": {
        "label": "Ground Type",
        "choices": GROUND_TYPES,
        "default": "FREE",
    },
    "conductivity": {
        "label": "Conductivity",
        "unit": "S/m",
        "default": 0.0,
    },
    "permittivity": {
        "label": "Permittivity",
        "unit": None,
        "default": 1.0,
    },
}


# ------------------------------------------------------------
# OPTIONS BLOCK SCHEMA
# ------------------------------------------------------------

OPTIONS_FIELDS = {
    "nBasisPerLambda": {
        "label": "Basis Functions per λ",
        "unit": None,
        "default": 40,
    },
}


# ------------------------------------------------------------
# NODE BLOCK SCHEMA
# ------------------------------------------------------------

NODE_FIELDS = {
    "tag": {
        "label": "Node Tag",
        "default": "",
    },
    "x": {
        "label": "X",
        "unit": "m",
        "default": 0.0,
    },
    "y": {
        "label": "Y",
        "unit": "m",
        "default": 0.0,
    },
    "z": {
        "label": "Z",
        "unit": "m",
        "default": 0.0,
    },
}


# ------------------------------------------------------------
# WIRE BLOCK SCHEMA
# ------------------------------------------------------------

WIRE_FIELDS = {
    "tag": {
        "label": "Wire Tag",
        "default": "",
    },
    "node_tags": {
        "label": "Node Tags",
        "default": [],
    },
    "radius": {
        "label": "Radius",
        "unit": "m",
        "default": 0.001,
    },
    "segments": {
        "label": "Segments",
        "unit": None,
        "default": 1,
    },
}


# ------------------------------------------------------------
# EXCITATION BLOCK SCHEMA
# ------------------------------------------------------------

EXCIT_FIELDS = {
    "wireTag": {
        "label": "Wire Tag",
        "default": "",
    },
    "nodeTag": {
        "label": "Node Tag",
        "default": "",
    },
    "voltage": {
        "label": "Voltage",
        "unit": "V",
        "default": 1.0,
    },
    "phase_deg": {
        "label": "Phase",
        "unit": "deg",
        "default": 0.0,
    },
}
