"""Greedy set-cover exporter: the `I1195` and `BIDS2I75` rulesets.

Both rulesets set ``json_inheritance_within_dir = InheritanceWithinDir.any`` and
``keyvalue_override = KeyvalueOverride.violation``: any number of applicable JSON files
may sit in one directory, but no key may ever be overridden. That combination makes the
placement problem a set cover — each (key, value) pair must be carried by a set of
metadata files whose applicability sets exactly partition the data files holding it —
rather than the per-field hoist of ``_tiered``.

The `allow_suffixless` axis is the whole difference between the two:

- ``allow_suffixless=False`` — `I1195`.
- ``allow_suffixless=True`` — `BIDS2I75`, whose ``compulsory_suffix`` is False. It
  permits candidate metadata paths whose stem is entirely entities with no trailing
  suffix; such a file is applicable to data files of ANY suffix, so a single file can
  carry fields shared across suffixes.
"""

from itertools import combinations

from ..filepath import BIDSFilePath
from ..filepath import BIDSFilePathList
from ..utils.applicability import is_applicable
from ._common import ExportContext
from ._common import hashable
from ._common import powerset
from ._common import write_metafiles


def export_greedy(context: ExportContext, *, allow_suffixless: bool) -> None:

    metadata = context.metadata
    parent_sets = context.parent_sets

    context.copy_datafiles()

    # Index data files for candidate-eligibility lookup.
    #   A candidate metadata path with suffix S (non-None) and entities E can only be
    #   *name*-applicable to a data file whose suffix equals S and whose entity
    #   key-values are a superset of E (equal values); the candidate's extension plays
    #   no part in is_applicable() at all. So key each data file by (suffix, frozenset
    #   of its entity (key, value) pairs) for EVERY subset of its entities. A candidate
    #   then retrieves exactly the data files it is name-applicable to via key
    #   (candidate.suffix, frozenset(candidate entities)); the filesystem-location
    #   filter is applied afterwards by is_applicable() over that already-narrowed set.
    # Correctness: this is built over the FULL `metadata` set (not just the remaining
    #   data files), so the "reject if ANY non-remaining data file is applicable" guard
    #   still sees every data file. The retrieved bucket is EXACTLY the name-applicable
    #   set: any data file omitted from a candidate's bucket differs in suffix or is
    #   missing one of the candidate's entities, so is_applicable() would return False
    #   for it regardless of location — dropping it changes nothing. When
    #   `allow_suffixless`, a parallel family of suffix-agnostic buckets keyed
    #   (None, subset) is also built so a suffixless candidate (which matches ANY data
    #   suffix) retrieves its exact name-applicable set from the index too, instead of
    #   a full scan.
    datafile_index: dict[tuple, list[BIDSFilePath]] = {}
    for datapath in metadata:
        entity_kvs = [(entity.key, entity.value) for entity in datapath.entities]
        for size in range(len(entity_kvs) + 1):
            for subset in combinations(entity_kvs, size):
                datafile_index.setdefault(
                    (datapath.suffix, frozenset(subset)), []
                ).append(datapath)
                if allow_suffixless:
                    datafile_index.setdefault((None, frozenset(subset)), []).append(
                        datapath
                    )

    # First step: For every unique key-value pair, generate a list of BIDSFilePaths to
    #   which it applies.
    # Note: This applies exclusively to JSON; non-JSON is handled separately, keyed by
    #   a tuple of file extension and contents.
    revkeyvalue: dict[tuple, BIDSFilePathList] = {}
    revother: dict[tuple, BIDSFilePathList] = {}
    for datapath, by_extension in metadata.items():
        for extension, contents in by_extension.items():
            if extension == ".json":
                for key, value in contents.items():
                    revkeyvalue.setdefault((key, hashable(value)), []).append(datapath)
            else:
                revother.setdefault((extension, hashable(contents)), []).append(
                    datapath
                )

    # Algorithm presumably will not be of the form of
    #   "find the smallest / largest filename that captures all of these",
    #   since there's no guarantee that there will in fact be a location
    #   that will encapsulate 100% of these files and 0% of other files
    # Consider instead:
    # - Generate a comprehensive list of all candidate metadata file paths
    #   that would capture at least one of these files
    # - For each of these:
    #   - If a data file not in this list would match, reject the candidate immediately
    #   - If no such match, add candidate to a set indexed by the number of data
    #     files in the list that it would be applicable to
    # - Choose the candidate that becomes applicable to the greatest number of such
    #   files
    # - Remove these from the list, and repeat

    def build_candidates(datapaths, extension: str) -> "set[BIDSFilePath]":
        # Generate the entity/suffix/parent candidate space ONCE per
        #   applicability-set — from the deduplicated union of the set's data files'
        #   parents x entity-subsets x suffix — instead of rebuilding the 2^entities
        #   power set inside best_metadata_path on every greedy `while` iteration. The
        #   set() collapses candidates shared between data files (same parent/suffix,
        #   overlapping entity subsets) into one.
        # Correctness: this is built over the FULL applicability-set, not the shrinking
        #   `remaining` set, so it is a *superset* of the candidates a per-iteration
        #   generation (over `remaining` only) would produce. Every extra candidate is
        #   one derivable only from data files already covered this round; by
        #   construction such a candidate is applicable (name AND location) to at least
        #   one of those now-non-remaining data files, so best_metadata_path's
        #   eligibility scan rejects it. The chosen candidate is therefore unchanged.
        # Location rule: each candidate's parent, suffix and entity-subset are all
        #   taken from the SAME data file, so no cross-file entity mixing is introduced
        #   and every generated candidate remains fully applicable to its own
        #   generating data file — the "applicable by name but inapplicable by
        #   location" rule is not violated.
        candidates: set[BIDSFilePath] = set()
        # BIDS2I75 only: also propose a suffixless variant of each JSON candidate,
        #   applicable to data of any suffix. The empty-stem case (no entities AND no
        #   suffix -> a bare ".json") is excluded, so a suffixless candidate is emitted
        #   only when it carries >=1 entity. Restricted to ".json"; .bval/.bvec/.tsv
        #   stay suffix-specific.
        emit_suffixless = allow_suffixless and extension == ".json"
        for datapath in datapaths:
            for parent in datapath.relpath.parents:
                for entities in powerset(datapath.entities):
                    candidates.add(
                        BIDSFilePath(parent, list(entities), datapath.suffix, extension)
                    )
                    if emit_suffixless and entities:
                        candidates.add(
                            BIDSFilePath(parent, list(entities), None, extension)
                        )
        return candidates

    # TODO Functions with greatest contribution to slow runtime.
    #   (cProfile, with the per-call columns dropped: every one read 0.000)
    #     ncalls  tottime  cumtime  filename:lineno(function)
    # 3040723994  372.330 1553.077  filepath.py:115(__eq__)
    # 3230168741  840.637 1392.261  pathlib.py:663(__eq__)
    #   70587301   44.752  789.144  applicability.py:39(is_applicable)
    #   70587301   61.262  650.027  _collections_abc.py:1049(__contains__)
    #  260146218   54.752  377.506  _collections_abc.py:1039(__iter__)
    #  223426531  118.538  322.754  pathlib.py:525(__getitem__)
    # 6461241622  422.710  441.470  pathlib.py:654(_cparts)
    # 3460638239  126.970  126.970  {built-in method builtins.isinstance}
    #  412966059   62.059   82.203  pathlib.py:519(__len__)
    #  261022523   52.145   74.922  pathlib.py:600(_from_parsed_parts)
    #
    # - Find a more efficient way to generate the set of all possible filesystem paths
    #   given the set of data files to which this metadata key-value applies
    # - Try to avoid instantiation of pathlib.Paths until necessary
    # - Try JIT compilation: https://numba.pydata.org/
    #
    # NB: is_applicable() is called directly rather than via
    #   ExportContext.applicable_datafiles(); this is the profiled hot path, and the
    #   candidate-driven access pattern here is the opposite of that method's
    #   metapath-keyed memoisation.

    def best_metadata_path(
        remaining_set: "set[BIDSFilePath]",
        candidates: "set[BIDSFilePath]",
        rejected: "set[BIDSFilePath]",
    ) -> BIDSFilePath:

        # `candidates` is generated once per applicability-set (see build_candidates)
        #   and reused across the greedy iterations; `rejected` caches eligibility
        #   rejections across them.
        # Rejection monotonicity: a candidate disqualified because a NON-remaining
        #   (external / already-covered) data file is applicable to it stays
        #   disqualified — that data file never re-enters `remaining` within this
        #   solve, so the disqualifying match persists. A cached rejection is thus
        #   permanently valid and such candidates are skipped outright.
        # NOT cached: the match count (`datafile_matches`) of a still-eligible
        #   candidate DOES change as `remaining` shrinks, as does the chosen-candidate
        #   ranking; both are recomputed every iteration below.
        # BIDSFilePath is hashable (hash == relpath.__hash__, __eq__ compares relpath),
        #   so it is a valid set member for `candidates`/`rejected` and for the O(1)
        #   `remaining_set` membership test below.
        refined_candidates: BIDSFilePathList = []
        max_matches: int = 0
        for candidate in candidates:
            if candidate in rejected:
                continue
            # Stringify the candidate's parent directory once per candidate, not once
            #   per data file.
            candidate_parent_str: str = str(candidate.relpath.parent)
            candidate_eligible: bool = True
            datafile_matches: int = 0
            # Consult only the data files this candidate could be name-applicable to,
            #   instead of scanning all of `metadata`. The index bucket keyed on the
            #   candidate's own suffix (possibly None, for a suffixless BIDS2I75
            #   candidate, whose (None, subset) buckets are populated above) is EXACTLY
            #   that name-applicable set. Location is still filtered by is_applicable()
            #   below.
            relevant_datapaths = datafile_index.get(
                (
                    candidate.suffix,
                    frozenset(
                        (entity.key, entity.value) for entity in candidate.entities
                    ),
                ),
                (),
            )
            for datapath in relevant_datapaths:
                # `relevant_datapaths` is EXACTLY the candidate's name-applicable set
                #   (is_applicable_nameonly == True for every member). So the
                #   is_applicable() call here reduces to the filesystem-location test
                #   alone.
                if not is_applicable(
                    datapath,
                    candidate,
                    parent_sets[datapath],
                    candidate_parent_str,
                ):
                    # Name-applicable but the candidate is NOT in this data file's
                    #   filesystem path. Under MetaPathCheck.ver170 that is a "matches
                    #   in name but not in path" violation (evaluate.py's
                    #   bad_metadata_path check), which makes the candidate an invalid
                    #   metadata-file location outright — independent of whether the
                    #   data file is still remaining. Using is_applicable() (name AND
                    #   path) for the leak check alone would push a file DOWN into a
                    #   subdirectory to dodge a path-leak while still name-matching
                    #   data files outside that subtree; that produced ver170
                    #   violations. Rejecting here forbids such placements, forcing the
                    #   field onto a pattern whose entire name-applicable set lies
                    #   within its subtree.
                    candidate_eligible = False
                    break
                if datapath in remaining_set:
                    datafile_matches += 1
                else:
                    # Path-applicable to a data file that is NOT in `remaining_set`
                    #   (already covered this solve, or carrying a different value): a
                    #   second applicable metadata file for the same key, i.e. an
                    #   override/leak. Forbidden under these rulesets.
                    candidate_eligible = False
                    break
            if not candidate_eligible:
                # Cache this eligibility rejection. Both rejection causes are monotonic
                #   across the shrinking `remaining_set`: the ver170 name-but-not-path
                #   match depends only on the candidate and the full data-file set, and
                #   an external path-leak match persists for every later, smaller
                #   `remaining`. So the candidate need never be re-tested within this
                #   solve.
                rejected.add(candidate)
                continue
            if datafile_matches > max_matches:
                max_matches = datafile_matches
                refined_candidates = [candidate]
            elif datafile_matches == max_matches:
                refined_candidates.append(candidate)
        # At the very worst this should give a list of sidecars for the remaining data
        #   files; if it is somehow empty then there's a deficit in the generation of
        #   candidates
        assert refined_candidates

        # Now we need to choose one of the candidates from this list.
        # Order of selection (among candidates of equal coverage):
        #   - A suffixless candidate ahead of a suffixed one (BIDS2I75 maximal
        #     exploitation)
        #   - Then lowest in the filesystem hierarchy (ie. modality directory)
        #   - Then shortest file name (fewest entities)
        #   - Then the path itself, purely to break remaining ties
        # For I1195 (allow_suffixless False) no suffixless candidate exists, so the
        #   leading key is constant.
        # The trailing key matters: `refined_candidates` is accumulated by iterating
        #   `candidates`, a set of BIDSFilePath whose hash is pathlib's (string-based,
        #   and therefore randomised per interpreter run). Without a total order the
        #   winner among equally-ranked candidates was whichever the set happened to
        #   yield first, so successive conversions of one dataset produced different —
        #   though equally valid — layouts. BIDSFilePath.__lt__ is the ordering used
        #   throughout the codebase, so reuse it here.
        def priority(item: BIDSFilePath) -> tuple:
            return (
                0 if item.suffix is None else 1,
                len(item.entities) - 1024 * len(item.relpath.parents),
                item,
            )

        candidate = sorted(refined_candidates, key=priority)[0]
        # TODO If the nominated path is higher in the filesystem hierarchy
        #   than is necessary to capture all datafiles to which it applies,
        #   push it to the lowest common parent
        # TODO Does the change in priority() above resolve?
        return candidate

    # Possible further work:
    # - Generate candidate paths in highest filesystem level only;
    #   if zero plausible candidates are found, choose all directories at the next
    #   level down

    def cover(datapaths, extension: str, assign) -> None:
        # Greedily cover one applicability-set: repeatedly take the candidate metadata
        #   path applicable to the most still-uncovered data files, hand it to
        #   `assign`, and drop the data files it covers. The candidate space is built
        #   once and the rejection cache carried across iterations.
        candidates = build_candidates(datapaths, extension)
        rejected: set[BIDSFilePath] = set()
        remaining_set = set(datapaths)
        while remaining_set:
            metapath: BIDSFilePath = best_metadata_path(
                remaining_set, candidates, rejected
            )
            assign(metapath)
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

    new_json_data: dict[BIDSFilePath, dict] = {}
    new_other_data: dict[BIDSFilePath, object] = {}

    # Many distinct (key, value) pairs apply to exactly the same set of data files
    #   (e.g. every key sharing one sidecar). The greedy best_metadata_path search
    #   depends ONLY on that set of data files (plus the fixed ".json" extension and
    #   the global parent_sets/datafile_index/metadata indices), so its result — the
    #   sequence of chosen metapaths and which data files each covers — is identical
    #   for every key-value sharing an identical applicable-file set. Group the
    #   key-values by that set (a frozenset of BIDSFilePath, which is hashable — hash
    #   == relpath.__hash__) and solve ONCE per distinct set, attaching every key-value
    #   in the group to the resulting metapath(s) exactly as a per-key loop would have.
    # Guard: group STRICTLY by equal sets. Two key-values with even slightly different
    #   applicable-file sets keep separate solves — merging them would place a key on a
    #   path that over- or under-covers it and break re-resolution.
    # Invariant: within one group every key is distinct. For a fixed key, distinct
    #   values partition the data files (a data file resolves one value per key), so
    #   two (key, value) entries with the same key have DISJOINT datapaths and can
    #   never land in the same frozenset — the assert below therefore still holds.
    keyvalue_groups: dict["frozenset[BIDSFilePath]", list[tuple]] = {}
    for keyvalue, datapaths in revkeyvalue.items():
        keyvalue_groups.setdefault(frozenset(datapaths), []).append(keyvalue)

    for datapath_set, keyvalues in keyvalue_groups.items():

        def assign_keyvalues(metapath: BIDSFilePath, keyvalues=keyvalues) -> None:
            target = new_json_data.setdefault(metapath, {})
            for key, value in keyvalues:
                assert key not in target
                target[key] = value

        cover(datapath_set, ".json", assign_keyvalues)

    for (extension, contents), datapaths in revother.items():

        def assign_contents(metapath: BIDSFilePath, contents=contents) -> None:
            assert metapath not in new_other_data
            new_other_data[metapath] = contents

        cover(datapaths, extension, assign_contents)

    write_metafiles(context.out_dir, new_json_data)
    write_metafiles(context.out_dir, new_other_data)
