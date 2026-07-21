# from cProfile import Profile
# from pstats import SortKey, Stats

import csv
import json
from itertools import chain, combinations
import logging
import pathlib
import shutil

# import sys
import numpy

from ipfreely.extensions import EXTENSIONS
from ipfreely.filepath import BIDSFilePath
from ipfreely.filepath import BIDSFilePathList
from ipfreely.ruleset import Ruleset
from ipfreely.utils.applicability import is_applicable

logger = logging.getLogger(__name__)


COPY_UNMODIFIED = [
    "code",
    # "dataset_description.json",
    # "derivatives",
    "participants.json",
    "participants.tsv",
    "phenotype",
    "samples.json",
    "samples.tsv",
    "sourcedata",
    # "README.md",
    # "README.rst",
    # "README.txt"
]


CONVERSION_RULESETS = ["forbidden", "I1195", "PR1003", "1.1.x", "1.7.x", "1.11.x"]


def export_forbidden(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:

    for datapath, by_extension in metadata.items():
        parent = out_dir / datapath.relpath.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)
        for extension, content in by_extension.items():
            fullpath = out_dir / datapath.relpath.parent / f"{datapath.stem}{extension}"
            with open(fullpath, "w", encoding="utf-8") as f:
                if EXTENSIONS[extension].is_numerical_matrix:
                    numpy.savetxt(f, numpy.array(content))
                else:
                    if extension == ".json":
                        json.dump(content, f, indent=4, sort_keys=True)
                    elif extension == ".tsv":
                        for row in content:
                            f.write("\t".join(row) + "\n")
                    else:
                        assert False


