import sys
from ..filepath import BIDSFilePath


# Function that determines whether a metadata file
#   could potentially be applicable to a data file
#   but based exclusively on filename, not filesystem location
def is_applicable_nameonly(datafile: BIDSFilePath, metafile: BIDSFilePath) -> bool:
    # While this would be a nice requirement to impose,
    #   getting the data into this form is likely requiring unnecessary computation
    # if len(datafile.relpath.parents) != 1 or len(metafile.relpath.parents) != 1:
    #    raise TypeError(
    #        "Inputs to utils.is_applicable_filename()"
    #        "must be pure file names only; no parent directory"
    #    )
    # If the metadata file has a suffix,
    #   it must match the data file
    # (there are some proposed rule sets where maybe metadata files
    #   don't need to have a suffix)
    if metafile.suffix is not None and metafile.suffix != datafile.suffix:
        return False
    # If there's any entities in the metafile that are either absent from the data file,
    #   or that have a different value for that entity than the data file,
    #   then the metadata file is not applicable
    # The data file can however have entities that aren't present in the metadata file
    #
    # That is exactly subset containment of the (key, value) pairs, evaluated here as a
    #   single C-level frozenset comparison over the sets cached on each BIDSFilePath at
    #   construction, in place of the previous
    #   `next(item for item in datafile.entities if item.key == entity.key)` linear scan
    #   (one generator built and consumed per metadata entity per call: 304k calls and
    #   1.37M generator steps for one BIDS2I75 conversion).
    #
    # Why the two are the same predicate. Write E_m and E_d for the metadata and data
    #   files' (key, value) sets. BIDSFilePath rejects duplicate entity keys in BOTH
    #   constructors, so within one file a key appears at most once and E_d is a
    #   faithful rendering of `datafile.entities`.
    #   - If E_m <= E_d: for each metadata entity (k, v), (k, v) is in E_d, so the data
    #     file has an entity with key k; key-uniqueness makes it THE entity next() would
    #     have found, and its value is v, so no iteration returned False. Old: True.
    #   - If the old form returned True: for each metadata entity (k, v), next()
    #     succeeded and the found entity's value equalled v, so (k, v) is in E_d. Hence
    #     E_m <= E_d.
    #   Duplicate entities on the METADATA side (which the constructors reject, but
    #   which the old form tolerated) would not separate the two either: a repeated
    #   (k, v) re-tests an identical condition and collapses in E_m, while (k, v1) and
    #   (k, v2) with v1 != v2 fail both forms, since E_d holds at most one pair for k.
    return metafile.entityset <= datafile.entityset


def is_applicable(
    datafile: BIDSFilePath,
    metafile: BIDSFilePath,
    datafile_parent_set: "frozenset[str] | None" = None,
    metafile_parent_str: "str | None" = None,
) -> bool:
    # Fast path: when the caller supplies a precomputed hashed set of the data
    #   file's ancestor-directory strings, the parent-directory test is an O(1)
    #   string-set membership instead of iterating a pathlib parents sequence.
    # Note: datafile.relpath.parents includes the immediate parent as parents[0],
    #   so frozenset(map(str, datafile.relpath.parents)) covers the same-directory
    #   case identically; the two branches below are behaviourally equivalent.
    if datafile_parent_set is None:
        if not metafile.relpath.parent in datafile.relpath.parents:
            return False
    else:
        if metafile_parent_str is None:
            metafile_parent_str = str(metafile.relpath.parent)
        if metafile_parent_str not in datafile_parent_set:
            return False
    return is_applicable_nameonly(datafile, metafile)
