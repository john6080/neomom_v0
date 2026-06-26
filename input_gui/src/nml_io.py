from neomom_model import NeoMoMModel, Node, Wire, Excitation, FrequencyBlock

def write_nml(model: NeoMoMModel, path: str):

    def w(line=""):
        f.write(line + "\n")

    with open(path, "w") as f:

        # ============================================================
        # RunTitle
        # ============================================================
        w("&RunTitle")
        w(f"   title = '{model.run_title}'")
        w("/\n")

        # ============================================================
        # Frequency_MHz  (LEGACY FORMAT)
        # ============================================================
        freq = model.frequency

        w("&Frequency_MHz")
        w(f"   fmin  = {freq.fmin}")
        w(f"   fmax  = {freq.fmax}")
        w(f"   nFreq = {freq.nFreq}")
        w("/\n")

        # ============================================================
        # Ground (legacy names)
        # ============================================================
        g = model.ground
        w("&Ground")

        plane = g.ground_type.lower()
        if plane in ("free", "free_space"):
            plane_out = "free_space"
        elif plane == "perfect":
            plane_out = "perfect"
        else:
            plane_out = "real"

        w(f"   Ground_Plane = {plane_out}")
        w(f"   epsilon = {g.permittivity}")
        w(f"   sigma = {g.conductivity}")
        w("/\n")

        # ============================================================
        # OPTIONS (legacy name)
        # ============================================================
        opt = model.options
        w("&OPTIONS")
        w(f"   NBASISPERLAMBDA = {opt.nBasisPerLambda}")
        w("/\n")

        # ============================================================
        # node_input (legacy format)
        # ============================================================
        nodes = model.nodes
        meta = model.node_input_meta  # you still have this in your model

        w("&node_input")
        w(f"   zHeight = {meta.zHeight}")
        w(f"   nNodes = {len(nodes)}")
        w(f"   units = {meta.units}")
        w("")

        for i, node in enumerate(nodes, start=1):
            w(f" node_list({i}) = {node.tag}, {node.x}, {node.y}, {node.z}")

        w("/\n")

        # ============================================================
        # wire_primitive (legacy format)
        # ============================================================
        for wpr in model.wires:
            w("&wire_primitive")
            w(f"   tag   = {wpr.tag},")
            w(f"   nNodes = {len(wpr.node_tags)},")
            w(f"   nodeTags = {' '.join(wpr.node_tags)}")
            w(f"   radius     = {wpr.radius}")
            w("/\n")

        # ============================================================
        # excitation_input (legacy format)
        # ============================================================
        for ex in model.excitations:
            w("&excitation_input")
            w(f"   wireTag = {ex.wireTag}")
            w(f"   nodeTag = {ex.nodeTag}")
            w(f"   voltage = {ex.voltage}")
            w(f"   phase_deg = {ex.phase_deg}")
            w("/\n")