def export_I1195(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:

    if True:  # profiling disabled: with Profile() as profile:

        for datapath, by_extension in metadata.items():
            parent = out_dir / datapath.relpath.parent
            if not parent.exists():
                parent.mkdir(parents=True)
            shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)

        # Precompute, once per data file, the hashed set of its ancestor-directory
        #   strings. relpath.parents includes the immediate parent as parents[0],
        #   so this covers the same-directory case exactly. Threaded into
        #   is_applicable() below to replace per-call pathlib.parents iteration.
        parent_sets: dict[BIDSFilePath, "frozenset[str]"] = {
            datapath: frozenset(map(str, datapath.relpath.parents))
            for datapath in metadata
        }

        # Index data files for candidate-eligibility lookup (optimisation (c)).
        #   A candidate metadata path with suffix S (non-None) and entities E can
        #   only be *name*-applicable to a data file whose suffix equals S and whose
        #   entity key-values are a superset of E (equal values); the candidate's
        #   extension plays no part in is_applicable() at all. So key each data file
        #   by (suffix, frozenset of its entity (key, value) pairs) for EVERY subset
        #   of its entities. A candidate then retrieves exactly the data files it is
        #   name-applicable to via key (candidate.suffix, frozenset(candidate
        #   entities)); the filesystem-location filter is applied afterwards by
        #   is_applicable() over that already-narrowed set.
        # Correctness: this is built over the FULL `metadata` set (not just the
        #   remaining data files), so the "reject if ANY non-remaining data file is
        #   applicable" guard still sees every data file. The retrieved bucket is
        #   EXACTLY the name-applicable set: any data file omitted from a candidate's
        #   bucket differs in suffix or is missing one of the candidate's entities, so
        #   is_applicable() would return False for it regardless of location — dropping
        #   it changes nothing. Candidates with a None suffix (would match any data
        #   file's suffix) fall back to the full scan rather than risk a miss.
        datafile_index: dict[tuple, list[BIDSFilePath]] = {}
        for datapath in metadata:
            entity_kvs = [(entity.key, entity.value) for entity in datapath.entities]
            for size in range(len(entity_kvs) + 1):
                for subset in combinations(entity_kvs, size):
                    datafile_index.setdefault(
                        (datapath.suffix, frozenset(subset)), []
                    ).append(datapath)

        # First step: For every unique key-value pair, generate a list of BIDSFilePaths to which it applies
        # Note: This applies exclusively to JSON; will need to do separate for non-JSON
        revkeyvalue: dict[tuple, BIDSFilePathList] = {}
        # For other metadata extensions, key by a tuple of file extension and contents
        revother: dict[tuple, BIDSFilePathList] = {}
        for datapath, by_extension in metadata.items():
            for extension, contents in by_extension.items():
                if extension == ".json":
                    for key, value in contents.items():
                        if isinstance(value, list):
                            if isinstance(value[0], list):
                                value = tuple(tuple(row) for row in value)
                            else:
                                value = tuple(value)
                        if (key, value) in revkeyvalue:
                            revkeyvalue[(key, value)].append(datapath)
                        else:
                            revkeyvalue[(key, value)] = [datapath]
                else:
                    if isinstance(contents, list):
                        if isinstance(contents[0], list):
                            contents = tuple(tuple(row) for row in contents)
                        else:
                            contents = tuple(contents)
                    if (extension, contents) in revother:
                        revother[(extension, contents)].append(datapath)
                    else:
                        revother[(extension, contents)] = [datapath]

        # Algorithm presumably will not be of the form of
        #   "find the smallest / largest filename that captures all of these",
        #   since there's no guarantee that there will in fact be a location
        #   that will encapsulate 100% of these files and 0% of other files
        # Consider instead:
        # - Generate a comprehensive list of all candidate metadata file paths
        #   that would capture at least one of these files
        # - For each of these:
        #   - If a data file not in this list would match, reject the candidate immediately
        #   - If no such match, add candidate to a set
        #     indexed by the number of data files in the list that it would be applicable to
        # - Choose the candidate that becomes applicable to the greatest number of such files
        #   (if there's a tie, should choose higher or lower parent? Fewer or more entities?
        #
        # - Remove these from the list, and repeat
        #
        # TODO Functions with greatest contribution to slow runtime:
        #     ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        # 3040723994  372.330    0.000 1553.077    0.000 filepath.py:115(__eq__)
        # 3230168741  840.637    0.000 1392.261    0.000 pathlib.py:663(__eq__)
        #   70587301   44.752    0.000  789.144    0.000 applicability.py:39(is_applicable)
        #   70587301   61.262    0.000  650.027    0.000 _collections_abc.py:1049(__contains__)
        #  260146218   54.752    0.000  377.506    0.000 _collections_abc.py:1039(__iter__)
        #  223426531  118.538    0.000  322.754    0.000 pathlib.py:525(__getitem__)
        # 6461241622  422.710    0.000  441.470    0.000 pathlib.py:654(_cparts)
        # 3460638239  126.970    0.000  126.970    0.000 {built-in method builtins.isinstance}
        #  412966059   62.059    0.000   82.203    0.000 pathlib.py:519(__len__)
        #  261022523   52.145    0.000   74.922    0.000 pathlib.py:600(_from_parsed_parts)
        #
        # - Find a more efficient way to generate the set of all possible filesystem paths
        #   given the set of data files to which this metadata key-value applies
        # - Try to avoid instantiation of pathlib.Paths until necessary
        # - Try JIT compilation: https://numba.pydata.org/
        #

        def all_subsets(ss):
            return chain(*map(lambda x: combinations(ss, x), range(0, len(ss) + 1)))

        def build_candidates(datapaths, extension: str) -> "set[BIDSFilePath]":
            # Optimisation (e), part 1: generate the entity/suffix/parent candidate
            #   space ONCE per applicability-set — from the deduplicated union of the
            #   set's data files' parents x entity-subsets x suffix — instead of
            #   rebuilding the 2^entities power set inside best_metadata_path on every
            #   greedy `while` iteration. The set() collapses candidates shared between
            #   data files (same parent/suffix, overlapping entity subsets) into one.
            # Correctness: this is built over the FULL applicability-set, not the
            #   shrinking `remaining` set, so it is a *superset* of the candidates the
            #   original per-iteration generation (over `remaining` only) would produce.
            #   Every extra candidate is one derivable only from data files already
            #   covered this round; by construction such a candidate is applicable (name
            #   AND location) to at least one of those now-non-remaining data files, so
            #   best_metadata_path's eligibility scan rejects it. The chosen candidate is
            #   therefore unchanged.
            # Location rule: each candidate's parent, suffix and entity-subset are all
            #   taken from the SAME data file, so no cross-file entity mixing is
            #   introduced and every generated candidate remains fully applicable to its
            #   own generating data file — the "applicable by name but inapplicable by
            #   location" rule is not newly violated relative to the original.
            candidates: set[BIDSFilePath] = set()
            for datapath in datapaths:
                for parent in datapath.relpath.parents:
                    for entities in all_subsets(datapath.entities):
                        candidates.add(
                            BIDSFilePath(
                                parent, list(entities), datapath.suffix, extension
                            )
                        )
            return candidates

        def best_metadata_path(
            remaining_set: "set[BIDSFilePath]",
            candidates: "set[BIDSFilePath]",
            rejected: "set[BIDSFilePath]",
        ) -> BIDSFilePath:

            # Optimisation (e), part 2: `candidates` is generated once per
            #   applicability-set (see build_candidates) and reused across the greedy
            #   iterations; `rejected` caches eligibility rejections across them.
            # Rejection monotonicity: a candidate disqualified because a NON-remaining
            #   (external / already-covered) data file is applicable to it stays
            #   disqualified — that data file never re-enters `remaining` within this
            #   solve, so the disqualifying match persists. A cached rejection is thus
            #   permanently valid and such candidates are skipped outright.
            # NOT cached: the match count (`datafile_matches`) of a still-eligible
            #   candidate DOES change as `remaining` shrinks, as does the chosen-candidate
            #   ranking; both are recomputed every iteration below.
            # BIDSFilePath is hashable (hash == relpath.__hash__, __eq__ compares
            # relpath), so it is a valid set member for `candidates`/`rejected` and for
            # the O(1) `remaining_set` membership test below.
            refined_candidates: BIDSFilePathList = []
            max_matches: int = 0
            for candidate in candidates:
                if candidate in rejected:
                    continue
                # Stringify the candidate's parent directory once per candidate,
                #   not once per data file.
                candidate_parent_str: str = str(candidate.relpath.parent)
                candidate_eligible: bool = True
                datafile_matches: int = 0
                # Consult only the data files this candidate could be name-applicable
                #   to (optimisation (c)) instead of scanning all of `metadata`. For a
                #   suffix-bearing candidate that is the exact index bucket; a
                #   suffix-less candidate could match any suffix, so fall back to the
                #   full set to stay conservative. Location is still filtered by
                #   is_applicable() below, so the truth value is unchanged.
                if candidate.suffix is not None:
                    relevant_datapaths = datafile_index.get(
                        (
                            candidate.suffix,
                            frozenset(
                                (entity.key, entity.value)
                                for entity in candidate.entities
                            ),
                        ),
                        (),
                    )
                else:
                    relevant_datapaths = metadata
                for datapath in relevant_datapaths:
                    if datapath in remaining_set:
                        if is_applicable(
                            datapath,
                            candidate,
                            parent_sets[datapath],
                            candidate_parent_str,
                        ):
                            datafile_matches += 1
                    elif is_applicable(
                        datapath,
                        candidate,
                        parent_sets[datapath],
                        candidate_parent_str,
                    ):
                        candidate_eligible = False
                        break
                if not candidate_eligible:
                    # Cache this eligibility rejection: an external match holds for
                    #   every later, smaller `remaining` in this solve, so this
                    #   candidate need never be re-tested.
                    rejected.add(candidate)
                    continue
                if datafile_matches > max_matches:
                    max_matches = datafile_matches
                    refined_candidates = [candidate]
                elif datafile_matches == max_matches:
                    refined_candidates.append(candidate)
            # At the very worst this should give a list of sidecars
            #   for the remaining data files;
            #   if it is somehow empty then there's a deficit
            #   in the generation of candidates
            assert refined_candidates

            # Now we need to choose one of the candidates from this list
            # What should our order of selection be?
            # For now, going to go with:
            #   - Lowest in the filesystem hierarchy (ie. modality directory)
            #   - But shortest file name
            # TODO If generating a proposal ruleset where suffixes are optional,
            #   may need to refine this accordingly
            def priority(item: BIDSFilePath) -> int:
                return len(item.entities) - 1024 * len(item.relpath.parents)

            candidate = sorted(refined_candidates, key=priority)[0]
            # TODO If the nominated path is higher in the filesystem hierarchy
            #   than is necessary to capture all datafiles to which it applies,
            #   push it to the lowest common parent
            # TODO Does the change in priority() above resolve?
            return candidate

        # Optimisations (a)-(e) applied. The candidate space is now generated once per
        #   applicability-set (build_candidates) rather than every greedy iteration, with
        #   rejected candidates cached across iterations.
        # Possible further work:
        # - Generate candidate paths in highest filesystem level only;
        #   if zero plausible candidates are found, choose all directories at the next level down

        new_json_data: dict[BIDSFilePath, dict] = {}
        # Optimisation (d): many distinct (key, value) pairs apply to exactly the
        #   same set of data files (e.g. every key sharing one sidecar). The greedy
        #   best_metadata_path search depends ONLY on that set of data files (plus the
        #   fixed ".json" extension and the global parent_sets/datafile_index/metadata
        #   indices), so its result — the sequence of chosen metapaths and which data
        #   files each covers — is identical for every key-value sharing an identical
        #   applicable-file set. Group the key-values by that set (a frozenset of
        #   BIDSFilePath, which is hashable — hash == relpath.__hash__) and solve ONCE
        #   per distinct set, attaching every key-value in the group to the resulting
        #   metapath(s) exactly as the per-key loop would have.
        # Guard: group STRICTLY by equal sets. Two key-values with even slightly
        #   different applicable-file sets keep separate solves — merging them would
        #   place a key on a path that over- or under-covers it and break re-resolution.
        # Invariant: within one group every key is distinct. For a fixed key, distinct
        #   values partition the data files (a data file resolves one value per key), so
        #   two (key, value) entries with the same key have DISJOINT datapaths and can
        #   never land in the same frozenset — the assert below therefore still holds.
        keyvalue_groups: dict["frozenset[BIDSFilePath]", list[tuple]] = {}
        for keyvalue, datapaths in revkeyvalue.items():
            keyvalue_groups.setdefault(frozenset(datapaths), []).append(keyvalue)
        for datapath_set, keyvalues in keyvalue_groups.items():
            # Optimisation (e): build this applicability-set's candidate space once,
            #   and carry a rejected-candidate cache across the greedy iterations.
            candidates = build_candidates(datapath_set, ".json")
            rejected: set[BIDSFilePath] = set()
            remaining_set = set(datapath_set)
            # Exit loop once there are no data files left to which these key-value
            #   metadata should be ascribed
            while remaining_set:
                metapath: BIDSFilePath = best_metadata_path(
                    remaining_set, candidates, rejected
                )
                if metapath in new_json_data:
                    target = new_json_data[metapath]
                else:
                    target = new_json_data[metapath] = {}
                for key, value in keyvalues:
                    assert key not in target
                    target[key] = value
                old_count: int = len(remaining_set)
                metapath_parent_str: str = str(metapath.relpath.parent)
                remaining_set = {
                    item
                    for item in remaining_set
                    if not is_applicable(
                        item, metapath, parent_sets[item], metapath_parent_str
                    )
                }
                assert len(remaining_set) < old_count

        new_other_data: dict[BIDSFilePath] = {}
        for (extension, contents), datapaths in revother.items():
            # Optimisation (e): as above, once-built candidate space + rejection cache.
            candidates = build_candidates(datapaths, extension)
            rejected = set()
            remaining_set = set(datapaths)
            while remaining_set:
                metapath: BIDSFilePath = best_metadata_path(
                    remaining_set, candidates, rejected
                )
                assert metapath not in new_other_data
                new_other_data[metapath] = contents
                old_count: int = len(remaining_set)
                metapath_parent_str: str = str(metapath.relpath.parent)
                remaining_set = {
                    item
                    for item in remaining_set
                    if not is_applicable(
                        item, metapath, parent_sets[item], metapath_parent_str
                    )
                }
                assert len(remaining_set) < old_count

        # (
        #     Stats(profile)
        #     .strip_dirs()
        #     .sort_stats(SortKey.CUMULATIVE)
        #     .print_stats()
        # )

    for new_json_filepath, keyvalues in new_json_data.items():
        with open(out_dir / new_json_filepath.relpath, "w", encoding="utf-8") as f:
            json.dump(keyvalues, f, indent=4)
    for new_metapath, content in new_other_data.items():
        with open(out_dir / new_metapath.relpath, "w", encoding="utf-8") as f:
            if EXTENSIONS[new_metapath.extension].is_numerical_matrix:
                numpy.savetxt(f, numpy.array(content))
            else:
                if new_metapath.extension == ".tsv":
                    for row in content:
                        f.write("\t".join(row) + "\n")
                else:
                    assert False


