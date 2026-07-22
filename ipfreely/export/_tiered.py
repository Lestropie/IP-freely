"""Height-first tiered exporter: the `1.1.x` / `1.7.x` / `1.11.x` and `PR1003` rulesets.

Strategy: for every (data file, JSON key) — and every atomic non-JSON content — hoist
the field to the HIGHEST candidate metadata file at which doing so introduces neither a
spurious nor an overriding value, falling back to the data file's own sidecar. The
candidate lattice is constructed so that the structural invariants of these rulesets
hold *by construction* (see :func:`_candidate_metapaths`), leaving this module only one
decision per field: how high may it rise.

This is the height-first objective realised without an explicit antichain-repair phase.

The `expand` axis is the whole difference between the two families:

- ``expand=False`` — the 1.x family. One pattern per suffix per entity directory, so
  the emitted metadata files within any one directory are pairwise non-nested: the
  ``InheritanceWithinDir.unique`` invariant holds trivially and no keyvalue override can
  arise. A warning-free result under `1.11.x` (the strictest of the three) is clean
  under all three.
- ``expand=True`` — `PR1003`. Under ``InheritanceWithinDir.ordered`` a directory may
  host several co-applicable metadata files of one extension provided their entity
  counts differ, so each directory offers a whole family of patterns rather than one.
  That freedom has to be policed explicitly, by :class:`_OrderedOccupancy`.

`PR1003` also permits keyvalue overrides (``KeyvalueOverride.permitted``), but this
exporter deliberately does not use that freedom: as in the 1.x family, every key reaches
each data file from exactly one applicable JSON and no override is ever emitted.
"""

from ..filepath import BIDSFilePath
from ._common import ExportContext
from ._common import powerset
from ._common import write_metafiles


def _candidate_metapaths(
    datapath: BIDSFilePath, extension: str, *, expand: bool
) -> "list[tuple[BIDSFilePath, bool]]":
    # Enumerate the candidate placements for one data file, ordered from highest in
    #   the filesystem hierarchy (dataset root) to lowest (the data file's own
    #   sidecar). Each returned tuple is (metapath, is_sidecar).
    #
    # The tiers are the *entity directories* on the path to the data file — the
    #   dataset root and every ancestor directory introduced by a sub-/ses- entity —
    #   plus the data file's own directory.
    #
    # Two properties make placement into these tiers valid BY CONSTRUCTION,
    #   independent of which fields land where:
    # - Entity directories sit STRICTLY above the data-file (modality) directory, so a
    #   hoisted file never shares a directory with a sidecar; the level gap turns
    #   co-application into inheritance-merge, never a same-level collision.
    # - Including exactly the sub-/ses- entities materialised as directories on the
    #   path to each tier keeps the pattern ver170-valid: it name-matches only data
    #   files inside that directory's subtree. Non-directory entities (acq-, task-,
    #   echo-, part-, run-, ...) are omitted, so fields common across them still hoist.
    #
    # With `expand`, each ancestor directory D additionally offers the whole family
    #   (D, dir-entities(D) u S, suffix) for every subset S of the data file's
    #   *non-directory* entities, and the data file's own directory joins the tiers
    #   rather than contributing the sidecar alone:
    # - S = () recovers the single 1.x pattern at that tier.
    # - Adding a non-directory entity strictly raises the pattern's entity count, so
    #   two candidates in one directory that a common data file matches differ in
    #   entity count iff |S| differs — the legality key under `ordered`.
    # - The pay-off, unavailable to 1.x: a field common to a *subset* of a directory's
    #   data files can be hoisted alongside a more general file in that same directory,
    #   because their entity counts differ.
    directory_entities = {
        f"{entity.key}-{entity.value}": entity
        for entity in datapath.entities
        if entity.key in ("sub", "ses")
    }
    nondirectory_entities = [
        entity for entity in datapath.entities if entity.key not in ("sub", "ses")
    ]
    ancestors = list(datapath.relpath.parents)  # [modality_dir, ..., root]
    sidecar_dir = ancestors[0]

    candidates: list[tuple[BIDSFilePath, bool]] = []
    for ancestor in reversed(ancestors):  # root -> ... -> modality_dir
        at_sidecar_dir = ancestor == sidecar_dir
        if at_sidecar_dir and not expand:
            # Without `expand` the data file's own directory offers the sidecar only,
            #   which is appended unconditionally below.
            break
        dir_entities = [
            directory_entities[part]
            for part in ancestor.parts
            if part in directory_entities
        ]
        for subset in powerset(nondirectory_entities) if expand else [()]:
            if at_sidecar_dir and len(subset) == len(nondirectory_entities):
                # dir-entities(sidecar_dir) u all non-directory entities IS the
                #   sidecar; it is appended below, in its canonical form.
                continue
            candidates.append(
                (
                    BIDSFilePath(
                        ancestor,
                        dir_entities + list(subset),
                        datapath.suffix,
                        extension,
                    ),
                    False,
                )
            )
        if at_sidecar_dir:
            break
    # The sidecar carries the data file's entities verbatim rather than a reassembled
    #   dir-entities + non-directory-entities list, so that a sub-/ses- entity which
    #   happens not to be materialised as a directory cannot be silently dropped.
    candidates.append(
        (
            BIDSFilePath(
                sidecar_dir, list(datapath.entities), datapath.suffix, extension
            ),
            True,
        )
    )
    return candidates


