from enum import Enum

InheritanceBehaviour = Enum("InheritanceBehaviour", "forbidden nearest merge")

EXTENSIONS_STR = [".bval", ".bvec", ".json", ".tsv"]


class MetafileExtension:
    def __init__(self, extension: str, behaviour: InheritanceBehaviour):
        assert extension in EXTENSIONS_STR
        self.extension = extension
        self.behaviour = behaviour


EXTENSIONS = {
    ".bval": MetafileExtension(".bval", InheritanceBehaviour.nearest),
    ".bvec": MetafileExtension(".bvec", InheritanceBehaviour.nearest),
    ".json": MetafileExtension(".json", InheritanceBehaviour.merge),
    ".tsv": MetafileExtension(".tsv", InheritanceBehaviour.forbidden),
}