def _tier_metapaths(
    datapath: BIDSFilePath, extension: str
) -> "list[tuple[BIDSFilePath, bool]]":
    # Enumerate the candidate placement "tiers" for one data file, ordered from
    #   highest in the filesystem hierarchy (dataset root) to lowest (the data
    #   file's own sidecar). Each returned tuple is (metapath, is_sidecar).
    #
    # The tiers are the *entity directories* on the path to the data file — the
    #   dataset root and every ancestor directory introduced by a sub-/ses-
    #   entity — plus the data file's own directory (the sidecar).
    #
    # Two properties make placement into these tiers valid under the 1.x family
    #   (unique-within-dir + no-override + ver170 + compulsory-suffix) BY
    #   CONSTRUCTION, independent of which fields land where:
    # - Every entity-directory tier carries a *single* pattern per suffix: the
    #   accumulated sub-/ses- entities of that directory plus the suffix (e.g.
    #   `T2w` at root, `sub-01_T2w` under sub-01/). So within any one directory
    #   the emitted metadata files of a given extension are pairwise non-nested
    #   (one pattern per suffix) — the within-directory antichain invariant holds
    #   trivially, and no keyvalue override can arise between two files at one
    #   level.
    # - Entity directories sit STRICTLY above the data-file (modality) directory,
    #   so a hoisted file never shares a directory with a sidecar; the level gap
    #   turns co-application into inheritance-merge, never a same-level collision.
    # - Including exactly the sub-/ses- entities of each tier keeps the pattern
    #   ver170-valid: it name-matches only data files inside that directory's
    #   subtree (non-directory entities such as acq-/task-/echo- are omitted, so
    #   fields common across them still hoist).
    tiers: list[tuple[BIDSFilePath, bool]] = []
    directory_entities = {
        f"{entity.key}-{entity.value}": entity
        for entity in datapath.entities
        if entity.key in ("sub", "ses")
    }
    ancestors = list(datapath.relpath.parents)  # [modality_dir, ..., root]
    sidecar_dir = ancestors[0]
    for ancestor in reversed(ancestors):  # root -> ... -> modality_dir
        if ancestor == sidecar_dir:
            break
        entities = [
            directory_entities[part]
            for part in ancestor.parts
            if part in directory_entities
        ]
        tiers.append(
            (BIDSFilePath(ancestor, entities, datapath.suffix, extension), False)
        )
    tiers.append(
        (
            BIDSFilePath(
                sidecar_dir, list(datapath.entities), datapath.suffix, extension
            ),
            True,
        )
    )
    return tiers


