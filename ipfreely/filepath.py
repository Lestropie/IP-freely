import pathlib
from . import BIDSError
from .extensions import EXTENSIONS_STR
from .ruleset import Ruleset


class BIDSEntity:
    def __init__(self, *args):
        if len(args) == 1:
            if (
                not isinstance(args[0], list)
                or len(args[0]) != 2
                or not all(isinstance(item, str) for item in args[0])
            ):
                raise TypeError(
                    "Invalid construction of BIDSEntity class"
                    f' from "{list(map(str, *args))}"'
                )
            self.key = args[0][0]
            self.value = args[0][1]
            return
        if len(args) != 2 or all(isinstance(item, str) for item in args):
            raise TypeError(
                "Invalid construction of BIDSEntity class"
                f' from "{list(map(str, *args))}"'
            )
        self.key = args[0]
        self.key = args[1]

    def __getitem__(self, index: int) -> str:
        if index == 0:
            return self.key
        if index == 1:
            return self.value
        assert False

    def __str__(self):
        return f"{self.key}-{self.value}"


class BIDSFilePath:

    def __init__(self, root_dir: pathlib.Path, abspath: pathlib.Path):
        self.relpath = abspath.relative_to(root_dir)
        self.stem = self.relpath.stem
        # For some reason, pathlib.PurePath.stem yields the file name
        #   excluding only the final suffix, not all of them;
        #   therefore remove suffixes iteratively until none left,
        #   as here want to use "stem" to refer to the string
        #   formed by the entities and suffix
        while pathlib.PurePath(self.stem).suffix:
            self.stem = pathlib.PurePath(self.stem).stem
        self.extension = "".join(self.relpath.suffixes)
        split_stem = self.stem.split("_")
        if "-" in split_stem[-1]:
            self.suffix = None
        else:
            self.suffix = split_stem[-1]
            split_stem = split_stem[:-1]
        try:
            self.entities = [BIDSEntity(kv.split("-")) for kv in split_stem]
        except BIDSError as e:
            raise BIDSError(
                f"Malformed entity structure in BIDS file {self.relpath}"
            ) from e
        if len(set(entity.key for entity in self.entities)) != len(self.entities):
            raise BIDSError(f"Duplicate entities in BIDS file {self.relpath}")

    def check(self, ruleset: Ruleset) -> None:
        if ruleset.compulsory_suffix and self.suffix is None:
            raise BIDSError(f"Absent suffix in BIDS file {self.relpath}")

    def has_entity(self, key: str) -> bool:
        return any(entity[0] == key for entity in self.entities)

    def is_metadata(self) -> bool:
        return self.extension in EXTENSIONS_STR

    def __eq__(self, other) -> bool:
        return self.relpath == other.relpath

    def __hash__(self):
        return self.relpath.__hash__()

    def __lt__(self, other) -> bool:  # pylint: disable=too-many-return-statements
        # Define sorting function for parsed BIDS filesystem paths
        # This is not alphabetical, nor is it sorted by length:
        # - Starts at highest level of filesystem hierarchy (ie. root)
        # - Within a directory, ordered by # entities
        # - Hypothetically, to support proposals
        #   where metadata files don't need a suffix,
        #   anything that doesn't have a suffix
        #   should probably be before anything that does
        if self.relpath.parent in other.relpath.parents[1:]:
            return True
        if other.relpath.parent in self.relpath.parents[1:]:
            return False
        if self.relpath.parent != other.relpath.parent:
            # Don't bother trying to find the first common parent;
            #   can just do an alphanumeric sort on the whole path,
            #   and the first distinguishing factor will be
            #   the first uncommon parent
            return str(self) < str(other)
        if self.suffix is None and other.suffix:
            return True
        if other.suffix is None and self.suffix:
            return False
        if len(self.entities) != len(other.entities):
            return len(self.entities) < len(other.entities)
        # Finally, resort to alphanumeric sorting
        return str(self) < str(other)

    def __str__(self) -> str:
        return str(self.relpath)

    def __format__(self, format_spec) -> str:
        return self.relpath.__format__(format_spec)


def sort(files: list[BIDSFilePath]) -> list[BIDSFilePath]:
    def first(one: BIDSFilePath, two: BIDSFilePath) -> bool:
        if two.filepath.parent.is_relative_to(one.filepath.parent):
            return True
        if one.filepath.parent.is_relative_to(two.filepath.parent):
            return False
        return len(one.entities) < len(two.entities)

    return sorted(files, key=first)
