from dataclasses import dataclass
import pathlib

# import sys
from . import BIDSError
from .extensions import EXTENSIONS_STR
from .ruleset import InheritanceWithinDir
from .ruleset import Ruleset


class BIDSEntity:
    # Two construction forms:
    # - BIDSEntity(["sub", "01"]): a single key-value list, as produced by splitting
    #   an underscore-separated filename token on "-". This form is fed from dataset
    #   filenames, so a wrongly-shaped list means a malformed BIDS file name rather
    #   than a programming error: it raises BIDSError, which is what
    #   BIDSFilePath.__init__ below expects to catch.
    # - BIDSEntity("sub", "01"): key and value as separate arguments. Only ever
    #   invoked programmatically, so bad input here is a TypeError.
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], list):
            if len(args[0]) != 2 or not all(isinstance(item, str) for item in args[0]):
                raise BIDSError(
                    f'Invalid construction of BIDSEntity class from "{args[0]}"'
                )
            self.key = args[0][0]
            self.value = args[0][1]
            return
        if len(args) != 2 or not all(isinstance(item, str) for item in args):
            raise TypeError(
                "Invalid construction of BIDSEntity class"
                f' from "{list(map(str, args))}"'
            )
        self.key = args[0]
        self.value = args[1]

    def __getitem__(self, index: int) -> str:
        if index == 0:
            return self.key
        if index == 1:
            return self.value
        assert False

    def __str__(self):
        return f"{self.key}-{self.value}"


class BIDSFilePath:

    # def __init__(self, root_dir: pathlib.Path, abspath: pathlib.Path):
    def __init__(self, *args):
        if len(args) == 2 and all(isinstance(item, pathlib.Path) for item in args):
            self.relpath = args[1].relative_to(args[0])
            self.stem = self.relpath.stem
            # For some reason, pathlib.PurePath.stem yields the file name
            #   excluding only the final suffix, not all of them;
            #   therefore remove suffixes iteratively until none left,
            #   as here want to use "stem" to refer to the string
            #   formed by the entities and suffix
            while pathlib.PurePath(self.stem).suffix:
                self.stem = pathlib.PurePath(self.stem).stem
            self.stem = str(self.stem)
            self.extension = "".join(self.relpath.suffixes)
            split_stem = self.stem.split("_")
            # The final underscore-separated token is the suffix, UNLESS it is
            #   itself an entity (contains a "-"), in which case the file has no
            #   suffix at all: its stem consists entirely of entities. This holds
            #   whether the stem is a single token (e.g. "sub-01") or several
            #   (e.g. "sub-01_ses-1"). Data files always carry a datatype suffix;
            #   only metadata files may have a suffixless stem, and only under
            #   rulesets that permit it (enforced downstream, not here).
            if "-" in split_stem[-1]:
                self.suffix = None
            elif len(split_stem) == 1:
                self.suffix = split_stem[0]
                split_stem = ""
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
            return
        if (
            len(args) == 4
            and isinstance(args[0], pathlib.Path)
            and isinstance(args[1], list)
            and all(isinstance(item, BIDSEntity) for item in args[1])
            and isinstance(args[2], (str, type(None)))
            and isinstance(args[3], str)
            and args[3].startswith(".")
        ):
            self.entities = args[1]
            self.suffix = args[2]
            self.extension = args[3]
            self.stem = (
                "_".join(map(str, self.entities))
                + ("_" if self.entities and self.suffix else "")
                + ("" if self.suffix is None else f"{self.suffix}")
            )
            self.relpath = args[0] / f"{self.stem}{self.extension}"
            return
        raise TypeError(f"Unrecognised initialisation of filepath.BIDSFilePath: {args}")

    def check(self, ruleset: Ruleset) -> None:
        # A data file must always carry a datatype suffix; a metadata file must
        #   too, unless the ruleset explicitly permits suffixless metadata files
        #   (compulsory_suffix == False).
        if self.suffix is None and (
            not self.is_metadata() or ruleset.compulsory_suffix
        ):
            raise BIDSError(
                f"BIDS {'metadata' if self.is_metadata() else 'data'} file"
                f" {self.relpath} lacks a required suffix"
                f" under ruleset {ruleset.name}"
            )

    def has_entity(self, key: str) -> bool:
        return any(entity[0] == key for entity in self.entities)

    def is_metadata(self) -> bool:
        return self.extension in EXTENSIONS_STR

    # TODO Define __bool__() that yields whether the relative path is valid
    #   Example: Parent directory has "sub-" or "ses-" but those are absent from entities
    # TODO Update any pieces of code that should be making use of this function
    #   Eg. Generating candidate paths for maximal exploitation of inheritance

    def __eq__(self, other: "BIDSFilePath") -> bool:
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
        # NB: pathlib's parents sequence does not support slicing before
        #   Python 3.10, so materialise it as a list before dropping the
        #   immediate parent (parents[0]).
        if self.relpath.parent in list(other.relpath.parents)[1:]:
            return True
        if other.relpath.parent in list(self.relpath.parents)[1:]:
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


