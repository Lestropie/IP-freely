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
    for entity in metafile.entities:
        try:
            if (
                next(item for item in datafile.entities if item.key == entity.key).value
                != entity.value
            ):
                return False
        except StopIteration:
            # Metadata file entity not present in data file
            return False
    return True


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
