import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import re
import os
import sys
import queue

# --- INSERT AFTER LINE 6 ---
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

#from maa_parser import parse_maa_file, wrap_maa_into_model
from maa_parser import parse_maa_file, wrap_maa_into_model

from neomom_model import NeoMoMModel
from constants import FREQ_FIELDS, GROUND_FIELDS, OPTIONS_FIELDS

# ----------------------------------------------------------------------
# Parsing helpers for this specific MoM namelist structure
# ----------------------------------------------------------------------

# ── PyInstaller-aware helper-module locator ───────────────────────────────────
def _find_helper_py(filename):
    """
    Locate a helper .py file whether running from source or as a
    PyInstaller --onefile bundle.

    Source layout  : searches alongside __file__ then one level up.
    Frozen (bundle): PyInstaller extracts --add-data files into sys._MEIPASS;
                     we look there instead.

    Returns a pathlib.Path on success, None if not found.
    """
    from pathlib import Path
    if getattr(sys, 'frozen', False):          # running inside PyInstaller bundle
        search = [Path(sys._MEIPASS)]
    else:                                      # running from source
        here = Path(__file__).resolve().parent
        search = [here, here.parent]
    for d in search:
        p = d / filename
        if p.exists():
            return p
    return None
# ─────────────────────────────────────────────────────────────────────────────

NAMELIST_START_RE = re.compile(r"^\s*&(\w+)", re.IGNORECASE)
NAMELIST_END_RE = re.compile(r"^\s*/\s*$")

NODE_LIST_RE = re.compile(
    r"node_list\(\s*(\d+)\s*\)\s*=\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)",
    re.IGNORECASE,
)

ASSIGN_RE = re.compile(r"(\w+)\s*=\s*(.+)", re.IGNORECASE)

# mom_nml_parser.py


def parse_run_title(lines):
    """
    Parse a RunTitle block from an .nml file.
    Normalizes mixed-case keys and strips quotes.
    """
    rt = {}

    for line in lines:
        line_nc = _strip_comment(line)
        if not line_nc:
            continue

        m = ASSIGN_RE.match(line_nc)
        if m:
            raw_key = m.group(1).strip()
            raw_val = m.group(2).strip().rstrip(",")

            # Remove quotes
            if (raw_val.startswith("'") and raw_val.endswith("'")) or (
                raw_val.startswith('"') and raw_val.endswith('"')
            ):
                raw_val = raw_val[1:-1]

            # Normalize using your global helper
            key, val = normalize_nml_key_value(raw_key, raw_val)
            rt[key] = val

    return rt

def normalize_nml_key_value(key, val):
    key = key.strip().lower()
    val = val.strip().strip('"').strip("'")

    if key in ("wiretag", "nodetag", "tag", "node"):
        return key, val.upper()

    try:
        if "." in val:
            return key, float(val)
        return key, int(val)
    except ValueError:
        pass

    return key, val



def _strip_comment(line: str) -> str:
    return line.split("!", 1)[0].strip()


def parse_namelist_blocks(path):
    with open(path, "r") as f:
        lines = f.readlines()

    blocks = []
    current_name = None
    current_lines = []

    for raw in lines:
        line = raw.rstrip("\n")
        m_start = NAMELIST_START_RE.match(line)
        if m_start:
            current_name = m_start.group(1)
            current_lines = []
            continue

        if current_name is not None:
            if NAMELIST_END_RE.match(line):
                blocks.append((current_name, current_lines[:]))
                current_name = None
                current_lines = []
            else:
                current_lines.append(line)

    return blocks


def parse_scalar_block(lines):
    """
    Generic parser for scalar key=value blocks.
    Normalizes mixed-case keys/values, then maps keys to GUI schema.
    """
    block = {}

    for line in lines:
        line_nc = _strip_comment(line)
        if not line_nc:
            continue

        m = ASSIGN_RE.match(line_nc)
        if m:
            raw_key = m.group(1).strip()
            raw_val = m.group(2).strip().rstrip(",")

            # Strip quotes
            if (raw_val.startswith("'") and raw_val.endswith("'")) or (
                raw_val.startswith('"') and raw_val.endswith('"')
            ):
                raw_val = raw_val[1:-1]

            # Normalize using global helper
            key, val = normalize_nml_key_value(raw_key, raw_val)
            block[key] = val

    # --- Canonicalize keys for GUI compatibility ---

    # Frequency block
    if "nfreq" in block:
        block["nFreq"] = block.pop("nfreq")

    # Ground block
    if "ground_plane" in block:
        # GUI expects "Ground_Plane"
        block["Ground_Plane"] = block.pop("ground_plane").lower().strip()

    # OPTIONS block
    if "nbasisperlambda" in block:
        # GUI expects "NBASISPERLAMBDA"
        block["NBASISPERLAMBDA"] = block.pop("nbasisperlambda")

    if "output_currents" in block:
        raw = str(block["output_currents"]).strip().upper()
        block["output_currents"] = raw in (".TRUE.", "TRUE", "T", "YES", "1")

    # RunTitle block (GUI already uses lowercase "title")
    if "title" in block:
        block["title"] = block["title"]

    return block


    # """Parse simple key = value lines into a dict (no arrays)."""
    # result = {}
    # for line in lines:
    #     line = _strip_comment(line)
    #     if not line:
    #         continue
    #     m = ASSIGN_RE.match(line)
    #     if not m:
    #         continue
    #     key = m.group(1).strip()
    #     val = m.group(2).strip().rstrip(",")
    #     # strip quotes if present
    #     if (val.startswith("'") and val.endswith("'")) or (
    #         val.startswith('"') and val.endswith('"')
    #     ):
    #         val = val[1:-1]
    #     result[key] = val
    # return result


def parse_node_input(lines):
    meta = {}
    nodes = []

    for line in lines:
        line_nc = _strip_comment(line)
        if not line_nc:
            continue

        # First: handle node list entries (index, tag, x, y, z)
        m_node = NODE_LIST_RE.search(line_nc)
        if m_node:
            idx = int(m_node.group(1))

            # Normalize tag and coordinates (strip quotes added by writer)
            tag = m_node.group(2).strip().strip("'\"").upper()
            x = m_node.group(3).strip()
            y = m_node.group(4).strip()
            z = m_node.group(5).strip()

            nodes.append(
                {
                    "index": idx,
                    "tag": tag,
                    "x": x,
                    "y": y,
                    "z": z,
                }
            )
            continue

        # Second: handle meta assignments (zHeight, units, nNodes, etc.)
        m = ASSIGN_RE.match(line_nc)
        if m:
            raw_key = m.group(1).strip()
            raw_val = m.group(2).strip().rstrip(",")

            # Remove quotes
            if (raw_val.startswith("'") and raw_val.endswith("'")) or (
                raw_val.startswith('"') and raw_val.endswith('"')
            ):
                raw_val = raw_val[1:-1]

            # Normalize using the global helper
            key, val = normalize_nml_key_value(raw_key, raw_val)
            meta[key] = val

    # Sort nodes by index
    nodes.sort(key=lambda r: r["index"])
    #print('148: node input - meta  : ', meta)
    #print('148: node input - nodes : ', nodes)
    return meta, nodes


def parse_wire_primitive(lines):

    wire = {}

    for line in lines:
        line_nc = _strip_comment(line)
        if not line_nc:
            continue

        m = ASSIGN_RE.match(line_nc)
        if m:
            raw_key = m.group(1).strip()
            raw_val = m.group(2).strip().rstrip(",")

            if (raw_val.startswith("'") and raw_val.endswith("'")) or (
                raw_val.startswith('"') and raw_val.endswith('"')
            ):
                raw_val = raw_val[1:-1]

            key, val = normalize_nml_key_value(raw_key, raw_val)

            if key == "nodetags":
                tags = [t.strip().strip("'\"").upper() for t in val.split()]
                wire["nodetags"] = tags
                continue

            wire[key] = val

    # Canonicalize keys for GUI + preview
    if "nnodes" in wire:
        wire["nNodes"] = wire.pop("nnodes")

    if "nodetags" in wire:
        wire["nodeTags"] = wire.pop("nodetags")

    return wire
    

def parse_excitation_input(lines):
    """
    Parse an EXCITATION_INPUT block from an .nml file.
    Handles mixed-case keys, mixed-case values, and normalizes tags.
    """
    ex = {}

    for line in lines:
        line_nc = _strip_comment(line)
        if not line_nc:
            continue

        # Match key = value pairs
        m = ASSIGN_RE.match(line_nc)
        if m:
            raw_key = m.group(1).strip()
            raw_val = m.group(2).strip().rstrip(",")

            # Remove quotes if present
            if (raw_val.startswith("'") and raw_val.endswith("'")) or (
                raw_val.startswith('"') and raw_val.endswith('"')
            ):
                raw_val = raw_val[1:-1]

            # Normalize key/value
            key, val = normalize_nml_key_value(raw_key, raw_val)

            # Special handling for wiretag/nodetag
            if key in ("wiretag", "nodetag"):
                ex[key] = val.upper()
                continue

            # Store normalized key/value
            ex[key] = val

    return ex


def parse_mom_nml(path):
    blocks = parse_namelist_blocks(path)

    model = {
        "RunTitle": {"title": ""},
        "Frequency_MHz": {"fmin": "", "fmax": "", "nFreq": ""},
        "Ground": {"Ground_Plane": "", "epsilon": "", "sigma": ""},
        "OPTIONS": {"NBASISPERLAMBDA": "", "output_currents": False},
        "node_input_meta": {"zHeigth": "", "nNodes": "", "units": ""},
        "nodes": [],
        "wires": [],
        "excitations": [],
    }

    for name, lines in blocks:
        name_u = name.upper()
        if name_u == "RUNTITLE":
            model["RunTitle"] = parse_scalar_block(lines)
        #elif name_u == "RUNTITLE":
        #    model["RunTitle"] = parse_run_title(lines)


        elif name_u == "FREQUENCY_MHZ":
            model["Frequency_MHz"] = parse_scalar_block(lines)
        elif name_u == "GROUND":
            model["Ground"] = parse_scalar_block(lines)
        elif name_u == "OPTIONS":
            model["OPTIONS"] = parse_scalar_block(lines)
        elif name_u == "NODE_INPUT":
            meta, nodes = parse_node_input(lines)
            model["node_input_meta"] = meta
            model["nodes"] = nodes
        elif name_u == "WIRE_PRIMITIVE":
            wp = parse_wire_primitive(lines)
            model["wires"].append(wp)
        # elif name_u == "EXCITATION_INPUT":
        #     ex = parse_excitation_input(lines)
        #     model["excitations"].append(ex)
        elif name_u == "EXCITATION_INPUT":
            raw_ex = parse_excitation_input(lines)

            # Normalize to GUI schema
            # ex = {
            #     "wiretag": f"EX{len(model['excitations'])+1}",
            #     "nodetag": raw_ex.get("node") or raw_ex.get("nodetag") or raw_ex.get("port"),
            #     "amp": raw_ex.get("amp", ""),
            #     "phase": raw_ex.get("phase", "")
            # }
            ex = {
                "wiretag": raw_ex.get("wiretag"),
                "nodetag": raw_ex.get("nodetag"),
                "amp": raw_ex.get("amp", ""),
                "phase": raw_ex.get("phase", "")
            }
            model["excitations"].append(ex)

            #print( '197: model["excitations"]',model["excitations"]) 
            #print()

    # derive nNodes from nodes if not set
    if model["nodes"]:
        model["node_input_meta"].setdefault("nNodes", str(len(model["nodes"])))

    return model


