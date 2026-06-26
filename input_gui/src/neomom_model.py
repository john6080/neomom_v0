# neomom_model.py
# Structured data model for NeoMoM (Fortran-style architecture)

from dataclasses import dataclass, field
from typing import List

#from neomom_model import Node, WirePrimitive, Excitation

# ------------------------------------------------------------
# GLOBAL BLOCKS (Fortran-style derived types)
# ------------------------------------------------------------

@dataclass
class NodeInputMeta:
    zHeight: float = 0.0
    units: str = "meters"

@dataclass
class FrequencyBlock:
    fmin: float = 7.0
    fmax: float = 7.0
    nFreq: int = 1


@dataclass
class GroundBlock:
    ground_type: str = "free_space"  # free_space, perfect, real
    conductivity: float = 0.005
    permittivity: float = 14.0


@dataclass
class OptionsBlock:
    nBasisPerLambda: int = 40      # Fortran solver parameter


# ------------------------------------------------------------
# GEOMETRY BLOCKS
# ------------------------------------------------------------

@dataclass
class Node:
    tag: str        # string tag (A, B, C, AA, etc.)
    x: float
    y: float
    z: float


@dataclass
class Wire:
    tag: str                 # wire tag (w1, w2, w10b, etc.)
    node_tags: List[str]     # list of node tags (A, CC, D, E)
    radius: float
    segments: int


# ------------------------------------------------------------
# EXCITATION BLOCK (NeoMoM-accurate)
# ------------------------------------------------------------

@dataclass
class Excitation:
    wireTag: str             # which wire is excited
    nodeTag: str             # which node on that wire
    voltage: float = 1.0
    phase_deg: float = 0.0


# ------------------------------------------------------------
# TOP-LEVEL MODEL (Fortran-style TYPE :: NeoMoMModel)
# ------------------------------------------------------------

@dataclass
class NeoMoMModel:
    """Structured model for NeoMoM input, replacing loose dictionaries."""

    run_title: str = "Untitled NeoMoM Run"

    frequency: FrequencyBlock = field(default_factory=FrequencyBlock)
    ground: GroundBlock = field(default_factory=GroundBlock)
    options: OptionsBlock = field(default_factory=OptionsBlock)

    node_input_meta: NodeInputMeta = field(default_factory=NodeInputMeta)

    nodes: List[Node] = field(default_factory=list)
    wires: List[Wire] = field(default_factory=list)
    excitations: List[Excitation] = field(default_factory=list)
    # --------------------------------------------------------
    # Convenience methods (Fortran-style subroutines)
    # --------------------------------------------------------

    def add_node(self, tag: str, x: float, y: float, z: float):
        self.nodes.append(Node(tag, x, y, z))

    def add_wire(self, tag: str, node_tags: List[str], radius: float, segments: int):
        self.wires.append(Wire(tag, node_tags, radius, segments))

    def add_excitation(self, wireTag: str, nodeTag: str,
                       voltage: float = 1.0, phase_deg: float = 0.0):
        self.excitations.append(Excitation(wireTag, nodeTag, voltage, phase_deg))

    def clear_geometry(self):
        self.nodes.clear()
        self.wires.clear()

    def clear_excitations(self):
        self.excitations.clear()

    def reset(self):
        """Reset the entire model to defaults (Fortran-style reinitialization)."""
        self.__init__()