def _pr1003_candidates(
    datapath: BIDSFilePath, extension: str
) -> "list[tuple[BIDSFilePath, bool]]":
    # PR1003 generalisation of _tier_metapaths. Under InheritanceWithinDir.ordered
    #   a directory may host several co-applicable metadata files of one extension,
    #   provided their entity counts differ (nearest-wins is then unambiguous). So at
    #   every ancestor directory D on the path to the data file — from the dataset
    #   root down to AND INCLUDING the data file's own (modality) directory — we offer
    #   NOT the single _tier_metapaths pattern but the whole family
    #     (D, dir-entities(D) ∪ S, suffix)   for every subset S of the data file's
    #   *non-directory* entities (acq, task, run, echo, part, ...).
    #
    # - dir-entities(D) — the sub-/ses- entities materialised as directories on the
    #   path to D — are ALWAYS included, exactly as in _tier_metapaths, keeping every
    #   pattern ver170-valid (name-matching only data files within D's subtree).
    # - S = ∅ recovers the single export_1x pattern at that tier; the modality
    #   directory with S = all non-directory entities recovers the data file's sidecar.
    # - Adding a non-directory entity strictly raises the pattern's entity count, so
    #   two candidates in one directory that a common data file matches differ in
    #   entity count iff |S| differs — the legality key under `ordered`.
    #
    # is_sidecar is True for exactly the (modality directory, full entity set) member.
    directory_entities = {
        f"{entity.key}-{entity.value}": entity
        for entity in datapath.entities
        if entity.key in ("sub", "ses")
    }
    nondir_entities = [
        entity for entity in datapath.entities if entity.key not in ("sub", "ses")
    ]
    ancestors = list(datapath.relpath.parents)  # [modality_dir, ..., root]
    sidecar_dir = ancestors[0]

    def subsets(items):
        return chain.from_iterable(
            combinations(items, size) for size in range(len(items) + 1)
        )

    candidates: list[tuple[BIDSFilePath, bool]] = []
    for ancestor in reversed(ancestors):  # root -> ... -> modality_dir
        dir_entities = [
            directory_entities[part]
            for part in ancestor.parts
            if part in directory_entities
        ]
        for subset in subsets(nondir_entities):
            entities = dir_entities + list(subset)
            is_sidecar = ancestor == sidecar_dir and len(subset) == len(nondir_entities)
            candidates.append(
                (
                    BIDSFilePath(ancestor, entities, datapath.suffix, extension),
                    is_sidecar,
                )
            )
        if ancestor == sidecar_dir:
            break
    return candidates