def _dict_to_model(d: dict) -> "NeoMoMModel":
    """
    Convert the dict returned by parse_mom_nml() or wrap_maa_into_model()
    into a NeoMoMModel dataclass.  Single bridge between parsers and GUI.
    """
    from neomom_model import (NeoMoMModel, FrequencyBlock, GroundBlock,
                               OptionsBlock, NodeInputMeta, Node, Wire, Excitation)
    m = NeoMoMModel()
    rt = d.get("RunTitle", {})
    m.run_title = rt.get("title", "Untitled NeoMoM Run")
    fq = d.get("Frequency_MHz", {})
    try:
        m.frequency = FrequencyBlock(
            fmin  = float(fq.get("fmin",  7.0) or 7.0),
            fmax  = float(fq.get("fmax",  7.0) or 7.0),
            nFreq = int(  fq.get("nFreq", 1)   or 1),
        )
    except (TypeError, ValueError): pass
    gnd = d.get("Ground", {})
    raw_plane = str(gnd.get("Ground_Plane", "free")).strip().upper()
    gtype = "FREE" if raw_plane in ("FREE","FREE_SPACE") else "PERFECT" if raw_plane == "PERFECT" else "REAL"
    try:
        m.ground = GroundBlock(
            ground_type   = gtype,
            conductivity  = float(gnd.get("sigma",   0.0) or 0.0),
            permittivity  = float(gnd.get("epsilon", 1.0) or 1.0),
        )
    except (TypeError, ValueError): pass
    opt = d.get("OPTIONS", {})
    try:
        m.options = OptionsBlock(
            nBasisPerLambda = int(opt.get("NBASISPERLAMBDA", 40) or 40),
            output_currents = bool(opt.get("output_currents", False)),
        )
    except (TypeError, ValueError): pass
    meta = d.get("node_input_meta", d.get("Node_input", {}).get("meta", {}))
    try:
        m.node_input_meta = NodeInputMeta(
            zHeight = float(meta.get("zheight", meta.get("zHeight", 0.0)) or 0.0),
            units   = str(meta.get("units", "meters")),
        )
    except (TypeError, ValueError): pass
    node_list = d.get("nodes", d.get("Node_input", {}).get("nodes", []))
    m.nodes = []
    for n in node_list:
        try:
            m.nodes.append(Node(
                tag = str(n.get("tag", "")).upper(),
                x   = float(n.get("x", 0.0)),
                y   = float(n.get("y", 0.0)),
                z   = float(n.get("z", 0.0)),
            ))
        except (TypeError, ValueError): continue
    wire_list = d.get("wires", d.get("Wire_primitive", []))
    m.wires = []
    for w in wire_list:
        raw_tags = w.get("nodeTags", w.get("node_tags", []))
        node_tags = [t.strip().upper() for t in raw_tags if t]
        try:
            m.wires.append(Wire(
                tag       = str(w.get("tag", "")).upper(),
                node_tags = node_tags,
                radius    = float(w.get("radius", 0.001) or 0.001),
                segments  = int(w.get("segments", w.get("nNodes", len(node_tags))) or 1),
            ))
        except (TypeError, ValueError): continue
    excit_list = d.get("excitations", d.get("Excitation_input", []))
    m.excitations = []
    for ex in excit_list:
        try:
            m.excitations.append(Excitation(
                wireTag   = str(ex.get("wiretag", ex.get("wireTag",   ""))).upper(),
                nodeTag   = str(ex.get("nodetag", ex.get("nodeTag",   ""))).upper(),
                voltage   = float(ex.get("voltage",   ex.get("amp",   1.0)) or 1.0),
                phase_deg = float(ex.get("phase_deg", ex.get("phase", 0.0)) or 0.0),
            ))
        except (TypeError, ValueError): continue
    return m


def validate_model(model):
    errors = []

    # --- Node validation ---
    node_tags = {n.tag for n in model.nodes}
    if len(node_tags) != len(model.nodes):
        errors.append("Duplicate node tags detected.")

    for n in model.nodes:
        for coord in ("x", "y", "z"):
            try:
                float(getattr(n, coord))
            except (TypeError, ValueError):
                errors.append(f"Node {n.tag} has non-numeric {coord}.")

    # --- Wire validation ---
    for w in model.wires:
        if not w.tag:
            errors.append("Wire missing tag.")
        if len(w.node_tags) < 2:
            errors.append(f"Wire {w.tag} has fewer than 2 node tags.")
        for nt in w.node_tags:
            if nt not in node_tags:
                errors.append(f"Wire {w.tag} references unknown node '{nt}'.")
        try:
            float(w.radius)
        except (TypeError, ValueError):
            errors.append(f"Wire {w.tag} has non-numeric radius.")

    # --- Excitation validation ---
    wire_tags = {w.tag for w in model.wires}
    for ex in model.excitations:
        if ex.wireTag not in wire_tags:
            errors.append(f"Excitation references unknown wire '{ex.wireTag}'.")
        if ex.nodeTag not in node_tags:
            errors.append(f"Excitation references unknown node '{ex.nodeTag}'.")

    return errors

###end parse_mom_nml


# ----------------------------------------------------------------------
# Formatting back to .nml
# ----------------------------------------------------------------------

def fmt_scalar_block(name, dct):
    lines = [f"&{name}"]
    for k, v in dct.items():
        if v == "":
            continue
        if isinstance(v, str) and " " in v and not v.replace(".", "", 1).isdigit():
            val = f"'{v}'"
        else:
            val = v
        lines.append(f"   {k} = {val}")
    lines.append("/\n")
    return "\n".join(lines)


def fmt_node_input(meta, nodes):
    lines = ["&node_input"]
    # keep order similar to example
    for key in ["zHeigth", "nNodes", "units"]:
        if key in meta and meta[key] != "":
            val = meta[key]
            if key == "units":
                val = f"'{val}'"
            lines.append(f" {key} = {val}")

    lines.append("")
    for i, node in enumerate(nodes, start=1):
        tag = node["tag"]
        x = node["x"]
        y = node["y"]
        z = node["z"]
        lines.append(f" node_list({i}) = {tag}, {x}, {y}, {z}")
    lines.append("/\n")
    return "\n".join(lines)


def fmt_wire_primitive(wp):
    lines = ["&wire_primitive"]
    tag = wp.get("tag", "")
    nNodes = wp.get("nNodes", "")
    nodeTags = wp.get("nodeTags", [])
    radius = wp.get("radius", "")

    if tag:
        lines.append(f"   tag   = {tag},")
    if nNodes:
        lines.append(f"   nNodes = {nNodes},")
    if nodeTags:
        lines.append("   nodeTags = " + " ".join(nodeTags))
    if radius:
        lines.append(f"   radius     = {radius}")
    lines.append("/\n")
    return "\n".join(lines)


def fmt_excitation_input(ex):
    lines = ["&excitation_input"]
    wt = ex.get("wiretag", "")
    nt = ex.get("nodetag", "")
    if wt:
        lines.append(f"   wiretag = {wt}")
    if nt:
        lines.append(f"   nodetag = {nt}")
    lines.append("/\n")
    return "\n".join(lines)


def format_mom_nml(model):
    out = []

    out.append(fmt_scalar_block("RunTitle", model["RunTitle"]))
    out.append(fmt_scalar_block("Frequency_MHz", model["Frequency_MHz"]))
    out.append(fmt_scalar_block("Ground", model["Ground"]))
    out.append(fmt_scalar_block("OPTIONS", model["OPTIONS"]))
    out.append(fmt_node_input(model["node_input_meta"], model["nodes"]))

    for wp in model["wires"]:
        out.append(fmt_wire_primitive(wp))

    for ex in model["excitations"]:
        out.append(fmt_excitation_input(ex))

    return "\n".join(out)


# ----------------------------------------------------------------------
# GUI components
# ----------------------------------------------------------------------

from neomom_model import Node