class BIDSFilePathList(list[BIDSFilePath]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def has_unambiguous_nearest(self) -> bool:
        # The nearest (last, self[-1]) metadata file is unambiguously nearest if
        #   it is distinguishable from the second-nearest (self[-2]) by any of the
        #   within-directory __lt__ ordering keys: deeper in the filesystem,
        #   differing in suffix presence, or carrying more entities. Suffix
        #   presence is a genuine discriminator now that suffixless metadata files
        #   are possible (a suffixless file sorts before an otherwise-equal
        #   suffixed one). NB: both comparisons are against self[-1] (the nearest);
        #   the previous self[1] was a bug for lists of three or more files.
        return (
            len(self) == 1
            or len(self[-2].relpath.parents) < len(self[-1].relpath.parents)
            or bool(self[-2].suffix) != bool(self[-1].suffix)
            or len(self[-2].entities) < len(self[-1].entities)
        )

    def has_order_ambiguity(self, inheritance_within_dir: InheritanceWithinDir) -> bool:
        # Checking whether requirements relating to the number of /
        #   capability to unambiguously sort metadata files
        #   within each filesystem hierarchy level individually is satisfied
        if inheritance_within_dir == InheritanceWithinDir.any:
            return False
        # First, split the paths into different lists:
        #   the key dictating which list each entry goes into
        #   is based on the number of parents,
        #   which is an adequate proxy for unique directory of residence
        #   in this instance
        by_parent_count: dict[int, BIDSFilePathList] = {}
        for metafile in self:
            parent_count = len(metafile.relpath.parents)
            if parent_count in by_parent_count:
                by_parent_count[parent_count].append(metafile)
            else:
                by_parent_count[parent_count] = [metafile]
        if inheritance_within_dir == InheritanceWithinDir.unique:
            return any(len(item) > 1 for item in by_parent_count.values())
        assert inheritance_within_dir == InheritanceWithinDir.ordered
        for metafiles_within_dir in by_parent_count.values():
            if len(metafiles_within_dir) == 1:
                continue
            # Quick way to determine if any pair of metadata files
            #   contain the same number of entities:
            # Generate a set containing all of the unique filename entity counts,
            #   and make sure that there are as many counts as there are files
            # Two files at one filesystem level are unambiguously orderable if
            #   they differ in either suffix presence or entity count (the
            #   within-directory __lt__ ordering keys). Keying solely on entity
            #   count would spuriously flag a suffixless and a suffixed file of
            #   equal entity count as ambiguous, even though __lt__ orders them.
            if len(
                set(
                    (bool(metafile.suffix), len(metafile.entities))
                    for metafile in metafiles_within_dir
                )
            ) < len(metafiles_within_dir):
                return True
        return False

    def __eq__(self, ref: "BIDSFilePathList") -> bool:
        # Check for equivalency,
        #   which enforces equivalent ordering
        #   *except for* arbitrary ordering of ties
        if len(self) != len(ref):
            return False

        # Transform both lists into a form that is easier to test for equivalence
        #   given the prospect of ties
        # This needs to be:
        # - Indexed by tuple (# parents, # entities)
        # - Include index of first entry
        # - Include list of paths within that group
        @dataclass
        class Group:
            # (parent count, suffix present, entity count): entries sharing a
            #   depth are ties under __lt__ (arbitrary relative order). Suffix
            #   presence is part of the key because a suffixless file is ordered
            #   strictly before an otherwise-equal suffixed one, so the two must
            #   not be collapsed into a single order-agnostic tie group.
            depth: tuple[int, bool, int]
            index: int
            paths: BIDSFilePathList

        data_self: list[Group] = []
        data_ref: list[Group] = []
        for index, filepath in enumerate(self):
            parent_count: int = len(filepath.relpath.parents)
            suffix_present: bool = filepath.suffix is not None
            entity_count: int = len(filepath.entities)
            depth = (parent_count, suffix_present, entity_count)
            if data_self and depth == data_self[-1].depth:
                data_self[-1].paths.append(filepath)
            else:
                data_self.append(Group(depth, index, [filepath]))
        for index, filepath in enumerate(ref):
            parent_count: int = len(filepath.relpath.parents)
            suffix_present: bool = filepath.suffix is not None
            entity_count: int = len(filepath.entities)
            depth = (parent_count, suffix_present, entity_count)
            if data_ref and depth == data_ref[-1].depth:
                data_ref[-1].paths.append(filepath)
            else:
                data_ref.append(Group(depth, index, [filepath]))
        if len(data_self) != len(data_ref):
            return False
        for group_self, group_ref in zip(data_self, data_ref):
            if group_self.depth != group_ref.depth:
                return False
            if group_self.index != group_ref.index:
                return False
            if not all(
                path_self in group_ref.paths for path_self in group_self.paths
            ) or not all(path_ref in group_self.paths for path_ref in group_ref.paths):
                return False
        return True
