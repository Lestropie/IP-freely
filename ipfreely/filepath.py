from dataclasses import dataclass
import os
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

    # Public attributes:
    # - relpath:   pathlib.Path, relative to the dataset root.
    # - pathstr:   str(relpath), cached at construction. This is the *identity key*
    #              of the class: __eq__, __hash__ and __str__ are all defined
    #              against it rather than against relpath.
    # - parentstr: str(relpath.parent), cached at construction. "." for a file at
    #              the dataset root, matching pathlib's rendering exactly, so it
    #              drops straight into the precomputed-string fast paths of
    #              utils.applicability.is_applicable().
    # - dirprefix: parentstr rendered as a *directory prefix* -- "" at the dataset
    #              root, otherwise parentstr plus the path separator. This is the
    #              ancestry key: directory A is an ancestor-or-self of directory B
    #              iff B.dirprefix.startswith(A.dirprefix), and a STRICT ancestor
    #              iff that holds and the two differ. The trailing separator is
    #              what makes the prefix test exact -- without it "sub-1" would
    #              spuriously prefix "sub-10". See __lt__.
    # - entitymap: {entity.key: entity.value}, cached at construction. Lossless
    #              because BOTH constructors reject duplicate entity keys, so the
    #              mapping has exactly one entry per element of `entities`.
    # - entityset: frozenset of the (key, value) pairs, cached at construction.
    #              Plain (str, str) tuples, NOT BIDSEntity objects -- BIDSEntity
    #              defines neither __eq__ nor __hash__, so a set of them would
    #              compare by identity and silently fail to deduplicate or match.
    #              This is the name-applicability key: metadata file M is
    #              name-applicable to data file D iff M.entityset <= D.entityset
    #              (plus the suffix rule); see utils.applicability.
    # - depth:     len(relpath.parents), i.e. the number of components of relpath.
    #              Equal to dirprefix.count(os.sep) + 1 because relpath is always
    #              relative (both constructors guarantee it) and pathlib-normalised
    #              (no trailing, doubled or "." components), and the file name
    #              itself contains no separator.
    #
    # Why cache it: instances are dict keys and set members throughout the export
    #   pipeline (Graph.m4d / Graph.d4m, ExportContext._applicable_cache, and the
    #   greedy candidates / rejected / remaining_set sets), so __hash__ and __eq__
    #   are the most frequently executed code in the tool -- over a million calls
    #   apiece for the greedy strategies. Delegating them to pathlib.PurePath costs
    #   a Python-level call into pathlib plus, for __eq__, an element-wise
    #   comparison of the cached _cparts tuples. Comparing one cached string
    #   instead is a single interpreter-level operation.
    #
    # Why this preserves the equivalence relation exactly: PurePath equality is
    #   equality of casefolded parts under an identical flavour. All instances here
    #   share the running platform's flavour, and on POSIX casefolding is the
    #   identity, so two relpaths are equal iff their parts are equal iff their
    #   string forms are equal -- str() being an unambiguous rendering of the parts
    #   for a fixed flavour. The two constructors below are obliged to agree on
    #   pathstr exactly, so that a parsed real file and a synthesised candidate
    #   denoting the same file remain equal and hash alike -- which the greedy
    #   exporter relies on when it matches candidates against data files. The
    #   parse-a-real-file form takes str(relpath) directly; the synthesise-a-
    #   candidate form reconstructs the same string without calling it (see the
    #   note there for why that is safe).
    #
    # def __init__(self, root_dir: pathlib.Path, abspath: pathlib.Path):
    def __init__(self, *args):
        if len(args) == 2 and all(isinstance(item, pathlib.Path) for item in args):
            self.relpath = args[1].relative_to(args[0])
            self.pathstr = str(self.relpath)
            # Derived from pathstr rather than from relpath.parent so that the two
            #   constructors cannot drift: a parsed real file and a synthesised
            #   candidate denoting the same file must agree on every ordering key,
            #   not merely on pathstr. rpartition finds the last separator; its
            #   absence means the file sits at the dataset root, where pathlib
            #   renders the parent as ".".
            head, sep, _ = self.pathstr.rpartition(os.sep)
            self.parentstr = head if sep else "."
            self.dirprefix = head + sep
            self.depth = self.dirprefix.count(os.sep) + 1
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
            # The key->value mapping doubles as the duplicate-key check: a dict
            #   comprehension keyed on entity.key collapses a repeated key, so a
            #   short mapping is exactly the "duplicate entities" condition that
            #   was previously tested with a separate set() of the keys. Building
            #   it here rather than testing and discarding it is what makes the
            #   mapping free.
            self.entitymap = {entity.key: entity.value for entity in self.entities}
            if len(self.entitymap) != len(self.entities):
                raise BIDSError(f"Duplicate entities in BIDS file {self.relpath}")
            self.entityset = frozenset(self.entitymap.items())
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
            # Same mapping, same duplicate-key rejection, as the parse-a-real-file
            #   branch above. Synthesising this branch's entity lists from the
            #   entities of an already-parsed data file (a powerset subset in
            #   _greedy.build_candidates, disjoint directory / non-directory
            #   groups in _tiered._candidate_metapaths) means a repeated key is
            #   unreachable in practice; the check is kept anyway so that
            #   `entitymap` and `entityset` are lossless renderings of `entities`
            #   for EVERY instance rather than only for parsed ones, which is the
            #   invariant utils.applicability relies on.
            self.entitymap = {entity.key: entity.value for entity in args[1]}
            if len(self.entitymap) != len(args[1]):
                raise BIDSError(f"Duplicate entities in BIDS file {args[1]}")
            self.entityset = frozenset(self.entitymap.items())
            self.suffix = args[2]
            self.extension = args[3]
            self.stem = (
                "_".join(map(str, self.entities))
                + ("_" if self.entities and self.suffix else "")
                + ("" if self.suffix is None else f"{self.suffix}")
            )
            name = f"{self.stem}{self.extension}"
            self.relpath = args[0] / name
            # Assemble the key by string concatenation rather than via
            #   str(self.relpath). This constructor is the hot one -- the greedy
            #   exporter runs it hundreds of thousands of times -- and
            #   PurePath.__str__ has to re-join the parsed parts on first access.
            #   str(args[0]) is memoised on the parent Path, and the same parent
            #   object is reused across every candidate synthesised for it, so
            #   this reduces to two string concatenations per candidate.
            # The result is identical to str(args[0] / name) for any relative
            #   parent: pathlib renders a parent of "." as no leading component
            #   at all, and otherwise joins with the flavour separator, which for
            #   the native pathlib.Path required here is os.sep. The endswith
            #   branch covers a root parent, whose rendering already ends in the
            #   separator.
            # dirprefix absorbs the three-way join: it is "" at the dataset root
            #   and otherwise ends in the separator, so pathstr is one
            #   concatenation and the ancestry key comes out for free.
            parent_str = str(args[0])
            self.parentstr = parent_str
            if parent_str == ".":
                self.dirprefix = ""
            elif parent_str.endswith(os.sep):
                self.dirprefix = parent_str
            else:
                self.dirprefix = parent_str + os.sep
            self.pathstr = self.dirprefix + name
            self.depth = self.dirprefix.count(os.sep) + 1
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
        # Equivalent to the previous any(entity[0] == key for entity in
        #   self.entities): entitymap has one entry per entity, keyed by
        #   entity.key, which is what BIDSEntity.__getitem__(0) returns.
        return key in self.entitymap

    def is_metadata(self) -> bool:
        return self.extension in EXTENSIONS_STR

    # TODO Define __bool__() that yields whether the relative path is valid
    #   Example: Parent directory has "sub-" or "ses-" but those are absent from entities
    # TODO Update any pieces of code that should be making use of this function
    #   Eg. Generating candidate paths for maximal exploitation of inheritance

    def __eq__(self, other: "BIDSFilePath") -> bool:
        # Compares the cached path key rather than relpath; see the class-level
        #   note above for why the two relations are identical. As before, this
        #   is duck-typed: comparison against a non-BIDSFilePath raises
        #   AttributeError rather than returning False or NotImplemented.
        return self.pathstr == other.pathstr

    def __hash__(self):
        # str hashes are memoised by CPython, so this is one cached lookup;
        #   it also avoids the Python-level call into pathlib.PurePath.__hash__.
        return hash(self.pathstr)

    def __lt__(self, other) -> bool:  # pylint: disable=too-many-return-statements
        # Define sorting function for parsed BIDS filesystem paths
        # This is not alphabetical, nor is it sorted by length:
        # - Starts at highest level of filesystem hierarchy (ie. root)
        # - Within a directory, ordered by # entities
        # - Hypothetically, to support proposals
        #   where metadata files don't need a suffix,
        #   anything that doesn't have a suffix
        #   should probably be before anything that does
        #
        # The hierarchy branches are expressed entirely on the cached dirprefix
        #   strings; no PurePath list is materialised and no PurePath is compared.
        #   The previous formulation asked whether self's parent directory appeared
        #   in list(other.relpath.parents)[1:] -- pathlib's parents sequence does
        #   not support slicing before Python 3.10, hence the list -- where the
        #   [1:] drops other's own immediate parent and so makes the test STRICT
        #   ancestry. Strictness is preserved here by requiring the two dirprefixes
        #   to differ before the prefix test is consulted: a file therefore does
        #   not sort before a sibling in its own directory by this branch, and
        #   falls through to the suffix / entity-count keys below exactly as before.
        # Why prefix testing is exact ancestry: dirprefix is the pathlib-normalised
        #   parent directory with a trailing separator ("" at the dataset root), so
        #   A is an ancestor-or-self directory of B iff B.dirprefix starts with
        #   A.dirprefix. The trailing separator is load-bearing -- comparing bare
        #   parent strings would let "sub-1" prefix "sub-10".
        self_dir = self.dirprefix
        other_dir = other.dirprefix
        if self_dir != other_dir:
            if other_dir.startswith(self_dir):
                return True
            if self_dir.startswith(other_dir):
                return False
            # Don't bother trying to find the first common parent;
            #   can just do an alphanumeric sort on the whole path,
            #   and the first distinguishing factor will be
            #   the first uncommon parent
            return self.pathstr < other.pathstr
        if self.suffix is None and other.suffix:
            return True
        if other.suffix is None and self.suffix:
            return False
        if len(self.entities) != len(other.entities):
            return len(self.entities) < len(other.entities)
        # Finally, resort to alphanumeric sorting
        return self.pathstr < other.pathstr

    def __str__(self) -> str:
        return self.pathstr

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