#start class NodesFrame()
class NodesFrame(ttk.Frame):

    #from neomom_model import Node

    def _reset_editor(self):
        """Prefill editor with next tag and default coordinates."""
        self.tag_var.set(self._next_tag())
        self.x_var.set("0.0")
        self.y_var.set("0.0")
        self.z_var.set("0.0")

    def save_to_model(self):
        try:
            m = self.model

            # NodeInputMeta
            m.node_input_meta.zHeight = float(self.zheight_var.get())
            m.node_input_meta.units   = self.units_var.get()

            # Node list
            m.nodes.clear()
            for row in self.tree.get_children():
                tag, x, y, z = self.tree.item(row, "values")
                m.nodes.append(Node(
                    tag=str(tag),
                    x=float(x),
                    y=float(y),
                    z=float(z)
                ))

        except Exception as e:
            messagebox.showerror("Invalid Node Entry", str(e))
            return False

        return True





    """
    Nodes editor: Treeview on top, one-line editor on bottom.
    Clean grid layout, uppercase tag normalization, stable add/apply/delete.
    """
    def __init__(self, master, model, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.model = model

        print("NodesFrame instance:", id(self))

        # ------------------------------------------------------------
        # Configure GRID layout for this frame
        # ------------------------------------------------------------
        self.rowconfigure(0, weight=1)   # Treeview expands
        self.rowconfigure(1, weight=0)   # Editor stays visible
        self.columnconfigure(0, weight=1)

        # ------------------------------------------------------------
        # Tk Variables (must be defined before widgets)
        # ------------------------------------------------------------
        self.units_var   = tk.StringVar(value="meters")   # radio buttons
        self.zheight_var = tk.StringVar(value="0.0")
        self.zheight_var.trace_add("write", self._on_zheight_changed)
        self.units_var.trace_add("write", self._on_units_changed)

        self.tag_var = tk.StringVar()
        self.x_var   = tk.StringVar()
        self.y_var   = tk.StringVar()
        self.z_var   = tk.StringVar()

        # ============================================================
        # TOP: Treeview
        # ============================================================
        self.tree = ttk.Treeview(
            self,
            columns=("tag", "x", "y", "z"),
            show="headings",
            height=10,
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        for col in ("tag", "x", "y", "z"):
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=100, anchor="center")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ============================================================
        # Editor frame (parent for ALL editor widgets)
        # ============================================================
        editor_frame = ttk.Frame(self)
        editor_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))
        self.editor_frame = editor_frame

        # ============================================================
        # Units (radio buttons) — FIRST ROW
        # ============================================================
        units_frame = ttk.Frame(editor_frame)
        units_frame.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))

        ttk.Label(units_frame, text="Units:").grid(row=0, column=0, padx=(0, 6))

        ttk.Radiobutton(units_frame, text="Meters", value="meters",
                        variable=self.units_var).grid(row=0, column=1, padx=(0, 6))
        ttk.Radiobutton(units_frame, text="Feet", value="feet",
                        variable=self.units_var).grid(row=0, column=2, padx=(0, 6))
        ttk.Radiobutton(units_frame, text="Inches", value="inches",
                        variable=self.units_var).grid(row=0, column=3)

        # ============================================================
        # Z Height — SECOND ROW
        # ============================================================
        z_frame = ttk.Frame(editor_frame)
        z_frame.grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

        ttk.Label(z_frame, text="Z Height:").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(z_frame, textvariable=self.zheight_var, width=10).grid(row=0, column=1)

        self._zheight_wl_label = ttk.Label(z_frame, text="", foreground="#555555")
        self._zheight_wl_label.grid(row=0, column=2, padx=(8, 0))

        # ============================================================
        # Tag / X / Y / Z Editor Row — THIRD ROW
        # ============================================================
        app = self.winfo_toplevel()
        vcmd = app.float_vcmd

        ttk.Label(editor_frame, text="Tag").grid(row=2, column=0, sticky="e", padx=4, pady=4)
        self.tag_entry = ttk.Entry(editor_frame, textvariable=self.tag_var, width=8)
        self.tag_entry.grid(row=2, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(editor_frame, text="X").grid(row=2, column=2, sticky="e", padx=4, pady=4)
        self.x_entry = ttk.Entry(editor_frame, textvariable=self.x_var, width=12,
                                validate="key", validatecommand=vcmd)
        self.x_entry.grid(row=2, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(editor_frame, text="Y").grid(row=2, column=4, sticky="e", padx=4, pady=4)
        self.y_entry = ttk.Entry(editor_frame, textvariable=self.y_var, width=12,
                                validate="key", validatecommand=vcmd)
        self.y_entry.grid(row=2, column=5, sticky="w", padx=4, pady=4)

        ttk.Label(editor_frame, text="Z").grid(row=2, column=6, sticky="e", padx=4, pady=4)
        self.z_entry = ttk.Entry(editor_frame, textvariable=self.z_var, width=12,
                                validate="key", validatecommand=vcmd)
        self.z_entry.grid(row=2, column=7, sticky="w", padx=4, pady=4)

        # ============================================================
        # Buttons — FOURTH ROW
        # ============================================================
        btns = ttk.Frame(editor_frame)
        btns.grid(row=3, column=0, columnspan=8, pady=6)

        ttk.Button(btns, text="Add",    command=self._add_node).pack(side="left", padx=4)
        ttk.Button(btns, text="Apply",  command=self._apply_edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete", command=self._delete_node).pack(side="left", padx=4)

        # Keyboard shortcuts
        self.bind_all("<Control-n>", lambda e: self._add_node())
        self.bind_all("<Return>",    lambda e: self._apply_edit())
        self.bind_all("<Delete>",    lambda e: self._delete_node())

        self._reset_editor()

        # Initial load
        self.load_from_model()



    # ============================================================
    # Model → GUI
    # ============================================================
    def _update_zheight_wl_label(self):
        """Recompute and display zHeight / lambda next to the zHeight entry."""
        try:
            z    = float(self.zheight_var.get())
            # Read frequency from the live GUI var, not the model —
            # the model is only updated on save_to_model(), not on every keystroke.
            app  = self.master.master
            fmhz = float(app.globals_frame.fmin_var.get())
            if fmhz <= 0:
                self._zheight_wl_label.config(text="")
                return
            units = self.units_var.get().lower()
            if units == "feet":
                z_m = z * 0.3048
            elif units == "inches":
                z_m = z * 0.0254
            else:
                z_m = z          # meters
            wl = z_m / (300.0 / fmhz)
            self._zheight_wl_label.config(text=f"= {wl:.4f} λ")
        except (TypeError, ValueError, ZeroDivisionError):
            self._zheight_wl_label.config(text="")

    def _on_zheight_changed(self, *args):
        """Push zHeight entry into model and refresh preview immediately."""
        try:
            self.model.node_input_meta.zHeight = float(self.zheight_var.get())
            self.master.master.safe_redraw()
        except ValueError:
            pass
        self._update_zheight_wl_label()
        # Update zHeight warning in GlobalsFrame
        app = self.master.master
        if hasattr(app, 'globals_frame'):
            app.globals_frame._check_zheight_warning()

    def _on_units_changed(self, *args):
        """Push units change to model and recompute wire lengths in wavelengths."""
        self.model.node_input_meta.units = self.units_var.get()
        self._update_zheight_wl_label()
        app = self.master.master
        if hasattr(app, 'wires_frame'):
            app.wires_frame.load_from_model()

    def load_from_model(self):
        m = self.model

        # NodeInputMeta
        self.zheight_var.set(m.node_input_meta.zHeight)
        self.units_var.set(m.node_input_meta.units)

        # Clear table
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Load nodes
        for n in m.nodes:
            self.tree.insert(
                "", "end",
                values=(n.tag, n.x, n.y, n.z)
            )

        # Update preview
        self.master.master.safe_redraw()



    # ============================================================
    # GUI → Model
    # ============================================================
    def _apply_edit(self, new_node=False):
        """Apply editor values to model."""
        tag = self.tag_var.get().strip().upper()
        x   = float(self.x_var.get() or 0.0)
        y   = float(self.y_var.get() or 0.0)
        z   = float(self.z_var.get() or 0.0)

        #from neomom_model import Node

        if new_node:
            self.model.nodes.append(Node(tag, x, y, z))
        else:
            sel = self.tree.selection()
            if not sel:
                return
            idx = self.tree.index(sel[0])
            self.model.nodes[idx] = Node(tag, x, y, z)

        self.master.master.safe_redraw()
        self.load_from_model()

    def _add_node(self):
        """Add a new node using current editor values."""
        self._apply_edit(new_node=True)

        # Prefill editor for next node
        self.tag_var.set(self._next_tag())
        self.x_var.set("0.0")
        self.y_var.set("0.0")
        self.z_var.set("0.0")

        #self._apply_edit(new_node=True)
        self._reset_editor()

        self.master.master.safe_redraw()

        self.x_entry.focus_set()

    def _delete_node(self):
        """Delete selected node."""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.model.nodes[idx]

        self.master.master.safe_redraw()    
        self.load_from_model()

    # ============================================================
    # Selection handler
    # ============================================================
    def _on_select(self, event):
        """Load selected node into editor."""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        node = self.model.nodes[idx]

        self.tag_var.set(node.tag)
        self.x_var.set(str(node.x))
        self.y_var.set(str(node.y))
        self.z_var.set(str(node.z))

    # ============================================================
    # Helpers
    # ============================================================
    def _next_tag(self):
        """Return next available tag (A, B, C, ...)."""
        existing = {node.tag.upper() for node in self.model.nodes}
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if c not in existing:
                return c
        return "Z"  # fallback

# end NodesFrame

from neomom_model import Wire  # ← REQUIRED

# start WiresFrame
class WiresFrame(ttk.Frame):
    """
    Wires editor: Treeview on top, one-line editor on bottom.
    Segments are hidden from the GUI but passed as a placeholder (1)
    because the model requires them. Solver will auto-segment later.
    """

    def _reset_editor(self):
        """Prefill editor with next wire tag and default radius."""
        self.tag_var.set(self._next_tag())
        self.nodes_var.set("")
        self.radius_var.set("0.001")

    def save_to_model(self):
        try:
            m = self.model
            m.wires.clear()

            for row in self.tree.get_children():
                vals      = self.tree.item(row, "values")
                tag       = vals[0]
                node_tags = vals[1]
                radius    = vals[2]
                # vals[3] = length  (computed display value — ignored here)
                # vals[4] = wl      (computed display value — ignored here)
                segs      = int(vals[5]) if len(vals) > 5 else 1

                node_tags_list = [
                    nt.strip() for nt in str(node_tags).replace(",", " ").split()
                    if nt.strip()
                ]

                m.wires.append(Wire(
                    tag=str(tag),
                    node_tags=node_tags_list,
                    radius=float(radius),
                    segments=segs
                ))

        except Exception as e:
            messagebox.showerror("Invalid Wire Entry", str(e))
            return False

        return True




    def __init__(self, master, model, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.model = model

        print("WiresFrame instance:", id(self))

        # ------------------------------------------------------------
        # Configure GRID layout for this frame
        # ------------------------------------------------------------
        self.rowconfigure(0, weight=1)   # Treeview expands
        self.rowconfigure(1, weight=0)   # Editor stays visible
        self.columnconfigure(0, weight=1)

        # ------------------------------------------------------------
        # StringVars
        # ------------------------------------------------------------
        self.tag_var    = tk.StringVar()
        self.nodes_var  = tk.StringVar()   # comma OR space separated node tags
        self.radius_var = tk.StringVar()

        # ============================================================
        # TOP: Treeview
        # ============================================================
        self.tree = ttk.Treeview(
            self,
            columns=("tag", "nodes", "radius", "length", "wl"),
            show="headings",
            height=10,
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        self.tree.heading("tag",    text="Tag")
        self.tree.heading("nodes",  text="Node Tags")
        self.tree.heading("radius", text="Radius (m)")
        self.tree.heading("length", text="Length")
        self.tree.heading("wl",     text="Length (\u03bb)")

        self.tree.column("tag",    width=60,  anchor="center")
        self.tree.column("nodes",  width=150, anchor="center")
        self.tree.column("radius", width=80,  anchor="center")
        self.tree.column("length", width=90,  anchor="center")
        self.tree.column("wl",     width=90,  anchor="center")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ============================================================
        # BOTTOM: Editor panel (one-line layout)
        # ============================================================
        editor = ttk.LabelFrame(self, text="Wire Editor")
        editor.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))

        ttk.Label(editor, text="Tag").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.tag_entry = ttk.Entry(editor, textvariable=self.tag_var, width=8)
        self.tag_entry.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(editor, text="Node Tags").grid(row=0, column=2, sticky="e", padx=4, pady=4)
        self.nodes_entry = ttk.Entry(editor, textvariable=self.nodes_var, width=20)
        self.nodes_entry.grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(editor, text="Radius").grid(row=0, column=4, sticky="e", padx=4, pady=4)
        self.radius_entry = ttk.Entry(editor, textvariable=self.radius_var, width=12)
        self.radius_entry.grid(row=0, column=5, sticky="w", padx=4, pady=4)

        # Buttons
        btns = ttk.Frame(editor)
        btns.grid(row=1, column=0, columnspan=6, pady=6)

        ttk.Button(btns, text="Add",    command=self._add_wire).pack(side="left", padx=4)
        ttk.Button(btns, text="Apply",  command=self._apply_edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete", command=self._delete_wire).pack(side="left", padx=4)

        # Keyboard shortcuts
        self.bind_all("<Control-w>", lambda e: self._add_wire())
        self.bind_all("<Return>",    lambda e: self._apply_edit())
        self.bind_all("<Delete>",    lambda e: self._delete_wire())

        self._reset_editor()

        # Initial load
        self.load_from_model()

    # ============================================================
    # Model → GUI
    # ============================================================
    def load_from_model(self):
        m = self.model

        # Clear table
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Load wires
        for w in m.wires:
            node_tags_str = " ".join(w.node_tags)
            length = self._compute_wire_length(w)
            wl     = self._length_to_wavelengths(length)
            self.tree.insert(
                "", "end",
                values=(w.tag, node_tags_str, w.radius,
                        f"{length:.4f}", f"{wl:.4f}",
                        w.segments)     # segments hidden at index 5
            )

        # Update preview
        self.master.master.safe_redraw()




    # ============================================================
    # GUI → Model (with validation)
    # ============================================================

    def _apply_edit(self, new_wire=False):
        tag = self.tag_var.get().strip().upper()

        # Accept commas OR spaces
        raw = self.nodes_var.get().replace(",", " ").split()
        node_tags = [s.strip().upper() for s in raw if s.strip()]

        if len(node_tags) < 2:
            messagebox.showerror("Invalid Wire", "A wire must have at least TWO node tags.")
            return

        defined_nodes = {node.tag.upper() for node in self.model.nodes}
        undefined = [n for n in node_tags if n not in defined_nodes]
        if undefined:
            messagebox.showerror("Undefined Node Tags", f"Unknown: {', '.join(undefined)}")
            return False

        try:
            radius = float(self.radius_var.get())
        except ValueError:
            messagebox.showerror("Invalid Radius", "Radius must be numeric.")
            return

        segments = 1

        from neomom_model import Wire

        if new_wire:
            self.model.wires.append(Wire(tag, node_tags, radius, segments))
        else:
            sel = self.tree.selection()
            if not sel:
                return
            idx = self.tree.index(sel[0])
            self.model.wires[idx] = Wire(tag, node_tags, radius, segments)

        self.load_from_model()

        self.master.master.safe_redraw()

        return True

    def _add_wire(self):

        if self._apply_edit(new_wire=True):
            self._reset_editor()
            self.nodes_entry.focus_set()

        self.master.master.safe_redraw()
 

    def _delete_wire(self):
        """Delete selected wire."""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.model.wires[idx]
        self.load_from_model()
        self.master.master.safe_redraw()


    # ============================================================
    # Selection handler
    # ============================================================
    def _on_select(self, event):
        """Load selected wire into editor."""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        wire = self.model.wires[idx]

        self.tag_var.set(wire.tag)
        self.nodes_var.set(",".join(wire.node_tags))
        self.radius_var.set(str(wire.radius))

    # ============================================================
    # Helpers
    # ============================================================
    def _next_tag(self):
        """Return next available wire tag (W1, W2, W3...)."""
        existing = {wire.tag.upper() for wire in self.model.wires}

        i = 1
        while True:
            tag = f"W{i}"
            if tag not in existing:
                return tag
            i += 1

    # ============================================================
    # Length / wavelength helpers
    # ============================================================
    def _compute_wire_length(self, wire):
        """Total polyline length: sum of node-to-node segment distances."""
        node_lookup = {n.tag: n for n in self.model.nodes}
        total = 0.0
        tags = wire.node_tags
        for i in range(len(tags) - 1):
            n1 = node_lookup.get(tags[i])
            n2 = node_lookup.get(tags[i + 1])
            if n1 and n2:
                total += ((n2.x - n1.x) ** 2 +
                          (n2.y - n1.y) ** 2 +
                          (n2.z - n1.z) ** 2) ** 0.5
        return total

    def _length_to_wavelengths(self, length):
        """Convert length (model units) to wavelengths at fmin."""
        try:
            fmhz = float(self.model.frequency.fmin)
            if fmhz <= 0:
                return 0.0
            units = self.model.node_input_meta.units.lower()
            if units == "feet":
                length_m = length * 0.3048
            elif units == "inches":
                length_m = length * 0.0254
            else:
                length_m = length       # already meters
            return length_m / (300.0 / fmhz)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    # ============================================================
    # Required by MomNMLApp._on_tab_changed
    # ============================================================
    def refresh_radius_defaults(self):
        """Placeholder for compatibility with tab-change handler."""
        pass

#end class WiresFrame
# start ExcitationsFrame

from neomom_model import Excitation

class ExcitationsFrame(ttk.Frame):

    def save_to_model(self):
        try:
            m = self.model
            m.excitations.clear()

            for row in self.tree.get_children():
                wiretag, nodetag, volts, phase = self.tree.item(row, "values")

                m.excitations.append(Excitation(
                    wireTag=str(wiretag),
                    nodeTag=str(nodetag),
                    voltage=float(volts),
                    phase_deg=float(phase)
                ))

        except Exception as e:
            messagebox.showerror("Invalid Excitation Entry", str(e))
            return False

        return True




    def _autosize_columns(self, event=None):
        """Resize columns based on heading text AND cell contents."""
        font = tkfont.Font()

        for col in ("wireTag", "nodeTag", "voltage", "phase_deg"):
            # Measure heading text
            heading = self.tree.heading(col)["text"]
            heading_width = font.measure(heading)

            # Measure widest cell content
            max_cell_width = 0
            for item in self.tree.get_children():
                text = str(self.tree.set(item, col))
                w = font.measure(text)
                if w > max_cell_width:
                    max_cell_width = w

            # Pick the larger of heading or content
            width = max(heading_width, max_cell_width)

            # Add padding
            width += 24

            # Enforce minimum width
            if width < 80:
                width = 80

            self.tree.column(col, width=width, stretch=True)




    """
    Excitations editor: Treeview on top, one-line editor on bottom.
    Matches model fields: wireTag, nodeTag, voltage, phase_deg.
    """

    def __init__(self, master, model, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.model = model

        print("ExcitationsFrame instance:", id(self))

        # ------------------------------------------------------------
        # GRID layout
        # ------------------------------------------------------------
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)

        # ------------------------------------------------------------
        # StringVars
        # ------------------------------------------------------------
        self.wiretag_var = tk.StringVar()
        self.nodetag_var = tk.StringVar()
        self.voltage_var = tk.StringVar(value="1.0")
        self.phase_var   = tk.StringVar(value="0.0")

        # ============================================================
        # TOP: Treeview
        # ============================================================
        self.tree = ttk.Treeview(
            self,
            columns=("wireTag", "nodeTag", "voltage", "phase_deg"),
            #columns=("wireTag", "nodeTag", "volts", "phi(deg)"),

            show="headings",
            height=10,
        )

        # ADD THIS RIGHT HERE
        self.tree.bind("<Configure>", self._autosize_columns)      

        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        # self.tree.heading("wireTag",  text="WireTag")
        # self.tree.heading("nodeTag",  text="NodeTag")
        # self.tree.heading("voltage",  text="Voltage")
        # #self.tree.heading("phase_deg", text="Phase(deg)")
        # self.tree.heading("phase_deg", text="phi(deg)")

        self.tree.heading("wireTag",  text="wire")
        self.tree.heading("nodeTag",  text="node")
        self.tree.heading("voltage",  text="volts")
        #self.tree.heading("phase_deg", text="Phase(deg)")
        self.tree.heading("phase_deg", text="phase")

        self.tree.column("wireTag",   width=90, anchor="center")
        self.tree.column("nodeTag",   width=90, anchor="center")
        self.tree.column("voltage",   width=80, anchor="center")
        self.tree.column("phase_deg", width=90, anchor="center")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Enable proportional autosizing
        self.tree.bind("<Configure>", self._autosize_columns)        

        # ============================================================
        # WARNING BANNER (row 1) — shown after MAA import
        # ============================================================
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)

        self._warn_frame = tk.Frame(self, bg="#FFD700", relief="flat")
        self._warn_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 2))
        self._warn_frame.grid_remove()   # hidden by default

        warn_icon  = tk.Label(self._warn_frame, text="⚠", bg="#FFD700",
                              font=("TkDefaultFont", 13, "bold"), fg="#7a5000")
        warn_icon.pack(side="left", padx=(6, 2), pady=4)

        warn_text = (
            "MAA import: excitation is antenna-specific.\n"
            "Review the wires and nodes, then add a new excitation below.\n"
            "You may need to add a feed node to the driven wire first."
        )
        self._warn_label = tk.Label(self._warn_frame, text=warn_text,
                                    bg="#FFD700", fg="#3a2500",
                                    font=("TkDefaultFont", 9),
                                    justify="left", anchor="w")
        self._warn_label.pack(side="left", padx=(0, 8), pady=4, fill="x", expand=True)

        close_btn = tk.Button(self._warn_frame, text="✕", bg="#FFD700",
                              relief="flat", bd=0, fg="#7a5000",
                              font=("TkDefaultFont", 10, "bold"),
                              cursor="hand2",
                              command=self._dismiss_warning)
        close_btn.pack(side="right", padx=(0, 6), pady=4)

        # ============================================================
        # BOTTOM: Editor panel
        # ============================================================
        editor = ttk.LabelFrame(self, text="Excitation Editor")
        editor.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))

        ttk.Label(editor, text="Wire Tag").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.wiretag_entry = ttk.Entry(editor, textvariable=self.wiretag_var, width=10)
        self.wiretag_entry.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(editor, text="Node Tag").grid(row=0, column=2, sticky="e", padx=4, pady=4)
        self.nodetag_entry = ttk.Entry(editor, textvariable=self.nodetag_var, width=10)
        self.nodetag_entry.grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(editor, text="Voltage").grid(row=0, column=4, sticky="e", padx=4, pady=4)
        self.voltage_entry = ttk.Entry(editor, textvariable=self.voltage_var, width=10)
        self.voltage_entry.grid(row=0, column=5, sticky="w", padx=4, pady=4)

        ttk.Label(editor, text="Phase (deg)").grid(row=0, column=6, sticky="e", padx=4, pady=4)
        self.phase_entry = ttk.Entry(editor, textvariable=self.phase_var, width=10)
        self.phase_entry.grid(row=0, column=7, sticky="w", padx=4, pady=4)

        # Buttons
        btns = ttk.Frame(editor)
        btns.grid(row=1, column=0, columnspan=8, pady=6)

        ttk.Button(btns, text="Add",    command=self._add_exc).pack(side="left", padx=4)
        ttk.Button(btns, text="Apply",  command=self._apply_edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete", command=self._delete_exc).pack(side="left", padx=4)

        # Shortcuts
        self.bind_all("<Control-e>", lambda e: self._add_exc())
        self.bind_all("<Return>",    lambda e: self._apply_edit())
        self.bind_all("<Delete>",    lambda e: self._delete_exc())

        # Initial load
        self.load_from_model()

    # ============================================================
    # Warning banner helpers
    # ============================================================
    def show_maa_warning(self):
        """Show the yellow MAA import warning banner."""
        self._warn_frame.grid()

    def _dismiss_warning(self):
        """User clicked ✕ — hide the banner."""
        self._warn_frame.grid_remove()

    def _update_warning(self):
        """
        Hide the warning automatically once all excitations have
        both a wire tag and a node tag filled in.
        """
        if not self._warn_frame.winfo_ismapped():
            return   # already dismissed
        all_complete = (
            bool(self.model.excitations) and
            all(ex.wireTag and ex.nodeTag for ex in self.model.excitations)
        )
        if all_complete:
            self._warn_frame.grid_remove()

    # ============================================================
    # Model → GUI
    # ============================================================
    def load_from_model(self):
        m = self.model

        # Clear table
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Load excitations
        for ex in m.excitations:
            self.tree.insert(
                "", "end",
                values=(ex.wireTag, ex.nodeTag, ex.voltage, ex.phase_deg)
            )

        # Update preview
        self.master.master.safe_redraw()


 
    # ============================================================
    # GUI → Model (with validation)
    # ============================================================
    def _apply_edit(self, new_exc=False):
        wireTag = self.wiretag_var.get().strip().upper()
        nodeTag = self.nodetag_var.get().strip().upper()

        # Validate wire tag
        defined_wires = {wire.tag.upper() for wire in self.model.wires}
        if wireTag not in defined_wires:
            messagebox.showerror("Invalid Wire Tag", f"Wire tag '{wireTag}' does not exist.")
            return

        # Validate node tag
        defined_nodes = {node.tag.upper() for node in self.model.nodes}
        if nodeTag not in defined_nodes:
            messagebox.showerror("Invalid Node Tag", f"Node tag '{nodeTag}' does not exist.")
            return

        # Validate voltage
        try:
            voltage = float(self.voltage_var.get())
        except ValueError:
            messagebox.showerror("Invalid Voltage", "Voltage must be numeric.")
            return

        # Validate phase
        try:
            phase_deg = float(self.phase_var.get())
        except ValueError:
            messagebox.showerror("Invalid Phase", "Phase must be numeric.")
            return

        from neomom_model import Excitation

        if new_exc:
            self.model.excitations.append(Excitation(wireTag, nodeTag, voltage, phase_deg))
        else:
            sel = self.tree.selection()
            if not sel:
                return
            idx = self.tree.index(sel[0])
            self.model.excitations[idx] = Excitation(wireTag, nodeTag, voltage, phase_deg)
        
        self.master.master.safe_redraw()

        self.load_from_model()

    def _add_exc(self):
        self._apply_edit(new_exc=True)

        self.wiretag_var.set("")
        self.nodetag_var.set("")
        self.voltage_var.set("1.0")
        self.phase_var.set("0.0")

        self._update_warning()
        self.master.master.safe_redraw()
        self.wiretag_entry.focus_set()

    def _delete_exc(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.model.excitations[idx]
        self.master.master.safe_redraw()
        self.load_from_model()

    # ============================================================
    # Selection handler
    # ============================================================
    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        exc = self.model.excitations[idx]

        self.wiretag_var.set(exc.wireTag)
        self.nodetag_var.set(exc.nodeTag)
        self.voltage_var.set(str(exc.voltage))
        self.phase_var.set(str(exc.phase_deg))

# End ExcitationsFrame

# --- INSERT AFTER ExcitationsFrame class ---
# Start class GeometryPreviewFrame(ttk.Frame):
class GeometryPreviewFrame(ttk.Frame):

    
    def __init__(self, master, model):
        super().__init__(master)
        self.model = model

        # ---------------------------------------------------------
        # 1. Visibility toggles
        # ---------------------------------------------------------
        self.show_nodes = tk.BooleanVar(value=True)
        self.show_node_labels = tk.BooleanVar(value=True)
        self.show_wire_labels = tk.BooleanVar(value=True)
        self.show_excitation = tk.BooleanVar(value=True)
        self.show_ground = tk.BooleanVar(value=True)

        # ---------------------------------------------------------
        # 2. Toolbar at TOP (compact)
        # ---------------------------------------------------------
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", side="top", pady=2)

        ttk.Button(toolbar, text="Fit", command=self.fit_view).pack(side="left", padx=2)
        ttk.Button(toolbar, text="+", command=lambda: self._zoom(0.8)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="-", command=lambda: self._zoom(1.25)).pack(side="left", padx=2)

        # Visibility dropdown
        vis_btn = ttk.Menubutton(toolbar, text="Visibility")
        menu = tk.Menu(vis_btn, tearoff=0)
        menu.add_checkbutton(label="Nodes", variable=self.show_nodes, command=self._redraw)
        menu.add_checkbutton(label="Node Labels", variable=self.show_node_labels, command=self._redraw)
        menu.add_checkbutton(label="Wire Labels", variable=self.show_wire_labels, command=self._redraw)
        menu.add_checkbutton(label="Excitation", variable=self.show_excitation, command=self._redraw)
        menu.add_checkbutton(label="Ground Plane", variable=self.show_ground, command=self._redraw)
        vis_btn["menu"] = menu
        vis_btn.pack(side="left", padx=2)

        # ---------------------------------------------------------
        # 3. Matplotlib figure + canvas
        # ---------------------------------------------------------
        fig = Figure(figsize=(6, 6))
        self.ax = fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        # ---------------------------------------------------------
        # 4. SolidWorks-style mouse navigation
        # ---------------------------------------------------------

        # Disable Matplotlib default key handler
        try:
            self.canvas.mpl_disconnect(self.canvas.manager.key_press_handler_id)
        except:
            pass

        self._mouse_btn = None
        self._last_event = None

        # Store cids so update_geometry can cleanly disconnect and reconnect
        # only our handlers (preventing accumulation of matplotlib 3D handlers).
        self._cid_press   = self.canvas.mpl_connect("button_press_event",   self._on_mouse_press)
        self._cid_release = self.canvas.mpl_connect("button_release_event",  self._on_mouse_release)
        self._cid_move    = self.canvas.mpl_connect("motion_notify_event",   self._on_mouse_move)
        self._cid_scroll  = self.canvas.mpl_connect("scroll_event",          self._on_scroll)
        self._cid_dbl     = self.canvas.mpl_connect("button_press_event",    self._on_double_click)

        # Right-click context menu
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="Fit View", command=self.fit_view)
        self._context_menu.add_command(label="Reset Camera", command=lambda: self.ax.view_init(30, -60))
        self._context_menu.add_command(label="Center on Cursor", command=lambda: self._center_on_cursor(self._last_event))

        self._context_menu.add_separator()
        self._context_menu.add_command(label="Zoom In", command=lambda: self._zoom(0.8))
        self._context_menu.add_command(label="Zoom Out", command=lambda: self._zoom(1.25))

        self._context_menu.add_separator()
        self._context_menu.add_checkbutton(label="Nodes", variable=self.show_nodes, command=self._redraw)
        self._context_menu.add_checkbutton(label="Node Labels", variable=self.show_node_labels, command=self._redraw)
        self._context_menu.add_checkbutton(label="Wire Labels", variable=self.show_wire_labels, command=self._redraw)
        self._context_menu.add_checkbutton(label="Excitation", variable=self.show_excitation, command=self._redraw)
        self._context_menu.add_checkbutton(label="Ground Plane", variable=self.show_ground, command=self._redraw)

        # Bind right-click
        self.canvas_widget.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        # Save last event for "center on cursor"
        self._last_event = event
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()


    def _center_on_cursor(self, event):
        if event is None or event.x is None or event.y is None:
            return
        if event.inaxes != self.ax:
            return

        x, y = event.xdata, event.ydata
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()

        dx = (x - (xlim[0] + xlim[1]) / 2)
        dy = (y - (ylim[0] + ylim[1]) / 2)

        self.ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
        self.ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
        self.canvas.draw_idle()

    # ---------------------------------------------------------
    # Mouse event handlers
    # ---------------------------------------------------------

    def _on_mouse_press(self, event):
        # No inaxes guard — axis reference can be stale after clf/add_subplot
        self._mouse_btn = event.button
        self._last_event = event

    def _on_mouse_release(self, event):
        self._mouse_btn = None
        self._last_event = None

    def _on_mouse_move(self, event):
        if self._mouse_btn is None or self._last_event is None:
            return
        # No inaxes guard — on Windows TkAgg, event.inaxes can mismatch the
        # recreated axis and silently suppress rotation.  Guard with coords only.
        if event.x is None or event.y is None:
            return

        dx = event.x - self._last_event.x
        dy = event.y - self._last_event.y

        # --- Left button: rotate ---
        if self._mouse_btn == 1:
            self.ax.view_init(
                elev=self.ax.elev - dy * 0.5,
                azim=self.ax.azim - dx * 0.5
            )

        # --- Middle button: pan ---
        elif self._mouse_btn == 2:
            scale = 0.002
            self.ax.set_xlim(self.ax.get_xlim() - dx * scale)
            self.ax.set_ylim(self.ax.get_ylim() + dy * scale)

        # --- Right button: zoom ---
        elif self._mouse_btn == 3:
            factor = 1 + (dy * 0.01)
            self._zoom(factor)

        self._last_event = event
        # Use draw() not draw_idle(): on Windows TkAgg, draw_idle() is deferred
        # and axis tick labels don't reposition until the next Tkinter idle cycle,
        # making them appear frozen during drag.  draw() forces an immediate
        # synchronous render so all axis decorations update with every mouse event.
        self.canvas.draw()
        # Force Tkinter to flush pending paint events so the PhotoImage backing
        # the canvas widget is actually rendered to screen (mirrors what a manual
        # window resize does).
        self.canvas_widget.update_idletasks()

    def _on_scroll(self, event):
        factor = 0.9 if event.step > 0 else 1.1
        self._zoom(factor)

    def _on_double_click(self, event):
        if event.dblclick:
            if event.xdata is None or event.ydata is None:
                return
            x, y = event.xdata, event.ydata
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
            dx = (x - (xlim[0] + xlim[1]) / 2)
            dy = (y - (ylim[0] + ylim[1]) / 2)
            self.ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
            self.ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
            self.canvas.draw()

    # ---------------------------------------------------------
    # Redraw using last model
    # ---------------------------------------------------------
    def _redraw(self):
        if hasattr(self, "_last_model"):
            self.update_geometry(self._last_model)

    # ---------------------------------------------------------
    # Zoom
    # ---------------------------------------------------------
    def _zoom(self, factor):
        ax = self.ax
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        zlim = ax.get_zlim()

        def scale(lim):
            mid = (lim[0] + lim[1]) / 2
            half = (lim[1] - lim[0]) * factor / 2
            return (mid - half, mid + half)

        ax.set_xlim(scale(xlim))
        ax.set_ylim(scale(ylim))
        ax.set_zlim(scale(zlim))
        self.canvas.draw()

    # ---------------------------------------------------------
    # Fit view
    # ---------------------------------------------------------
    def fit_view(self):
        ax = self.ax
        ax.autoscale(enable=True, axis='both', tight=True)
        self.canvas.draw()

    # ---------------------------------------------------------
    # Main geometry update  (debounced)
    # ---------------------------------------------------------
    def update_geometry(self, model):
        """
        Debounced entry point — collapses rapid successive calls into one.

        Uses after_idle (not after(N)) so the actual draw runs *after* all
        pending Tkinter events have been processed — critically including the
        initial <Configure>/resize events that tell matplotlib the Toplevel
        window's true pixel size.

        Root cause of the "frozen tick labels" bug:
          The preview lives in a Toplevel(geometry="700x700").  When the
          frame is first created, winfo_width/height return 1 and matplotlib's
          FigureCanvasTkAgg hasn't received its <Configure> event yet, so
          Axes3D's internal pixel bounding-box is sized from the Figure's
          default figsize (e.g. 6x6 in = 600x600 px) rather than 700x700.
          Tick-label 2D positions are computed from that stale bbox and appear
          frozen until the user resizes the window (which fires <Configure>,
          re-syncs the bbox, and redraws).  after_idle defers our draw until
          the event queue is empty, so <Configure> always fires first.
        """
        self._pending_model = model
        if getattr(self, '_update_job', None) is not None:
            try:
                self.after_cancel(self._update_job)
            except Exception:
                pass
        self._update_job = self.after_idle(self._do_update_geometry)

    def _do_update_geometry(self):
        self._update_job = None
        model = getattr(self, '_pending_model', None)
        if model is None:
            return
        self._last_model = model

        # Belt-and-suspenders: if the figure's pixel size still doesn't match
        # the canvas widget (can happen if after_idle fired before the first
        # <Configure> in edge cases), sync it now.  This is the same operation
        # matplotlib's resize handler performs and ensures Axes3D's pixel bbox
        # is correct before we draw.
        try:
            _w = self.canvas_widget.winfo_width()
            _h = self.canvas_widget.winfo_height()
            _dpi = self.canvas.figure.dpi
            _fw = round(self.canvas.figure.get_figwidth()  * _dpi)
            _fh = round(self.canvas.figure.get_figheight() * _dpi)
            if _w > 1 and _h > 1 and (abs(_fw - _w) > 2 or abs(_fh - _h) > 2):
                self.canvas.figure.set_size_inches(_w / _dpi, _h / _dpi,
                                                   forward=False)
        except Exception:
            pass

        # Clearing strategy history:
        #   ax.cla()             → leaves ghost tick/axis labels (matplotlib 3D bug)
        #   clf()+add_subplot()  → Axes3D.__init__ re-registers its own
        #                          motion/press/release handlers AFTER our wipe,
        #                          so both sets run and labels freeze during rotation
        #
        # Fix: remove only the DATA artists (collections, lines, texts, patches)
        # and leave the Axes3D object — and its decorations — untouched.
        # No axis recreation → no handler accumulation → no frozen labels.

        elev = self.ax.elev
        azim = self.ax.azim

        for _c in list(self.ax.collections):
            _c.remove()
        for _l in list(self.ax.lines):
            _l.remove()
        for _t in list(self.ax.texts):
            _t.remove()
        for _p in list(self.ax.patches):
            _p.remove()

        self.ax.view_init(elev=elev, azim=azim)
        ax = self.ax

        # ---------------------------------------------------------
        # Nodes
        # ---------------------------------------------------------
        nodes = model.nodes
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        zs = [n.z for n in nodes]
        tags = [n.tag for n in nodes]

        if self.show_nodes.get():
            ax.scatter(xs, ys, zs, color="blue", s=40)

        if self.show_node_labels.get():
            for x, y, z, t in zip(xs, ys, zs, tags):
                ax.text(x, y, z, t, color="blue")

        # Build lookup for wires/excitations
        node_lookup = {n.tag: n for n in nodes}

        # ---------------------------------------------------------
        # Wires
        # ---------------------------------------------------------
        for w in model.wires:
            pts = []
            for nt in w.node_tags:
                node = node_lookup.get(nt)
                if node:
                    pts.append((node.x, node.y, node.z))

            if len(pts) >= 2:
                xs, ys, zs = zip(*pts)
                ax.plot(xs, ys, zs, color="black")

                if self.show_wire_labels.get():
                    mx = sum(xs) / len(xs)
                    my = sum(ys) / len(ys)
                    mz = sum(zs) / len(zs)
                    ax.text(mx, my, mz, w.tag, color="black")

        # ---------------------------------------------------------
        # Ground plane
        # ---------------------------------------------------------
        if self.show_ground.get() and model.ground.ground_type == "real":
            import numpy as np
            if nodes:
                size = max(
                    max(abs(n.x) for n in nodes),
                    max(abs(n.y) for n in nodes),
                ) * 1.2
            else:
                size = 1.0

            xx, yy = np.meshgrid(
                np.linspace(-size, size, 2),
                np.linspace(-size, size, 2)
            )
            zz = np.zeros_like(xx)
            ax.plot_surface(xx, yy, zz, alpha=0.2, color="green")

        # ---------------------------------------------------------
        # Excitation (first one only)
        # ---------------------------------------------------------
        if self.show_excitation.get() and model.excitations:
            ex = model.excitations[0]
            node = node_lookup.get(ex.nodeTag)
            if node:
                ax.scatter([node.x], [node.y], [node.z], color="red", s=120)
                ax.text(node.x, node.y, node.z,
                        f"EXC {ex.wireTag}/{ex.nodeTag}",
                        color="red")

        # ---------------------------------------------------------
        # Labels and title
        # ---------------------------------------------------------
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title("Antenna Geometry Preview")

        # Ground plane height legend
        try:
            zH = model.node_input_meta.zHeight
            #legend_text = f"Ground plane: z = 0\nAntenna height (zHeight): {zH}"
            legend_text = f"Antenna zHeight: {zH}"

            ax.text2D(0.02, 0.95, legend_text, transform=ax.transAxes,
                    fontsize=10, verticalalignment='top')
        except:
            pass

        self.canvas.draw()
        # Force Tkinter to flush the pending repaint so the canvas widget
        # actually shows the new Agg buffer — mirrors what a manual window
        # resize triggers.  Without this the old image can persist until the
        # next Tkinter event loop iteration.
        self.canvas_widget.update_idletasks()

#End:class GeometryPreviewFrame(ttk.Frame):

# Globals Frame start
class GlobalsFrame(ttk.Frame):

    def save_to_model(self):
        try:
            m = self.model

            # RunTitle
            m.run_title = self.title_var.get().strip()

            # FrequencyBlock
            m.frequency.fmin  = float(self.fmin_var.get())
            m.frequency.fmax  = float(self.fmax_var.get())
            # nFreq only used in pattern mode
            # VNA mode uses fstep — nFreq computed by engine
            mode = self.sweep_mode_var.get()
            if mode == 'vna_sweep':
                m.frequency.nFreq = 0      # signals: use fstep
                try:
                    m.frequency.fstep = float(self.fstep_var.get())
                except ValueError:
                    m.frequency.fstep = 0.010   # safe default
            else:
                # pattern mode
                try:
                    m.frequency.nFreq = int(self.nfreq_var.get())
                except ValueError:
                    m.frequency.nFreq = 1   # safe default
                m.frequency.fstep = 0.0
            m.options.sweep_mode = mode

            # GroundBlock
            m.ground.ground_type  = self.ground_type_var.get().strip().upper()
            m.ground.permittivity = float(self.epsilon_var.get())
            m.ground.conductivity = float(self.sigma_var.get())

            # OptionsBlock
            m.options.nBasisPerLambda = int(self.nbasis_var.get())
            m.options.output_currents = bool(self.output_currents_var.get())

        except Exception as e:
            messagebox.showerror("Invalid Globals Input", str(e))
            return False

        return True



    def _on_ground_type_changed(self, event=None):
        gtype = self.ground_type_var.get()

        if gtype == "real":
            # Enable fields
            self.epsilon_entry.configure(state="normal")
            self.sigma_entry.configure(state="normal")

            # Preload defaults if empty
            if not self.epsilon_var.get().strip():
                self.epsilon_var.set("14.0")
            if not self.sigma_var.get().strip():
                self.sigma_var.set("0.005")

        else:
            # Disable fields
            self.epsilon_entry.configure(state="disabled")
            self.sigma_entry.configure(state="disabled")

        self.master.master.safe_redraw()
        self._check_zheight_warning()

    def _on_start_freq_changed(self, event=None):
        """When user edits Start Frequency.
        Pattern mode: auto-fill Stop = Start, Steps = 1.
        VNA mode: just update point count, leave Stop alone.
        """
        try:
            fmin = float(self.fmin_var.get())
        except ValueError:
            return

        if self.sweep_mode_var.get() == 'pattern':
            self.fmax_var.set(str(fmin))
            self.nfreq_var.set("1")
        else:
            # VNA mode — update point count only
            self._update_point_count()

        # Update zHeight/lambda label in NodesFrame
        app = self.master.master
        if hasattr(app, 'nodes_frame'):
            app.nodes_frame._update_zheight_wl_label()

    def _on_stop_freq_changed(self, event=None):
        """When user edits Stop Frequency.
        Pattern mode: clear Steps.  VNA mode: update point count.
        """
        if self.sweep_mode_var.get() == 'pattern':
            self.nfreq_var.set("")
        else:
            self._update_point_count()


    def __init__(self, master, model, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.model = model

        # ------------------------------------------------------------
        # Tk Variables
        # ------------------------------------------------------------
        self.title_var = tk.StringVar()

        # Frequency (legacy NEC/MMANA format)
        self.fmin_var  = tk.StringVar()
        self.fmax_var  = tk.StringVar()
        self.nfreq_var      = tk.StringVar()
        self.fstep_var      = tk.StringVar(value='0.010')
        self.sweep_mode_var = tk.StringVar(value='pattern')  # 'pattern' or 'vna_sweep'
        self.launch_plot_var = tk.BooleanVar(value=True)

        # Ground
        self.ground_type_var = tk.StringVar()
        self.epsilon_var     = tk.StringVar()
        self.sigma_var       = tk.StringVar()

        # Options
        self.nbasis_var = tk.StringVar()
        self.output_currents_var = tk.BooleanVar(value=False)

        self._build_main()
        self.load_from_model()

    # ============================================================
    # BUILD UI
    # ============================================================
    def _build_main(self):

        app = self.winfo_toplevel()
        vcmd = app.float_vcmd

        # ------------------------------------------------------------
        # Run Title
        # ------------------------------------------------------------
        title_frame = ttk.LabelFrame(self, text="Run Title")
        title_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=6)

        ttk.Entry(title_frame, textvariable=self.title_var, width=40).grid(
            row=0, column=0, padx=6, pady=6, sticky="w"
        )

        # ------------------------------------------------------------
        # Frequency Block (legacy: fmin, fmax, nFreq)
        # ------------------------------------------------------------
        # ------------------------------------------------------------
        # Frequency Block (legacy: fmin, fmax, nFreq)
        # ------------------------------------------------------------

        # ── Frequency frame — Start/Stop plus sweep mode and controls ────
        freq_frame = ttk.LabelFrame(self, text="Frequency (MHz)")
        freq_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=6)

        # Row 0: Start / Stop
        ttk.Label(freq_frame, text="Start:").grid(row=0, column=0, padx=4, pady=4, sticky="e")
        fmin_entry = ttk.Entry(
            freq_frame,
            textvariable=self.fmin_var,
            width=10,
            validate="key",
            validatecommand=vcmd
        )
        fmin_entry.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        fmin_entry.bind("<KeyRelease>", self._on_start_freq_changed)

        ttk.Label(freq_frame, text="Stop:").grid(row=0, column=2, padx=4, pady=4, sticky="e")
        fmax_entry = ttk.Entry(
            freq_frame,
            textvariable=self.fmax_var,
            width=10,
            validate="key",
            validatecommand=vcmd
        )
        fmax_entry.grid(row=0, column=3, padx=4, pady=4, sticky="w")
        fmax_entry.bind("<KeyRelease>", self._on_stop_freq_changed)

        # Row 1: sweep mode radio buttons
        ttk.Label(freq_frame, text="Mode:").grid(row=1, column=0, padx=4, pady=(2,4), sticky="e")
        ttk.Radiobutton(freq_frame, text="Pattern Sweep",
                        variable=self.sweep_mode_var, value='pattern',
                        command=self._on_sweep_mode_changed).grid(
            row=1, column=1, columnspan=2, padx=4, pady=(2,4), sticky="w")
        ttk.Radiobutton(freq_frame, text="VNA Sweep",
                        variable=self.sweep_mode_var, value='vna_sweep',
                        command=self._on_sweep_mode_changed).grid(
            row=1, column=3, columnspan=2, padx=4, pady=(2,4), sticky="w")

        # Row 2: pattern sweep controls (Steps)
        self._pat_frame = ttk.Frame(freq_frame)
        self._pat_frame.grid(row=2, column=0, columnspan=6, sticky="ew", padx=4, pady=2)
        ttk.Label(self._pat_frame, text="Steps:").pack(side="left", padx=4)
        ttk.Entry(self._pat_frame, textvariable=self.nfreq_var,
                  width=6).pack(side="left", padx=4)
        ttk.Label(self._pat_frame,
                  text="(each step produces a separate _xxxMHz.csv)",
                  foreground="grey").pack(side="left", padx=8)

        # Row 2: VNA sweep controls (Step size + point count)
        self._vna_frame = ttk.Frame(freq_frame)
        self._vna_frame.grid(row=2, column=0, columnspan=6, sticky="ew", padx=4, pady=2)
        ttk.Label(self._vna_frame, text="Step size:").pack(side="left", padx=4)
        ttk.Entry(self._vna_frame, textvariable=self.fstep_var,
                  width=8).pack(side="left", padx=2)
        ttk.Label(self._vna_frame, text="MHz").pack(side="left")
        self._points_label = ttk.Label(self._vna_frame,
                                       text="→  — points",
                                       foreground="#1a6", width=16)
        self._points_label.pack(side="left", padx=8)

        # Traces for live point count — set AFTER _points_label exists
        self.fstep_var.trace_add('write', self._update_point_count)
        self.fmin_var.trace_add('write',  self._update_point_count)
        self.fmax_var.trace_add('write',  self._update_point_count)

        # ------------------------------------------------------------
        # Ground Block
        # ------------------------------------------------------------
        ground_frame = ttk.LabelFrame(self, text="Ground")
        ground_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=6)

        # --- Ground Type ---
        ttk.Label(ground_frame, text="Type:").grid(row=0, column=0, padx=4, pady=4, sticky="e")

        # ground_type_cb = ttk.Combobox(
        #     ground_frame,
        #     textvariable=self.ground_type_var,
        #     values=["free", "perfect", "real"],
        #     width=10,
        #     state="readonly",
        # )
        # ground_type_cb.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        # ground_type_cb.bind("<<ComboboxSelected>>", self._on_ground_type_changed)
        self.ground_type_cb = ttk.Combobox(
            ground_frame,
            textvariable=self.ground_type_var,
            values=["free", "perfect", "real"],
            width=10,
            state="readonly",
        )
        self.ground_type_cb.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self.ground_type_cb.bind("<<ComboboxSelected>>", self._on_ground_type_changed)


        # --- Epsilon ---
        ttk.Label(ground_frame, text="Epsilon:").grid(row=0, column=2, padx=4, pady=4, sticky="e")
        self.epsilon_entry = ttk.Entry(
            ground_frame,
            textvariable=self.epsilon_var,
            width=10,
            validate="key",
            validatecommand=vcmd,
        )
        self.epsilon_entry.grid(row=0, column=3, padx=4, pady=4, sticky="w")

        # --- Sigma ---
        ttk.Label(ground_frame, text="Sigma:").grid(row=0, column=4, padx=4, pady=4, sticky="e")
        self.sigma_entry = ttk.Entry(
            ground_frame,
            textvariable=self.sigma_var,
            width=10,
            validate="key",
            validatecommand=vcmd,
        )
        self.sigma_entry.grid(row=0, column=5, padx=4, pady=4, sticky="w")


        # ------------------------------------------------------------
        # Options Block
        # ------------------------------------------------------------
        opt_frame = ttk.LabelFrame(self, text="Solver Options")
        opt_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=6)

        ttk.Label(opt_frame, text="NBasisPerLambda:").grid(
            row=0, column=0, padx=4, pady=4, sticky="e"
        )
        ttk.Entry(opt_frame, textvariable=self.nbasis_var, width=10).grid(
            row=0, column=1, padx=4, pady=4, sticky="w"
        )

        # Output Currents stays in Options
        ttk.Label(opt_frame, text="Output Currents:").grid(
            row=0, column=2, padx=(16, 4), pady=4, sticky="e"
        )
        ttk.Radiobutton(opt_frame, text="Yes", value=True,
                        variable=self.output_currents_var).grid(
            row=0, column=3, padx=(0, 4), pady=4, sticky="w"
        )
        ttk.Radiobutton(opt_frame, text="No", value=False,
                        variable=self.output_currents_var).grid(
            row=0, column=4, padx=(0, 8), pady=4, sticky="w"
        )

        # ------------------------------------------------------------
        # Run Controls Frame — Launch plot only
        # ------------------------------------------------------------
        run_frame = ttk.LabelFrame(self, text="Run Controls")
        run_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=6)

        ttk.Label(run_frame, text="Launch plot:").grid(
            row=0, column=0, padx=4, pady=6, sticky="e")
        ttk.Radiobutton(run_frame, text="Yes",
                        variable=self.launch_plot_var, value=True).grid(
            row=0, column=1, padx=4, pady=6, sticky="w")
        ttk.Radiobutton(run_frame, text="No",
                        variable=self.launch_plot_var, value=False).grid(
            row=0, column=2, padx=4, pady=6, sticky="w")

        # Initialise sweep mode display
        self._on_sweep_mode_changed()

        # ------------------------------------------------------------
        # zHeight Warning Banner (row=4, hidden by default)
        # ------------------------------------------------------------
        self.columnconfigure(0, weight=1)

        self._zheight_warn_frame = tk.Frame(self, bg="#FFD700", relief="flat")
        self._zheight_warn_frame.grid(row=5, column=0, sticky="ew", padx=8, pady=(2, 2))
        self._zheight_warn_frame.grid_remove()   # hidden by default

        warn_icon = tk.Label(self._zheight_warn_frame, text="⚠", bg="#FFD700",
                             font=("TkDefaultFont", 13, "bold"), fg="#7a5000")
        warn_icon.pack(side="left", padx=(6, 2), pady=4)

        self._zheight_warn_label = tk.Label(
            self._zheight_warn_frame,
            text="zHeight = 0 with a non-free-space ground: nodes lie on the ground plane.\n"
                 "Set zHeight > 0 in the Nodes tab to raise the antenna above ground.",
            bg="#FFD700", fg="#3a2500",
            font=("TkDefaultFont", 9),
            justify="left", anchor="w"
        )
        self._zheight_warn_label.pack(side="left", padx=(0, 8), pady=4, fill="x", expand=True)

        close_btn = tk.Button(
            self._zheight_warn_frame, text="✕", bg="#FFD700",
            relief="flat", bd=0, fg="#7a5000",
            font=("TkDefaultFont", 10, "bold"),
            cursor="hand2",
            command=self._dismiss_zheight_warning
        )
        close_btn.pack(side="right", padx=(0, 6), pady=4)

    # ============================================================
    # zHeight WARNING HELPERS
    # ============================================================

    def _check_zheight_warning(self):
        """Show warning if zHeight == 0 and ground type is not free/free_space."""
        try:
            z = float(self.model.node_input_meta.zHeight)
        except (TypeError, ValueError):
            z = 0.0
        gtype = self.ground_type_var.get().strip().lower()
        if z == 0.0 and gtype not in ("free", "free_space", ""):
            self._zheight_warn_frame.grid()
        else:
            self._zheight_warn_frame.grid_remove()

    def _dismiss_zheight_warning(self):
        """User clicked \u2715 \u2014 hide the banner."""
        self._zheight_warn_frame.grid_remove()

    # ============================================================
    # LOAD FROM MODEL
    # ============================================================

    def load_from_model(self):
        m = self.model

        # RunTitle
        self.title_var.set(m.run_title)

        # FrequencyBlock
        self.fmin_var.set(m.frequency.fmin)
        self.fmax_var.set(m.frequency.fmax)
        self.nfreq_var.set(m.frequency.nFreq)
        self.fstep_var.set(m.frequency.fstep)
        self.sweep_mode_var.set(m.options.sweep_mode)
        self._on_sweep_mode_changed()

        # GroundBlock
        self.ground_type_var.set(m.ground.ground_type)
        self.epsilon_var.set(m.ground.permittivity)
        self.sigma_var.set(m.ground.conductivity)

        # OptionsBlock
        self.nbasis_var.set(m.options.nBasisPerLambda)
        self.output_currents_var.set(m.options.output_currents)

        # Apply correct enabled/disabled state to epsilon/sigma fields
        self._on_ground_type_changed()

        # Update preview
        self.master.master.safe_redraw()

        # Check zHeight warning after model load
        self._check_zheight_warning()

        # Update zHeight/lambda label in NodesFrame
        app = self.master.master
        if hasattr(app, 'nodes_frame'):
            app.nodes_frame._update_zheight_wl_label()



    # ============================================================
    # AUTO-FILL STOP + STEPS WHEN START CHANGES
    # ============================================================
    def _on_start_freq_changed(self, event=None):
        try:
            fmin = float(self.fmin_var.get())
        except ValueError:
            return

        # Auto-fill behavior (original NEC/MMANA style)
        self.fmax_var.set(str(fmin))
        self.nfreq_var.set("1")
        # Update zHeight/lambda label in NodesFrame
        app = self.master.master
        if hasattr(app, 'nodes_frame'):
            app.nodes_frame._update_zheight_wl_label()


    def _on_sweep_mode_changed(self):
        """Show/hide pattern vs VNA sweep controls."""
        mode = self.sweep_mode_var.get()
        if mode == 'vna_sweep':
            self._pat_frame.grid_remove()
            self._vna_frame.grid()
            self._update_point_count()
        else:
            self._vna_frame.grid_remove()
            self._pat_frame.grid()

    def _update_point_count(self, *args):
        """Recompute and display VNA sweep point count live."""
        try:
            fmin  = float(self.fmin_var.get())
            fmax  = float(self.fmax_var.get())
            fstep = float(self.fstep_var.get())
            if fstep > 0 and fmax > fmin:
                n = int(round((fmax - fmin) / fstep)) + 1
                self._points_label.config(text=f'→  {n} points')
            else:
                self._points_label.config(text='→  —')
        except (ValueError, ZeroDivisionError, AttributeError):
            try:
                self._points_label.config(text='→  —')
            except Exception:
                pass

