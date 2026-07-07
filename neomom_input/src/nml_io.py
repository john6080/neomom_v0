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
        # Frequency_MHz
        #
        # Pattern sweep (nFreq > 1, fstep = 0):
        #   fmin, fmax, nFreq — engine produces one _xxxMHz.csv per step
        #
        # VNA sweep (fstep > 0):
        #   fmin, fmax, fstep — engine computes nFreq automatically
        #   nFreq = 0 signals "use fstep"
        #   sweep_mode = 'vna_sweep' written to OPTIONS below
        # ============================================================
        freq = model.frequency

        w("&Frequency_MHz")
        w(f"   fmin  = {freq.fmin}")
        w(f"   fmax  = {freq.fmax}")
        if freq.fstep > 0.0:
            w(f"   fstep = {freq.fstep}")
            w(f"   nFreq = 0")        # 0 signals: use fstep
        else:
            w(f"   nFreq = {freq.nFreq}")
        w("/\n")

        # ============================================================
        # Ground
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

        w(f"   Ground_Plane = '{plane_out}'")
        w(f"   epsilon = {g.permittivity}")
        w(f"   sigma = {g.conductivity}")
        w("/\n")

        # ============================================================
        # OPTIONS
        # sweep_mode written only when not default ('pattern')
        # ============================================================
        opt = model.options
        currents_str = ".TRUE." if opt.output_currents else ".FALSE."
        w("&OPTIONS")
        w(f"   NBASISPERLAMBDA = {opt.nBasisPerLambda}")
        w(f"   Output_Currents = {currents_str}")
        if opt.sweep_mode != 'pattern':
            w(f"   sweep_mode = '{opt.sweep_mode}'")
        w("/\n")

        # ============================================================
        # node_input
        # ============================================================
        nodes = model.nodes
        meta  = model.node_input_meta

        w("&node_input")
        w(f"   zHeight = {meta.zHeight}")
        w(f"   nNodes = {len(nodes)}")
        w(f"   units = '{meta.units}'")
        w("")

        for i, node in enumerate(nodes, start=1):
            w(f" node_list({i}) = '{node.tag}', {node.x}, {node.y}, {node.z}")

        w("/\n")

        # ============================================================
        # wire_primitive
        # ============================================================
        for wpr in model.wires:
            node_tags_quoted = " ".join(f"'{t}'" for t in wpr.node_tags)
            w("&wire_primitive")
            w(f"   tag   = '{wpr.tag}',")
            w(f"   nNodes = {len(wpr.node_tags)},")
            w(f"   nodeTags = {node_tags_quoted}")
            w(f"   radius     = {wpr.radius}")
            w("/\n")

        # ============================================================
        # excitation_input
        # ============================================================
        for ex in model.excitations:
            w("&excitation_input")
            w(f"   wireTag = '{ex.wireTag}'")
            w(f"   nodeTag = '{ex.nodeTag}'")
            w(f"   voltage = {ex.voltage}")
            w(f"   phase_deg = {ex.phase_deg}")
            w("/\n")