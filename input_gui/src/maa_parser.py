# ================================================================
# MMANA-GAL *.maa Parser (ASCII-only, structure-based)
# Extracts: title, frequency, nodes, wires, excitations(raw)
# ================================================================

def parse_maa_sources(lines):
    """
    Parse MMANA excitation block.
    Preserve the raw MMANA tag exactly (e.g., 'w2b').
    User will convert this to node-based excitation in GUI.
    """
    sources = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("*"):
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue

        raw_tag = parts[0]      # e.g., "w2b"
        pos = parts[1]          # usually "0.0"
        v_real = parts[2]       # usually "1.0"
        v_imag = parts[3] if len(parts) > 3 else "0.0"

        sources.append({
            "wiretag": raw_tag,   # preserve EXACT MMANA tag
            "nodetag": "",        # user will fill this in
            "amp": v_real,
            "phase": v_imag
        })

    return sources



def parse_maa_file(path):
    """
    ASCII-only, structure-based MMANA parser.
    Extracts: title, frequency, nodes, wires, excitations(raw)
    """

    with open(path, "r", errors="ignore") as f:
        lines = [ln.strip() for ln in f.readlines()]

    title = lines[0].strip() if lines else ""

    # Frequency is always on line 3 in MMANA
    freq = None
    if len(lines) >= 3:
        try:
            freq = float(lines[2].replace(",", "."))
        except:
            freq = None

    nodes = []
    wires = []
    sources = []
    node_map = {}   # (x,y,z) -> tag

    # Ground defaults (free space until the G/H/M section is found)
    ground = {"type_code": 0, "height": 0.0}

    def get_node(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key in node_map:
            return node_map[key]
        tag = f"N{len(node_map)+1}"
        node_map[key] = tag
        nodes.append({"tag": tag, "x": x, "y": y, "z": z})
        return tag

    # ---------------------------------------------------------
    # MAIN PARSE LOOP
    # ---------------------------------------------------------
    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect ANY section header: * ... *
        if line.startswith("*") and line.endswith("*"):

            # -------------------------------------------------
            # WIRE BLOCK
            # -------------------------------------------------
            if i+1 < len(lines) and lines[i+1].strip().isdigit():
                wire_count = int(lines[i+1].strip())
                i += 2

                for _ in range(wire_count):
                    if i >= len(lines):
                        break
                    parts = [p for p in lines[i].replace(",", " ").split() if p]
                    if len(parts) >= 8:
                        x1, y1, z1 = map(float, parts[0:3])
                        x2, y2, z2 = map(float, parts[3:6])
                        radius = float(parts[6])
                        segs = int(parts[7])

                        n1 = get_node(x1, y1, z1)
                        n2 = get_node(x2, y2, z2)

                        wires.append({
                            "tag": f"W{len(wires)+1}",
                            "n1": n1,
                            "n2": n2,
                            "radius": radius,
                            "segs": segs
                        })
                    i += 1
                continue

            # -------------------------------------------------
            # G/H/M/R/AzEl/X  (ground + pattern parameters)
            # -------------------------------------------------
            # Header: *** G/H/M/R/AzEl/X ***
            # Data line (no count prefix):
            #   G, H, M, R, Az, El, X
            #   G: 0=free space, 1=perfect (PEC), 2=real ground
            #   H: antenna height AGL (metres) -> zHeight
            #   M: wire/material type code (ignored, default 0)
            #   R, Az, El, X: pattern parameters (ignored on import)
            #
            # Must be detected BEFORE the source-block check because the
            # data line starts with 0/1/2 which the source detector would
            # misread as a count line and silently skip the ground data.
            if "AzEl" in line or ("G/" in line and "H/" in line):
                if i + 1 < len(lines):
                    gparts = lines[i + 1].replace(",", " ").split()
                    if len(gparts) >= 2:
                        try:
                            ground["type_code"] = int(float(gparts[0]))
                            ground["height"]    = float(gparts[1])
                        except (ValueError, IndexError):
                            pass
                i += 2
                continue

            # -------------------------------------------------
            # SOURCE BLOCK (MMANA excitations)
            # -------------------------------------------------
            # Header: *** Source ***
            # Count/mode line: 1, 1
            # Data line: w2b, 0.0, 1.0
            #
            # Detected by: next line has 2+ tokens and first is a digit.
            if i+1 < len(lines):
                nxt = lines[i+1].replace(",", " ").split()
                if len(nxt) >= 2 and nxt[0].isdigit():
                    # Read until next *...*
                    src_lines = []
                    i += 2
                    while i < len(lines) and not (lines[i].startswith("*") and lines[i].endswith("*")):
                        src_lines.append(lines[i])
                        i += 1

                    # Parse raw MMANA excitations
                    sources.extend(parse_maa_sources(src_lines))
                    continue

        i += 1

    return {
        "title":     title,
        "frequency": freq,
        "nodes":     nodes,
        "wires":     wires,
        "sources":   sources,
        "ground":    ground,   # ground type + epsilon + sigma from G/H/M section
    }



# ================================================================
# WRAPPER: Convert parsed_maa → canonical GUI model
# ================================================================
def wrap_maa_into_model(parsed):
    """
    Convert minimal parsed_maa dict into the full canonical model
    used by the GUI (same structure as parsed .nml files).
    """

    title = parsed.get("title", "")
    freq = parsed.get("frequency", None)

    # Frequency block
    freq_block = {
        "fmin": freq,
        "fmax": freq,
        "nFreq": 1
    }

    # Ground block -- read from parsed G/H/M/R/AzEl/X section.
    # MMANA ground type codes: 0=free space, 1=perfect (PEC), 2=real ground.
    # Epsilon/sigma are not stored in the .maa format; use NeoMoM defaults.
    _gnd     = parsed.get("ground", {})
    _gtype   = _gnd.get("type_code", 0)
    _GND_MAP = {0: "free_space", 1: "perfect", 2: "real"}
    _gnd_str = _GND_MAP.get(_gtype, "free_space")
    _height  = _gnd.get("height", 0.0)
    ground_block = {
        "Ground_Plane": _gnd_str,
        "epsilon": "14.0"  if _gtype == 2 else "",
        "sigma":   "0.005" if _gtype == 2 else "",
    }

    # OPTIONS block (MMANA has none)
    options_block = {
        "NBASISPERLAMBDA": ""
    }

    # Node_input block  (H field from G/H/M/R/AzEl/X -> zHeight)
    node_input_block = {
        "meta": {
            "zheight": str(_height) if _height != 0.0 else "",
            "units": "meters",
            "nnodes": str(len(parsed.get("nodes", [])))
        },
        "nodes": parsed.get("nodes", [])
    }

    # ---------------------------------------------------------
    # NORMALIZE WIRES (MMANA → GUI format)
    # ---------------------------------------------------------
    wires_out = []
    for w in parsed.get("wires", []):
        n1 = w.get("n1")
        n2 = w.get("n2")
        node_tags = [n1, n2]

        wires_out.append({
            "tag": w.get("tag", "").upper(),
            "nNodes": len(node_tags),
            "nodeTags": node_tags,
            "radius": w.get("radius", "")
        })

    # ---------------------------------------------------------
    # EXCITATIONS (preserve MMANA tag, but uppercase it)
    # ---------------------------------------------------------
    excit_out = []
    for s in parsed.get("sources", []):
        raw = s.get("wiretag", "")
        excit_out.append({
            "wiretag": raw.upper(),   # <‑‑ UPPERCASE HERE
            "nodetag": "",            # user will fix
            "amp": s.get("amp", ""),
            "phase": s.get("phase", "")
        })


    return {
        "RunTitle": {"title": title},
        "Frequency_MHz": freq_block,
        "Ground": ground_block,
        "OPTIONS": options_block,
        "Node_input": node_input_block,
        "Wire_primitive": wires_out,
        "Excitation_input": excit_out
    }