# end class GlobalsFrame

class MomNMLApp(tk.Tk):


    def import_maa(self):
        path = filedialog.askopenfilename(
            title="Import MMANA-GAL .maa file",
            filetypes=[("MMANA-GAL files", "*.maa"), ("All files", "*.*")]
        )
        if not path:
            return

        self.load_maa_file(path)    

 

    def _on_tab_changed(self, event):
        tab = event.widget.nametowidget(event.widget.select())

        # If WiresFrame is now visible, refresh its defaults
        if isinstance(tab, WiresFrame):
            tab.refresh_radius_defaults()

    def show_preview_window(self):
        win = getattr(self, "_preview_win", None)

        # If window exists and is still alive, just lift it
        if win is not None and win.winfo_exists():
            win.lift()
            return

        # Otherwise create a new one
        win = tk.Toplevel(self)
        win.title("Geometry Preview")
        win.geometry("700x700")

        def on_close():
            self._preview_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        # Create preview frame inside floating window
        self.preview_frame = GeometryPreviewFrame(win, self.model)
        self.preview_frame.pack(fill="both", expand=True)

        self._preview_win = win

        # Force the Tkinter geometry manager to run its layout pass and
        # process the canvas widget's <Configure> event before we draw.
        # Without this, matplotlib's FigureCanvasTkAgg hasn't received its
        # <Configure> yet, so Axes3D's pixel bounding-box is computed from
        # the Figure's default figsize rather than the actual 700x700 window.
        # That causes tick-label positions to be frozen until the user
        # manually resizes.  update_idletasks() flushes layout/configure
        # idle events synchronously so the figure is correctly sized before
        # update_geometry schedules its draw.
        win.update_idletasks()

        # Draw immediately if model exists
        if hasattr(self, "model"):
            try:
                if self.preview_frame is not None:
                    self.preview_frame.update_geometry(self.model)
            except:
                pass


    def validate_current(self):
        if not self.collect_model_from_frames():
            return
        errors = validate_model(self.model)
        if errors:
            messagebox.showerror("Validation Errors", "\n".join(errors))
        else:
            messagebox.showinfo("Validation", "No errors detected.")
   
    def _find_default_solver(self, solver_dir):
        """
        Look for neomom.exe (Windows) or neomom (Linux/macOS) in order:
          1. Same directory as the .nml file
          2. Same directory as this script
          3. Anywhere on the system PATH
        Returns the full path string, or None if not found.
        """
        import platform
        import shutil

        exe = "neomom.exe" if platform.system() == "Windows" else "neomom"

        # 1. Alongside the .nml file
        candidate = os.path.join(solver_dir, exe)
        if os.path.isfile(candidate):
            return candidate

        # 2. Alongside this script
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            candidate  = os.path.join(script_dir, exe)
            if os.path.isfile(candidate):
                return candidate
        except NameError:
            pass   # __file__ not defined (e.g. frozen/interactive)

        # 3. System PATH
        found = shutil.which(exe)
        if found:
            return found

        return None

    def run_solver(self):
        import threading
        import subprocess

        if not self.collect_model_from_frames():
            return

        path = filedialog.asksaveasfilename(
            title="Save NML for Solver",
            defaultextension=".nml",
            filetypes=[("Namelist files", "*.nml"), ("All files", "*.*")]
        )
        if not path:
            return

        # Write the .nml file
        try:
            from nml_io import write_nml
            write_nml(self.model, path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write NML file:\n{e}")
            return

        # Resolve to absolute path so the solver sees a full path regardless of cwd
        abs_path   = os.path.abspath(path)
        solver_dir = os.path.dirname(abs_path)

        # Try default solver name first; fall back to file dialog if not found
        solver = self._find_default_solver(solver_dir)
        if not solver:
            solver = filedialog.askopenfilename(
                title="Select MoM Solver Executable",
                filetypes=[("Executable", "*.exe" if __import__("platform").system() == "Windows" else "*"),
                           ("All files", "*.*")]
            )
        if not solver:
            return

        # Queue: worker thread pushes lines; GUI thread drains into the text widget.
        # No files opened here, so there is no conflict with solver output files.
        q = queue.Queue()

        # Open the live output window -- it will drain the queue
        self._open_solver_output_window(q)

        # ---- build command with optional flags ----
        cmd = [solver, abs_path]

        gf = self.globals_frame

        # sweep mode
        if gf.sweep_mode_var.get() == 'vna_sweep':
            cmd.append('sweep=vna_sweep')

        # plot suppression
        if not gf.launch_plot_var.get():
            cmd.append('plot=.false.')

        # currents override — always pass so .nml value is overridden
        if gf.output_currents_var.get():
            cmd.append('currents=.true.')
        else:
            cmd.append('currents=.false.')

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=solver_dir,
                )
                for line in proc.stdout:
                    q.put(line)
                proc.wait()
            except Exception as e:
                q.put(f"\n[GUI] Failed to run solver:\n{e}\n")
            finally:
                q.put(None)   # sentinel -- solver is done

        threading.Thread(target=worker, daemon=True).start()


    def _open_solver_output_window(self, q):
        win = tk.Toplevel(self)
        win.title("Solver Output (live)")

        win.lift()
        win.focus_force()
        win.attributes('-topmost', True)
        win.after(300, lambda: win.attributes('-topmost', False))

        txt = tk.Text(win, wrap="word", width=100, height=40)
        txt.pack(fill="both", expand=True)

        txt.insert("end", "=== LIVE SOLVER OUTPUT ===\n\n")
        txt.config(state="disabled")

        self._solver_output_widget = txt

        # Start draining the queue into the text widget
        self._drain_solver_queue(q, txt)

    def _drain_solver_queue(self, q, text_widget):
        # Stop if the output window was closed
        try:
            if not text_widget.winfo_exists():
                return
        except Exception:
            return

        done = False
        lines_buf = []

        # Drain everything available right now (non-blocking)
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item is None:        # sentinel -- solver finished
                done = True
                break
            lines_buf.append(item)

        if lines_buf:
            text_widget.config(state="normal")
            text_widget.insert("end", "".join(lines_buf))
            text_widget.see("end")
            text_widget.config(state="disabled")

        if done:
            text_widget.config(state="normal")
            text_widget.insert("end", "\n=== SOLVER FINISHED ===\n")
            text_widget.config(state="disabled")
            return  # stop rescheduling

        # Reschedule until sentinel arrives or window closes
        self.after(100, lambda: self._drain_solver_queue(q, text_widget))

    def refresh_preview(self):
        if not self.collect_model_from_frames():
            return
        if hasattr(self, "preview_frame"):
            if self.preview_frame is not None:
                self.preview_frame.update_geometry(self.model)

    def set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def _validate_float(self, text):
        if text in ("", "-", ".", "-."):
            return True
        try:
            float(text)
            return True
        except ValueError:
            return False


    def _validate_float(self, text):
        # Allow empty or partial input
        if text in ("", "-", ".", "-."):
            return True
        try:
            float(text)
            return True
        except ValueError:
            return False


    def __init__(self, initial_file=None):
        super().__init__()
        self._initial_file = initial_file

        self.option_add("*Menu.font", ("Segoe UI", 10, "bold"))
        self.option_add("*Menu.activeBorderWidth", 2)
        self.option_add("*Menu.activeBackground", "#d0d7e5")

        # -----------------------------------------
        # Global UI styling (tabs, fonts, spacing)
        # -----------------------------------------
        style = ttk.Style()

        # Make sure theme supports tab styling
        style.theme_use("default")

        # Stronger tab appearance

        style.configure("TNotebook.Tab",
                        font=("Segoe UI", 11, "bold"),
                        padding=[20, 12],
                        foreground="#1A1A1A")

        style.map("TNotebook.Tab",
                background=[("selected", "#8faadc")],   # deeper blue
                foreground=[("selected", "#000000")])

        
        self.float_vcmd = (self.register(self._validate_float), "%P")
       
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status.pack(side="bottom", fill="x")

        # Float validator for numeric entry fields
        self.float_vcmd = (self.register(self._validate_float), "%P")

        # --------------------------------------------------------
        # HiDPI / DPI scaling
        # On Windows, the OS handles DPI scaling automatically —
        # applying manual tk scaling on top doubles the size.
        # On Linux we apply scaling based on screen resolution.
        #
        # Geometry is computed as a fraction of screen size so the
        # window fits correctly on both 1080p and 4K monitors without
        # hardcoded pixel values.
        # --------------------------------------------------------
        import platform
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        if platform.system() == "Windows":
            # Windows handles geometry scaling via OS DPI awareness.
            # tk scaling = 1.0 gives correct window size on 4K at 200%.
            # font_scale is set separately to get readable font sizes.
            scale      = 1.0      # controls tk scaling (window geometry)
            font_scale = 2.0      # controls font/row sizes independently
            self.tk.call('tk', 'scaling', scale)
        else:
            # Linux / macOS: reports physical pixels, manual scaling.
            if sw >= 3500 and sh >= 2000:
                scale = 2.5       # 4K physical (~3840x2160)
            elif sw >= 2500 and sh >= 1400:
                scale = 1.5       # 1440p physical (~2560x1440)
            else:
                scale = 1.2       # 1080p — no scaling, use native size
            font_scale = scale    # Linux: font and geometry scale together
            self.tk.call('tk', 'scaling', scale)

        # Store font_scale for use elsewhere
        self._font_scale = font_scale

        # Fix Treeview row height using font_scale
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=int(28 * font_scale))

        # HiDPI Treeview font tuning
        # Base font size 8 → scales to 20 on 4K
        base_size = 8
        tv_font = ("TkDefaultFont", int(base_size * font_scale))

        style.configure("Treeview", font=tv_font)
        style.configure("Treeview.Heading",
                        font=(tv_font[0], tv_font[1] + 1, "bold"))

        # Alternating row colors (zebra striping)
        style.map("Treeview", background=[("selected", "#347083")])

        style.configure("Treeview",
                        background="#ffffff",
                        foreground="black",
                        fieldbackground="#ffffff")

        style.configure("Treeview.Row", background="#ffffff")
        style.configure("Treeview.Alternate", background="#f0f0f0")

        style.configure("Hdr3.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Panel.TFrame", background="#f7f7f7")
        style.configure("Panel.TLabel", background="#f7f7f7")
        style.configure("Panel.TEntry", fieldbackground="#ffffff")



        self.title("Neo Wire MOM Input Editor")
        # Window geometry — computed as a fraction of screen size so
        # the window fits correctly on any monitor without hardcoded values.

        if platform.system() == "Windows":
            self.geometry("600x475")
        else:
            # Linux: size as fraction of screen — fits 1080p, 1440p and 4K
            # w = int(sw * 0.55)   # 55% of screen width  → 1056px on 1080p
            # h = int(sh * 0.75)   # 75% of screen height → 810px on 1080p
            w = int(sw * 0.35)   # 55% of screen width  → 1056px on 1080p
            h = int(sh * 0.45)   # 75% of screen height → 810px on 1080p            
            self.geometry(f"{w}x{h}")

        # if platform.system() == "Windows":
        #     # Windows reports logical pixels already scaled by OS.
        #     # Use a smaller logical size that Windows will scale up correctly.
        #     self.geometry("600x475")
        # else:
        #     # Linux: physical pixels — 65% width, 80% height of screen.
        #     # On 1080p: ~1248x864   On 4K: ~2496x1728 (then tk scale applies)
        #     w = int(sw * 0.65)
        #     h = int(sh * 0.80)
        #     self.geometry(f"{w}x{h}")

        # # --------------------------------------------------------
        # # HiDPI / DPI scaling
        # # On Windows, the OS handles DPI scaling automatically —
        # # applying manual tk scaling on top doubles the size.
        # # On Linux we apply scaling based on screen resolution.
        # # --------------------------------------------------------
        # import platform
        # sw = self.winfo_screenwidth()
        # sh = self.winfo_screenheight()

        # if platform.system() == "Windows":
        #     # Windows handles geometry scaling via OS DPI awareness.
        #     # tk scaling = 1.0 gives correct window size on 4K at 200%.
        #     # font_scale is set separately to get readable font sizes.
        #     scale      = 1.0      # controls tk scaling (window geometry)
        #     font_scale = 2.0      # controls font/row sizes independently
        #     self.tk.call('tk', 'scaling', scale)
        # else:
        #     # Linux / macOS: reports physical pixels, manual scaling.
        #     if sw >= 3500 and sh >= 2000:
        #         scale = 3.0       # 4K physical
        #     elif sw >= 2500 and sh >= 1400:
        #         scale = 1.75      # 1440p physical
        #     else:
        #         scale = 1.2       # 1080p baseline
        #     font_scale = scale    # Linux: font and geometry scale together
        #     self.tk.call('tk', 'scaling', scale)

        # # Store font_scale for use elsewhere
        # self._font_scale = font_scale

        # # Fix Treeview row height using font_scale
        # style = ttk.Style(self)
        # style.configure("Treeview", rowheight=int(28 * font_scale))

        # # HiDPI Treeview font tuning
        # # Base font size 8 → scales to 24 on 4K
        # base_size = 8
        # tv_font = ("TkDefaultFont", int(base_size * font_scale))

        # style.configure("Treeview", font=tv_font)
        # style.configure("Treeview.Heading",
        #                 font=(tv_font[0], tv_font[1] + 1, "bold"))


        # # Alternating row colors (zebra striping)
        # style.map("Treeview", background=[("selected", "#347083")])

        # style.configure("Treeview",
        #                 background="#ffffff",
        #                 foreground="black",
        #                 fieldbackground="#ffffff")

        # style.configure("Treeview.Row", background="#ffffff")
        # style.configure("Treeview.Alternate", background="#f0f0f0")

        # style.configure("Hdr3.TLabel", font=("Segoe UI", 10, "bold"))
        # style.configure("Panel.TFrame", background="#f7f7f7")
        # style.configure("Panel.TLabel", background="#f7f7f7")
        # style.configure("Panel.TEntry", fieldbackground="#ffffff")



        # self.title("Neo Wire MOM Input Editor")
        # # Window geometry — Windows reports logical pixels already scaled by OS,
        # # so use a smaller logical size that Windows will scale up correctly.
        # if platform.system() == "Windows":
        #     self.geometry("600x475")    # half of 1200x950 — OS doubles it to fill 4K
        # else:
        #     self.geometry("1200x950")   # Linux: physical pixels, full size

        #self.model = None
        self.model = NeoMoMModel()

        self._build_menu()
        self._build_main()

        self.show_preview_window()

        # If a file was supplied on the command line, load it after the
        # event loop starts (preview window must exist before update_geometry).
        if self._initial_file:
            self.after(0, self._load_initial_file)

    def _load_initial_file(self):
        """Called once, after the event loop starts, to load a command-line file."""
        path = self._initial_file
        ext  = os.path.splitext(path)[1].lower()
        if ext == ".maa":
            self.load_maa_file(path)
        elif ext == ".nml":
            # Reuse open_file logic without showing a dialog
            try:
                raw = parse_mom_nml(path)
                self.model = _dict_to_model(raw)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file:\n{e}")
                return
            self.globals_frame.model     = self.model
            self.nodes_frame.model       = self.model
            self.wires_frame.model       = self.model
            self.excitations_frame.model = self.model
            self.globals_frame.load_from_model()
            self.nodes_frame.load_from_model()
            self.wires_frame.load_from_model()
            self.excitations_frame.load_from_model()
            if self.preview_frame is not None:
                self.preview_frame.update_geometry(self.model)
            self.current_file = path
            self.title(f"Neo Wire MOM Input Editor - {os.path.basename(path)}")
        else:
            messagebox.showwarning(
                "Unknown file type",
                f"Cannot open '{os.path.basename(path)}'.\n"
                "Expected a .nml or .maa file."
            )

    def safe_redraw(self):
        """Redraw preview only if the preview window exists and is alive."""
        if (hasattr(self, "preview_frame")
                and self.preview_frame is not None
                and self.preview_frame.winfo_exists()):
            self.preview_frame._redraw()

    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New", command=self.new_file)
        filemenu.add_command(label="Open NML...", command=self.open_file)
        filemenu.add_command(label="Save As NML...", command=self.save_file_as)
        filemenu.add_command(label="Export as NEC (*.nec)...",   command=self.export_as_nec)
        filemenu.add_command(label="Export as MMANA (*.maa)...", command=self.export_as_maa)
        filemenu.add_separator()
        #filemenu.add_command(label="Import MMANA (*.maa)", command=self.load_maa_file)
        
        filemenu.add_command(label="Import MMANA (*.maa)", command=self.import_maa) 
        filemenu.add_separator()

        #Friday: 
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Show Preview Window", command=self.show_preview_window)
        #menubar.add_cascade(label="View", menu=view_menu)

        #view_menu = tk.Menu(menubar, tearoff=0)
        #view_menu.add_command(label="Show Preview Window", command=self.show_preview_window)
        #menubar.add_cascade(label="View", menu=view_menu)


        # --- INSERT BEFORE Quit ---
        filemenu.add_command(label="Validate", command=self.validate_current)

        filemenu.add_command(label="Run Solver...", command=self.run_solver)

        filemenu.add_command(label="Quit", command=self.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        menubar.add_cascade(label="View", menu=view_menu)

        self.config(menu=menubar)

        print("MomNMLApp model id:", id(self.model))

    def _build_main(self):

        # Create Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Shared structured model
        self.model = NeoMoMModel()

        # Preview frame is created as a floating Toplevel in show_preview_window()
        # Do NOT embed it in the main window here.
        self.preview_frame = None   # will be set by show_preview_window()

        # Create GUI frames (all share the same model)
        self.globals_frame = GlobalsFrame(self.notebook, self.model)
        self.nodes_frame = NodesFrame(self.notebook, self.model)
        self.wires_frame = WiresFrame(self.notebook, self.model)
        self.excitations_frame = ExcitationsFrame(self.notebook, self.model)

        # Add tabs
        self.notebook.add(self.globals_frame, text="Globals")
        self.notebook.add(self.nodes_frame, text="Nodes")
        self.notebook.add(self.wires_frame, text="Wires")
        self.notebook.add(self.excitations_frame, text="Excitations")

        # ⭐ Safe to initialize model contents now
        self.new_file()

        # Preview is initialized in show_preview_window() called from __init__
        

    def load_file(self, path=None):

        if path is None:
            path = filedialog.askopenfilename(
                filetypes=[("NML files", "*.nml"), ("All files", "*.*")]
            )
            if not path:
                return

        from nml_io import read_nml
        self.model = read_nml(path)

        # Push model → GUI
        self.globals_frame.load_from_model()
        self.nodes_frame.load_from_model()
        self.wires_frame.load_from_model()
        self.excitations_frame.load_from_model()

        # ⭐ Update preview after loading
        if self.preview_frame is not None:
            self.preview_frame.update_geometry(self.model)
        self.current_file = path

    # def collect_model_from_frames(self):

    #     ok = True
    #     ok = ok and self.globals_frame.save_to_model()
    #     ok = ok and self.nodes_frame.save_to_model()
    #     ok = ok and self.wires_frame.save_to_model()
    #     ok = ok and self.excitations_frame.save_to_model()

    #     if ok:
    #         # ⭐ Update preview after collecting changes
    #         self.preview_frame.update_geometry(self.model)
            

    #     return ok
    def collect_model_from_frames(self):

        ok = True
        ok = ok and self.globals_frame.save_to_model()
        ok = ok and self.nodes_frame.save_to_model()
        ok = ok and self.wires_frame.save_to_model()
        ok = ok and self.excitations_frame.save_to_model()

        if ok:
            # Update preview after collecting changes
            if self.preview_frame is not None:
                self.preview_frame.update_geometry(self.model)

        return ok


    def load_maa_file(self, path):
        """
        Load a MMANA-GAL *.maa file, convert to NeoMoMModel, load into GUI.
        """
        try:
            parsed     = parse_maa_file(path)
            raw        = wrap_maa_into_model(parsed)
            self.model = _dict_to_model(raw)
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import .maa file:\n{e}")
            return

        # Re-bind all frames to the new model
        self.globals_frame.model      = self.model
        self.nodes_frame.model        = self.model
        self.wires_frame.model        = self.model
        self.excitations_frame.model  = self.model

        # Push model → GUI
        self.globals_frame.load_from_model()
        self.nodes_frame.load_from_model()
        self.wires_frame.load_from_model()
        self.excitations_frame.load_from_model()

        # Warn user that MAA excitation needs to be set manually
        self.excitations_frame.show_maa_warning()

        # Update preview
        if self.preview_frame is not None:
            self.preview_frame.update_geometry(self.model)
        self.current_file = path
        self.title(f"Neo Wire MOM Input Editor - {os.path.basename(path)}")


    #start def new_file

    def new_file(self):
        self.model.reset()

        self.globals_frame.load_from_model()
        self.nodes_frame.load_from_model()
        self.wires_frame.load_from_model()
        self.excitations_frame.load_from_model()

        # ⭐ Update preview after model reset
        if self.preview_frame is not None:
            self.preview_frame.update_geometry(self.model)

    #end def new_file


    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open .nml file",
            filetypes=[("Namelist files", "*.nml"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            raw = parse_mom_nml(path)
            self.model = _dict_to_model(raw)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")
            return

        # Re-bind all frames to the new model object
        self.globals_frame.model      = self.model
        self.nodes_frame.model        = self.model
        self.wires_frame.model        = self.model
        self.excitations_frame.model  = self.model

        # Push model → GUI
        self.globals_frame.load_from_model()
        self.nodes_frame.load_from_model()
        self.wires_frame.load_from_model()
        self.excitations_frame.load_from_model()

        if self.preview_frame is not None:
            self.preview_frame.update_geometry(self.model)
        self.current_file = path
        self.title(f"Neo Wire MOM Input Editor - {os.path.basename(path)}")


    def export_as_nec(self):
        """
        Export the current model to a NEC-5 input file (*.nec).

        Pipeline:
          1. Collect GUI → model
          2. Write a temporary .nml via nml_io.write_nml
          3. Convert to NEC text via nml_to_nec.nml_to_nec()
             (this step adds zHeight to every node z-coordinate)
          4. Write the .nec text to the user-chosen path
          5. Delete the temporary .nml
        """
        import tempfile
        import importlib.util
        from pathlib import Path

        # Locate nml_to_nec.py — works both from source and inside a
        # PyInstaller bundle (sees sys._MEIPASS via _find_helper_py).
        _nml_to_nec_file = _find_helper_py('nml_to_nec.py')
        if _nml_to_nec_file is None:
            messagebox.showerror(
                "Import Error",
                "Cannot find nml_to_nec.py.\n\n"
                "Place nml_to_nec.py alongside neomom_input.py and retry."
            )
            return
        _spec = importlib.util.spec_from_file_location(
            '_nml_to_nec_module', str(_nml_to_nec_file)
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        nml_to_nec = _mod.nml_to_nec

        # 1. Collect GUI → model
        if not self.collect_model_from_frames():
            return

        # 2. Determine initial directory and suggested filename for the dialog.
        #    Use the directory of the currently open .nml file if known;
        #    otherwise fall back to the user home directory.
        current = getattr(self, 'current_file', None)
        if current:
            init_dir  = str(Path(current).parent)
            init_file = Path(current).stem + '.nec'
        else:
            init_dir  = str(Path.home())
            safe_title = (self.model.run_title or 'antenna').replace(' ', '_')
            init_file = safe_title + '.nec'

        nec_path = filedialog.asksaveasfilename(
            title="Export as NEC file",
            defaultextension=".nec",
            initialdir=init_dir,
            initialfile=init_file,
            filetypes=[("NEC input files", "*.nec"), ("All files", "*.*")],
        )
        if not nec_path:
            return

        # 3. Write model to a temporary .nml so nml_to_nec can parse it
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nml")
        os.close(tmp_fd)
        try:
            from nml_io import write_nml
            write_nml(self.model, tmp_path)

            # 4. Convert: nml_to_nec reads the 'units' field and scales
            #    ALL node coordinates AND wire radii to metres before
            #    writing GW cards — .nec output is always in metres.
            #    zHeight is also added to every node z-coordinate here.
            nec_text = nml_to_nec(tmp_path)

        except Exception as e:
            messagebox.showerror("Export Error", "Failed to generate NEC file:\n" + str(e))
            return
        finally:
            # 5. Always clean up the temp file
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        # 6. Write .nec output
        try:
            with open(nec_path, "w") as fh:
                fh.write(nec_text)
        except Exception as e:
            messagebox.showerror("Export Error", "Failed to write NEC file:" + str(e))
            return

        self.set_status(f"Exported NEC: {os.path.basename(nec_path)}")

    def export_as_maa(self):
        """
        Export the current model to a MMANA-GAL *.maa file.

        Uses the same safe importlib load as export_as_nec — no sys.path
        modification.  The converter (nml_to_maa.py) must live alongside
        neomom_input.py or one directory up.

        All coordinates are converted to metres and zHeight is applied
        before writing the MMANA wire geometry section.
        """
        import importlib.util
        import tempfile
        from pathlib import Path

        # Locate nml_to_maa.py — works both from source and inside a
        # PyInstaller bundle (sees sys._MEIPASS via _find_helper_py).
        _maa_file = _find_helper_py('nml_to_maa.py')
        if _maa_file is None:
            messagebox.showerror(
                "Import Error",
                "Cannot find nml_to_maa.py.\n\n"
                "Place nml_to_maa.py alongside neomom_input.py and retry."
            )
            return

        _spec = importlib.util.spec_from_file_location('_nml_to_maa_module', str(_maa_file))
        _mod  = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        nml_to_maa = _mod.nml_to_maa

        # Collect GUI -> model
        if not self.collect_model_from_frames():
            return

        # Build suggested filename and initial directory
        current = getattr(self, 'current_file', None)
        if current:
            init_dir  = str(Path(current).parent)
            init_file = Path(current).stem + '.maa'
        else:
            init_dir  = str(Path.home())
            safe_title = (self.model.run_title or 'antenna').replace(' ', '_')
            init_file = safe_title + '.maa'

        maa_path = filedialog.asksaveasfilename(
            title="Export as MMANA-GAL file",
            defaultextension=".maa",
            initialdir=init_dir,
            initialfile=init_file,
            filetypes=[("MMANA-GAL files", "*.maa"), ("All files", "*.*")],
        )
        if not maa_path:
            return

        # Write temp .nml, convert, clean up
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nml")
        os.close(tmp_fd)
        try:
            from nml_io import write_nml
            write_nml(self.model, tmp_path)

            # nml_to_maa converts all units to metres and applies zHeight
            maa_text = nml_to_maa(tmp_path)

        except Exception as e:
            messagebox.showerror("Export Error",
                                 "Failed to generate MAA file:\n" + str(e))
            return
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        try:
            with open(maa_path, 'w', encoding='ascii', errors='replace') as fh:
                fh.write(maa_text)
        except Exception as e:
            messagebox.showerror("Export Error",
                                 "Failed to write MAA file:\n" + str(e))
            return

        self.set_status(f"Exported MMANA: {os.path.basename(maa_path)}")

    def save_file_as(self):

        print("DEBUG save_file_as called on:", type(self))


        """Save the current model to a user-selected .nml file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".nml",
            filetypes=[("NML files", "*.nml"), ("All files", "*.*")]
        )
        if not path:
            return  # user cancelled

        try:
            # 1. Pull GUI → model
            self.collect_model_from_frames()

            # 2. Write using I/O subsystem
            from nml_io import write_nml
            write_nml(self.model, path)

            # 3. Update state
            self.current_file = path

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save NML file:\n{e}")



def main():
    import sys

    initial_file = None
    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        ext = os.path.splitext(candidate)[1].lower()
        if ext in (".nml", ".maa"):
            if os.path.isfile(candidate):
                initial_file = candidate
            else:
                print(f"Warning: file not found: {candidate}", file=sys.stderr)
        else:
            print(f"Warning: unrecognised extension '{ext}' — ignored.", file=sys.stderr)

    app = MomNMLApp(initial_file=initial_file)
    app.mainloop()


if __name__ == "__main__":
    main()