def export_PR1003(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:
    # Export a resolved dataset into a metadata layout valid — with zero warnings and
    #   zero emitted overrides — under the PR1003 ruleset (InheritanceWithinDir.ordered
    #   for JSON and non-JSON; keyvalue overrides permitted but deliberately unused).
    #
    # This reuses export_1x wholesale (copy pass, parent_sets, json_by_datafile,
    #   applicable-datafiles cache, per-field height-first placement, no-leak
    #   discipline, emit pass) and changes exactly two things:
    #   (2) the candidate set per tier expands from one pattern to
    #       _pr1003_candidates()'s power set over non-directory entities, and
    #   (3) a new "ordered-invariant" eligibility clause forbids giving any data file
    #       two applicable emitted files of EQUAL entity count within one directory.
    #   The selection priority also promotes fewest-entities above file-fatness (the
    #   entity count is now the legality key, not merely cosmetic).
    # The no-leak / non-sidecar-coverage clauses are inherited verbatim, so — as in
    #   export_1x — every key reaches each data file from exactly one applicable JSON
    #   and no override is ever emitted.

    for datapath in metadata:
        parent = out_dir / datapath.relpath.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)

    parent_sets: dict[BIDSFilePath, "frozenset[str]"] = {
        datapath: frozenset(map(str, datapath.relpath.parents)) for datapath in metadata
    }

    json_by_datafile: dict[BIDSFilePath, dict] = {
        datapath: by_extension.get(".json", {})
        for datapath, by_extension in metadata.items()
    }

    applicable_cache: dict[BIDSFilePath, "list[BIDSFilePath]"] = {}

    def applicable_datafiles(metapath: BIDSFilePath) -> "list[BIDSFilePath]":
        cached = applicable_cache.get(metapath)
        if cached is not None:
            return cached
        metapath_parent_str = str(metapath.relpath.parent)
        result = [
            datapath
            for datapath in metadata
            if is_applicable(
                datapath, metapath, parent_sets[datapath], metapath_parent_str
            )
        ]
        applicable_cache[metapath] = result
        return result

    candidate_cache: dict[tuple, "list[tuple[BIDSFilePath, bool]]"] = {}

    def candidates(datapath: BIDSFilePath, extension: str):
        key = (datapath, extension)
        cached = candidate_cache.get(key)
        if cached is None:
            cached = candidate_cache[key] = _pr1003_candidates(datapath, extension)
        return cached

    new_json_data: dict[BIDSFilePath, dict] = {}
    new_other_data: dict[BIDSFilePath, object] = {}

    # Ordered-invariant occupancy: (directory, extension, data file) ->
    #   {entity_count: metapath}. Clause 3 rejects a candidate whose entity count is
    #   already occupied for a covered data file by a DIFFERENT emitted pattern in the
    #   same directory; re-selecting the same metapath (e.g. a second key onto one
    #   JSON) is fine.
    # The extension is part of the key because the within-directory ordering rule is
    #   enforced PER EXTENSION (evaluate.py iterates has_order_ambiguity over each
    #   per-(data file, extension) BIDSFilePathList separately). A .bval and a .bvec
    #   — or a .json — at one directory level with equal entity counts never share an
    #   inheritance list and so never conflict; omitting the extension here would make
    #   a .bval placement spuriously block a .bvec (and vice versa) at the same count.
    used_patterns: dict[tuple, dict[int, BIDSFilePath]] = {}

    def choose_slot(datapath: BIDSFilePath, extension: str, matches) -> BIDSFilePath:
        def priority(item):
            metapath, _is_sidecar = item
            entries = (
                len(new_json_data.get(metapath, ())) if extension == ".json" else 0
            )
            # height (fewest parents) -> fewest entities -> most entries -> __lt__
            return (
                len(metapath.relpath.parents),
                len(metapath.entities),
                -entries,
                metapath,
            )

        for metapath, is_sidecar in sorted(
            candidates(datapath, extension), key=priority
        ):
            applicable = applicable_datafiles(metapath)
            if not all(matches(other) for other in applicable):
                continue  # clause 1: no leak / no override
            if not is_sidecar and len(applicable) < 2:
                continue  # clause 2: non-sidecar coverage >= 2
            count = len(metapath.entities)
            directory = metapath.relpath.parent
            if any(
                used_patterns.get((directory, metapath.extension, other), {}).get(
                    count, metapath
                )
                != metapath
                for other in applicable
            ):
                continue  # clause 3: ordered-invariant (equal-count collision)
            return metapath
        assert False  # sidecar tier is always admissible

    def record(metapath: BIDSFilePath) -> None:
        count = len(metapath.entities)
        directory = metapath.relpath.parent
        for other in applicable_datafiles(metapath):
            used_patterns.setdefault((directory, metapath.extension, other), {})[
                count
            ] = metapath

    for datapath in sorted(metadata):
        by_extension = metadata[datapath]
        for extension, content in by_extension.items():
            if extension == ".json":
                for key in sorted(content):
                    value = content[key]

                    def matches(other, key=key, value=value):
                        other_json = json_by_datafile[other]
                        return key in other_json and other_json[key] == value

                    metapath = choose_slot(datapath, ".json", matches)
                    target = new_json_data.setdefault(metapath, {})
                    assert target.get(key, value) == value
                    target[key] = value
                    record(metapath)
            else:

                def matches(other, extension=extension, value=content):
                    return metadata[other].get(extension) == value

                metapath = choose_slot(datapath, extension, matches)
                assert new_other_data.get(metapath, content) == content
                new_other_data[metapath] = content
                record(metapath)

    for new_json_filepath, keyvalues in new_json_data.items():
        with open(out_dir / new_json_filepath.relpath, "w", encoding="utf-8") as f:
            json.dump(keyvalues, f, indent=4, sort_keys=True)
    for new_metapath, content in new_other_data.items():
        with open(out_dir / new_metapath.relpath, "w", encoding="utf-8") as f:
            if EXTENSIONS[new_metapath.extension].is_numerical_matrix:
                numpy.savetxt(f, numpy.array(content))
            elif new_metapath.extension == ".tsv":
                for row in content:
                    f.write("\t".join(row) + "\n")
            else:
                assert False


