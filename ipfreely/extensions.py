from dataclasses import dataclass
from enum import Enum

InheritanceBehaviour = Enum("InheritanceBehaviour", "forbidden nearest merge")

EXTENSIONS_STR = [".bval", ".bvec", ".json", ".tsv"]

@dataclass
class MetafileExtension:
    extension: str
    inheritance_behaviour: InheritanceBehaviour
    is_numerical_matrix: bool


EXTENSIONS = {
    ".bval": MetafileExtension(".bval", InheritanceBehaviour.nearest, True),
    ".bvec": MetafileExtension(".bvec", InheritanceBehaviour.nearest, True),
    ".json": MetafileExtension(".json", InheritanceBehaviour.merge, False),
    ".tsv": MetafileExtension(".tsv", InheritanceBehaviour.forbidden, False),
}