class _NoOccupancy:  # pylint: disable=unused-argument
    # 1.x: the tier lattice is a per-directory antichain a priori (one pattern per
    #   suffix per entity directory), so there is no within-directory constraint left
    #   to police and every candidate is admissible. Same interface as
    #   _OrderedOccupancy, so that _choose_slot needs no ruleset-dependent branch.

    def admissible(self, metapath: BIDSFilePath, applicable) -> bool:
        return True

    def record(self, metapath: BIDSFilePath, applicable) -> None:
        pass


class _OrderedOccupancy:
    # PR1003: `ordered` permits several co-applicable metadata files of one extension
    #   in one directory only while their entity counts differ, so track which entity
    #   counts are already spoken for.
    #
    # Occupancy is keyed (directory string, extension, data file) -> {entity count:
    #   metapath}. The directory is keyed by its cached string rather than by a
    #   PurePath: for a fixed flavour the two induce the same equivalence classes, and
    #   the string needs neither construction nor a Python-level hash.
    #   A candidate is rejected when its entity count is already occupied, for a data
    #   file it covers, by a DIFFERENT emitted pattern in the same directory;
    #   re-selecting the same metapath (e.g. a second key onto one JSON) is fine.
    #
    # The extension is part of the key because the within-directory ordering rule is
    #   enforced PER EXTENSION (evaluate.py iterates has_order_ambiguity over each
    #   per-(data file, extension) BIDSFilePathList separately). A .bval and a .bvec —
    #   or a .json — at one directory level with equal entity counts never share an
    #   inheritance list and so never conflict; omitting the extension here would make
    #   a .bval placement spuriously block a .bvec at the same count.

    def __init__(self):
        self._used: dict[tuple, dict[int, BIDSFilePath]] = {}

    def admissible(self, metapath: BIDSFilePath, applicable) -> bool:
        count = len(metapath.entities)
        directory = metapath.parentstr
        return not any(
            self._used.get((directory, metapath.extension, other), {}).get(
                count, metapath
            )
            != metapath
            for other in applicable
        )

    def record(self, metapath: BIDSFilePath, applicable) -> None:
        count = len(metapath.entities)
        directory = metapath.parentstr
        for other in applicable:
            self._used.setdefault((directory, metapath.extension, other), {})[
                count
            ] = metapath


def _choose_slot(
    context: ExportContext, candidates, matches, occupancy, rank=None
) -> BIDSFilePath:
    # Return the highest-ranked candidate metapath at which one field may be placed.
    #   `matches(other_datafile) -> bool` reports whether another data file carries an
    #   identical value for the field.
    # `rank` is None for the 1.x family, whose candidates are already generated
    #   highest-first; PR1003 supplies an explicit ordering because its candidates form
    #   a lattice rather than a chain.
    for metapath, is_sidecar in (
        candidates if rank is None else sorted(candidates, key=rank)
    ):
        applicable = context.applicable_datafiles(metapath)
        if not all(matches(other) for other in applicable):
            # Clause 1: no leak, no override. A candidate is admissible only if EVERY
            #   data file it is applicable to resolves this field to the same value;
            #   otherwise placing the field here would either invent a value for a
            #   data file that lacks it or override one that differs.
            continue
        if not is_sidecar and len(applicable) < 2:
            # Clause 2: a non-sidecar metadata file exclusive to a single data file
            #   would draw a non-sidecar warning for no benefit.
            continue
        if not occupancy.admissible(metapath, applicable):
            # Clause 3: PR1003's ordered invariant (no equal-entity-count collision
            #   within one directory). A no-op for the 1.x family.
            continue
        return metapath
    # The sidecar tier is always admissible: it is applicable to exactly `datapath`,
    #   which matches itself.
    assert False