def export_1x(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:
    # Export a resolved dataset into a metadata layout valid — with zero warnings
    #   — under the 1.1.x / 1.7.x / 1.11.x rulesets (1.11.x being the strictest,
    #   so a warning-free 1.11.x result is clean under all three).
    #
    # Strategy: for every (data file, JSON key) — and every atomic non-JSON
    #   content — hoist the field to the HIGHEST entity-directory tier
    #   (see _tier_metapaths) at which doing so introduces neither a spurious
    #   nor an overriding value, falling back to the data file's own sidecar.
    #   Tier placement guarantees the structural 1.x invariants by construction
    #   (see _tier_metapaths); this function only has to enforce, per field, that
    #   a hoisted metadata file "leaks" onto no data file whose resolved value
    #   differs (or which lacks the field entirely).
    #
    # This is the height-first objective of the plan realised without an explicit
    #   antichain-repair phase: the tier lattice is an antichain per directory a
    #   priori, so the only decision left is how high each field may rise.

    for datapath in metadata:
        parent = out_dir / datapath.relpath.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)

    parent_sets: dict[BIDSFilePath, "frozenset[str]"] = {
        datapath: frozenset(map(str, datapath.relpath.parents)) for datapath in metadata
    }

    # Precompute each data file's JSON key-values for O(1) leak checks below.
    json_by_datafile: dict[BIDSFilePath, dict] = {
        datapath: by_extension.get(".json", {})
        for datapath, by_extension in metadata.items()
    }

    # Cache, per candidate metapath, the set of data files it is applicable to
    #   (by name AND filesystem location). The applicable set depends only on the
    #   metapath, so it is shared across every field that probes the same tier.
    applicable_cache: dict[BIDSFilePath, "list[BIDSFilePath]"] = {}

    def applicable_datafiles(metapath: BIDSFilePath) -> "list[BIDSFilePath]":
        cached = applicable_cache.get(metapath)
        if cached is not None:
            return cached
        metapath_parent_str = str(metapath.relpath.parent)
        result = [
            datapath
            for datapath in metadata
            if is_applicable(
                datapath, metapath, parent_sets[datapath], metapath_parent_str
            )
        ]
        applicable_cache[metapath] = result
        return result

    def choose_slot(datapath: BIDSFilePath, extension: str, matches) -> BIDSFilePath:
        # Return the highest-tier metapath at which `datapath`'s field for this
        #   extension may be placed. `matches(other_datafile) -> bool` reports
        #   whether another data file carries an identical value for the field;
        #   a tier is admissible only if EVERY data file it is applicable to
        #   matches (no leak, no override), and — to avoid a non-sidecar warning
        #   for a metadata file exclusive to a single data file — a non-sidecar
        #   tier must cover at least two data files. The sidecar tier always
        #   qualifies (it is applicable to exactly `datapath`, which matches
        #   itself), so a slot is always found.
        for metapath, is_sidecar in _tier_metapaths(datapath, extension):
            applicable = applicable_datafiles(metapath)
            if not all(matches(other) for other in applicable):
                continue
            if is_sidecar or len(applicable) >= 2:
                return metapath
        assert False  # sidecar tier is always admissible

    new_json_data: dict[BIDSFilePath, dict] = {}
    new_other_data: dict[BIDSFilePath, object] = {}

    for datapath, by_extension in metadata.items():
        for extension, content in by_extension.items():
            if extension == ".json":
                for key, value in content.items():

                    def matches(other, key=key, value=value):
                        other_json = json_by_datafile[other]
                        return key in other_json and other_json[key] == value

                    metapath = choose_slot(datapath, ".json", matches)
                    target = new_json_data.setdefault(metapath, {})
                    # A key can reach one metapath from two data files only if
                    #   both resolve the same value (guaranteed by the leak
                    #   check), so an existing entry must be identical.
                    assert target.get(key, value) == value
                    target[key] = value
            else:

                # A non-JSON metadata file is atomic content; another data file
                #   "matches" only if its resolved content for this extension is
                #   identical.
                def matches(other, extension=extension, value=content):
                    return metadata[other].get(extension) == value

                metapath = choose_slot(datapath, extension, matches)
                assert new_other_data.get(metapath, content) == content
                new_other_data[metapath] = content

    for new_json_filepath, keyvalues in new_json_data.items():
        with open(out_dir / new_json_filepath.relpath, "w", encoding="utf-8") as f:
            json.dump(keyvalues, f, indent=4, sort_keys=True)
    for new_metapath, content in new_other_data.items():
        with open(out_dir / new_metapath.relpath, "w", encoding="utf-8") as f:
            if EXTENSIONS[new_metapath.extension].is_numerical_matrix:
                numpy.savetxt(f, numpy.array(content))
            elif new_metapath.extension == ".tsv":
                for row in content:
                    f.write("\t".join(row) + "\n")
            else:
                assert False


