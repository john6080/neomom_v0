from neomom_model import NeoMoMModel, Node, Wire, Excitation, FrequencyBlock

NODE_COORD_DECIMALS = 6

def write_nml(model: NeoMoMModel, path: str):

    def w(line=""):
        f.write(line + "\n")

    def fmt_coord(v):
        return f"{v:.{NODE_COORD_DECIMALS}f}"

    with open(path, "w") as f:

        # ============================================================
        # RunTitle
        # ============================================================
        w(f"&RunTitle title = '{model.run_title}' /\n")

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

        if freq.fstep > 0.0:
            nfreq_part = "fstep = %s nFreq = 0" % freq.fstep   # 0 signals: use fstep
        else:
            nfreq_part = f"nFreq = {freq.nFreq}"
        w(f"&Frequency_MHz fmin = {freq.fmin} fmax = {freq.fmax} {nfreq_part} /\n")

        # ============================================================
        # Ground
        # ============================================================
        g = model.ground

        plane = g.ground_type.lower()
        if plane in ("free", "free_space"):
            plane_out = "free_space"
        elif plane == "perfect":
            plane_out = "perfect"
        else:
            plane_out = "real"

        w(f"&Ground Ground_Plane = '{plane_out}' epsilon = {g.permittivity} "
          f"sigma = {g.conductivity} /\n")

        # ============================================================
        # OPTIONS
        # sweep_mode written only when not default ('pattern')
        # ============================================================
        opt = model.options
        currents_str = ".TRUE." if opt.output_currents else ".FALSE."
        sweep_part = f" sweep_mode = '{opt.sweep_mode}'" if opt.sweep_mode != 'pattern' else ""
        w(f"&OPTIONS NBASISPERLAMBDA = {opt.nBasisPerLambda} "
          f"Output_Currents = {currents_str}{sweep_part} /\n")

        # ============================================================
        # node_input
        # One line per node ( tag, x, y, z ); numeric/tag columns are
        # padded so they line up across all node_list lines.
        # ============================================================
        nodes = model.nodes
        meta  = model.node_input_meta

        w(f"&node_input zHeight = {meta.zHeight} nNodes = {len(nodes)} units = '{meta.units}'")

        if nodes:
            idx_w  = len(str(len(nodes)))
            tags   = [f"'{node.tag}'" for node in nodes]
            xs     = [fmt_coord(node.x) for node in nodes]
            ys     = [fmt_coord(node.y) for node in nodes]
            zs     = [fmt_coord(node.z) for node in nodes]
            tag_w  = max(len(s) for s in tags)
            x_w    = max(len(s) for s in xs)
            y_w    = max(len(s) for s in ys)
            z_w    = max(len(s) for s in zs)

            for i, (tag, x, y, z) in enumerate(zip(tags, xs, ys, zs), start=1):
                idx = str(i).rjust(idx_w)
                w(f" node_list({idx}) = {tag.ljust(tag_w)}, {x.rjust(x_w)}, "
                  f"{y.rjust(y_w)}, {z.rjust(z_w)}")

        w("/\n")

        # ============================================================
        # wire_primitive
        # Each wire is its own namelist group (one line each); tag /
        # nNodes / nodeTags columns are padded so radius lines up as
        # the last column across all wire_primitive lines.
        # ============================================================
        wires = model.wires
        if wires:
            tags      = [f"'{wpr.tag}'" for wpr in wires]
            nnodes    = [str(len(wpr.node_tags)) for wpr in wires]
            nodetags  = [" ".join(f"'{t}'" for t in wpr.node_tags) for wpr in wires]
            radii     = [str(wpr.radius) for wpr in wires]
            tag_w     = max(len(s) for s in tags)
            nnodes_w  = max(len(s) for s in nnodes)
            nodetags_w = max(len(s) for s in nodetags)
            radius_w  = max(len(s) for s in radii)

            for tag, nn, nt, r in zip(tags, nnodes, nodetags, radii):
                w(f"&wire_primitive tag = {tag.ljust(tag_w)} nNodes = {nn.rjust(nnodes_w)} "
                  f"nodeTags = {nt.ljust(nodetags_w)} radius = {r.rjust(radius_w)} /\n")

        # ============================================================
        # excitation_input
        # ============================================================
        for ex in model.excitations:
            w(f"&excitation_input wireTag = '{ex.wireTag}' nodeTag = '{ex.nodeTag}' "
              f"voltage = {ex.voltage} phase_deg = {ex.phase_deg} /\n")