def export_tiered(context: ExportContext, *, expand: bool = False) -> None:

    context.copy_datafiles()

    occupancy = _OrderedOccupancy() if expand else _NoOccupancy()
    new_json_data: dict[BIDSFilePath, dict] = {}
    new_other_data: dict[BIDSFilePath, object] = {}

    candidate_cache: dict[tuple, "list[tuple[BIDSFilePath, bool]]"] = {}

    def candidates(datapath: BIDSFilePath, extension: str):
        key = (datapath, extension)
        cached = candidate_cache.get(key)
        if cached is None:
            cached = candidate_cache[key] = _candidate_metapaths(
                datapath, extension, expand=expand
            )
        return cached

    def rank(item):
        # height (fewest parents) -> fewest entities -> most entries -> path.
        # Fewest-entities outranks file-fatness because under `ordered` the entity
        #   count is the legality key, not merely cosmetic. The trailing key makes the
        #   ordering total, so the choice never depends on generation order.
        # The trailing key is the metapath's cached path STRING, not the metapath
        #   itself: tuple comparison only ever reaches it once height and entity count
        #   are equal, and for two such candidates BIDSFilePath.__lt__ itself reduces
        #   to the same alphanumeric comparison of the path. (Equal height rules out
        #   its ancestor branches -- a strict ancestor directory is strictly
        #   shallower -- and every candidate for one data file carries that data file's
        #   suffix, so its suffixless-first branch cannot fire either.) Using the
        #   string avoids paying __lt__ per comparison on every sort.
        metapath, _is_sidecar = item
        entries = (
            len(new_json_data.get(metapath, ())) if metapath.extension == ".json" else 0
        )
        return (
            metapath.depth,
            len(metapath.entities),
            -entries,
            metapath.pathstr,
        )

    ranker = rank if expand else None

    # Data files and JSON keys are visited in sorted order. PR1003 requires it: its
    #   ranking consults how many entries a candidate already holds, and its occupancy
    #   map accumulates, so its per-field decisions are order-dependent. The 1.x family
    #   reads nothing that placement mutates — applicable_datafiles() and matches()
    #   depend only on the input metadata — so its decisions are order-independent and
    #   sorting is free.
    for datapath in sorted(context.metadata):
        for extension, content in context.metadata[datapath].items():
            if extension == ".json":
                for key in sorted(content):
                    value = content[key]

                    def matches(other, key=key, value=value):
                        other_json = context.json_by_datafile[other]
                        return key in other_json and other_json[key] == value

                    metapath = _choose_slot(
                        context,
                        candidates(datapath, ".json"),
                        matches,
                        occupancy,
                        ranker,
                    )
                    target = new_json_data.setdefault(metapath, {})
                    # A key can reach one metapath from two data files only if both
                    #   resolve the same value (guaranteed by clause 1), so an existing
                    #   entry must be identical.
                    assert target.get(key, value) == value
                    target[key] = value
                    occupancy.record(metapath, context.applicable_datafiles(metapath))
            else:

                # A non-JSON metadata file is atomic content; another data file
                #   "matches" only if its resolved content for this extension is
                #   identical.
                def matches(other, extension=extension, value=content):
                    return context.metadata[other].get(extension) == value

                metapath = _choose_slot(
                    context,
                    candidates(datapath, extension),
                    matches,
                    occupancy,
                    ranker,
                )
                assert new_other_data.get(metapath, content) == content
                new_other_data[metapath] = content
                occupancy.record(metapath, context.applicable_datafiles(metapath))

    write_metafiles(context.out_dir, new_json_data)
    write_metafiles(context.out_dir, new_other_data)