def export(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    ruleset: Ruleset,
    out_dir: pathlib.Path,
) -> None:

    if ruleset.name not in CONVERSION_RULESETS:
        raise TypeError(
            "Only rulesets currently supported for conversion are: "
            + str(CONVERSION_RULESETS)
        )

    out_dir.mkdir()

    for copy_unmodified in COPY_UNMODIFIED:
        fullpath = bids_dir / copy_unmodified
        if fullpath.exists():
            if fullpath.is_file():
                shutil.copyfile(fullpath, out_dir / copy_unmodified)
            elif fullpath.is_dir():
                shutil.copytree(fullpath, out_dir / copy_unmodified)
            else:
                assert False

    with open(bids_dir / "dataset_description.json", "r", encoding="utf-8") as f:
        dataset_description_data = json.load(f)
    if "GeneratedBy" in dataset_description_data:
        dataset_description_data["GeneratedBy"].append("BIDS IP-Freely")
    else:
        dataset_description_data["GeneratedBy"] = ["BIDS IP-Freely"]
    if "SourceDatasets" in dataset_description_data:
        dataset_description_data["SourceDatasets"].append(str(bids_dir))
    else:
        dataset_description_data["SourceDatasets"] = [str(bids_dir)]
    with open(out_dir / "dataset_description.json", "w", encoding="utf-8") as f:
        json.dump(dataset_description_data, f)

    if ruleset.name == "forbidden":
        export_forbidden(bids_dir, metadata, out_dir)
    elif ruleset.name == "I1195":
        export_I1195(bids_dir, metadata, out_dir)
    elif ruleset.name == "PR1003":
        export_PR1003(bids_dir, metadata, out_dir)
    elif ruleset.name in ("1.1.x", "1.7.x", "1.11.x"):
        export_1x(bids_dir, metadata, out_dir)
    else:
        assert False
