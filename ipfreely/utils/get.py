import os
import pathlib
from .. import InheritanceError
from .. import EXCLUSIONS
from ..filepath import BIDSFilePath
from ..extensions import EXTENSIONS
from ..extensions import EXTENSIONS_STR
from ..extensions import InheritanceBehaviour
from ..ruleset import InheritanceWithinDir
from ..ruleset import Ruleset
from .applicability import is_applicable


def metafiles_for_datafile(
    bids_dir: pathlib.Path, datafile: BIDSFilePath, ruleset: Ruleset, **kwargs
) -> dict[str, list[BIDSFilePath]]:

    single_extension = kwargs.pop("extension", None)
    extensions = kwargs.pop("extensions", None)
    assert not (single_extension is not None and extensions is not None)
    if single_extension is not None:
        assert single_extension in EXTENSIONS_STR
        extensions = {single_extension: EXTENSIONS[single_extension]}
    if extensions is None:
        extensions = EXTENSIONS
    else:
        assert all(item in EXTENSIONS_STR for item in extensions)
        extensions = dict([item, EXTENSIONS[item]] for item in extensions)

    # Generate a list of directories in which the search will occur
    # This is all parents of the data file,
    #   including the directory in which it resides,
    #   but does not include anything beyond the BIDS root directory
    parents = [bids_dir / parent for parent in datafile.relpath.parents]

    all_matches: dict[str, list[BIDSFilePath]] = {}

    # Start at the highest level in the filesystem hierarchy
    for parent in reversed(parents):

        # Get all matches just at this level of the filesystem hierarchy
        dir_matches: dict[str, list[BIDSFilePath]] = {}

        # Get list of files present in this directory
        for filename in parent.iterdir():
            if filename.is_dir():
                continue

            # Don't attempt to process BIDS reserved files
            if parent == bids_dir and filename.name in EXCLUSIONS:
                continue

            filepath = BIDSFilePath(bids_dir, filename)
            # Find out if the file extension matches our metadata search
            if filepath.extension not in extensions:
                continue

            # Is the metadata file deemed applicable to the data file?
            if not is_applicable(datafile, filepath):
                continue

            # Violations to the Inheritance Principle:
            # Cannot be more than one applicable metadata file
            #   at any level of the filesystem hierarchy
            if (
                EXTENSIONS[filepath.extension].inheritance_behaviour
                == InheritanceBehaviour.forbidden
            ):
                if filepath.extension in all_matches or extension in dir_matches:
                    raise InheritanceError(
                        "Multiple applicable metadata files"
                        f" with file extension {extension}"
                        f" for data file {datafile}"
                    )
            elif (
                EXTENSIONS[filepath.extension].inheritance_behaviour == InheritanceBehaviour.nearest
            ):
                pass
            elif EXTENSIONS[filepath.extension].inheritance_behaviour == InheritanceBehaviour.merge:

                # While .behaviour == merge and .extension == 'json'
                #   are technically not one and the same,
                #   the code is currently written as such
                assert filepath.extension == ".json"

                if ruleset.json_inheritance_within_dir == InheritanceWithinDir.unique:
                    # Detect attempt to add a second applicable JSON
                    #   within this directory level
                    if filepath.extension in dir_matches:
                        raise InheritanceError(
                            f"Multiple applicable {filepath.extension} metadata files"
                            " within a single filesystem level"
                            f" for data file {datafile}"
                            f" forbidden in ruleset \"{ruleset.name}\""
                        )
                elif (
                    ruleset.json_inheritance_within_dir == InheritanceWithinDir.ordered
                ):
                    # Detect attempt to have two applicable JSONs
                    #   within a single directory level
                    #   that both possess the same number of entities
                    #   (and therefore can't be unambiguously sorted)
                    if filepath.extension in dir_matches and any(
                        len(item.entities) == len(filepath.entities)
                        for item in dir_matches[filepath.extension]
                    ):
                        raise InheritanceError(
                            f"Multiple applicable {filepath.extension} metadata files"
                            " with an identical number of entities"
                            " within a single filesystem level"
                            f" for data file {datafile}"
                            f" forbidden in ruleset \"{ruleset.name}\""
                        )
                elif ruleset.json_inheritance_within_dir == InheritanceWithinDir.any:
                    pass
                else:
                    assert False

            else:
                assert False

            # Add this file to the set of metadata files
            #   deemed applicable to this data file
            #   at this level of the filesystem hierarchy
            if filepath.extension in dir_matches:
                dir_matches[filepath.extension].append(filepath)
            else:
                dir_matches[filepath.extension] = [filepath]

        for extension, filepaths in dir_matches.items():
            # Resolve the set of matches found that this filesystem hierarchy level
            #   with the set of matches found at all levels
            # If we are only interested in whichever one metadata file
            #   is closest to the data file,
            #   then we don't need to worry about any of the contents
            #   of any lower parent directories
            if (
                extension not in all_matches
                or EXTENSIONS[extension].inheritance_behaviour == InheritanceBehaviour.nearest
            ):
                all_matches[extension] = sorted(filepaths)
            else:
                all_matches[extension].extend(sorted(filepaths))

    # Additional violation checks
    #   after all contents of this filesystem level have been read
    nearest_matches: dict[str] = {}
    for extension, filepaths in all_matches.items():
        if EXTENSIONS[extension].inheritance_behaviour == InheritanceBehaviour.nearest:
            # Needs to be a singular unambiguous choice
            #   as to which of these metadata files is "nearest" to the data file
            # Prior code ensures that if there are multiple candidate matches
            #   across multiple different filesystem levels,
            #   any that are further down the filesystem hierarchy
            #   than at least one other match
            #   will already have been discarded;
            #   we are therefore only considering the prospect of multiple matches
            #   within a single filesystem level
            if len(filepaths) == 1:
                continue
            max_entity_count = max(len(item.entities) for item in filepaths)
            nearest = [
                item for item in filepaths if len(item.entities) == max_entity_count
            ]
            if len(nearest) > 1:
                raise InheritanceError(
                    f"Ambiguity in nearest .{extension} metadata file"
                    f" applicable to data file {datafile}"
                    " due to presence of multiple applicable metadata files"
                    " at one filesystem level with an equal number of entities"
                    f" forbidden in ruleset \"{ruleset.name}\""
                )
            nearest_matches[extension] = nearest[0]
    # For extensions where only the nearest applicable metadata file is used,
    #   remove those that should be ignored
    for extension, filepath in nearest_matches:
        all_matches[extension] = [filepath]

    return all_matches


def datafiles_for_metafile(
    bids_dir: pathlib.Path, metafile: BIDSFilePath, ruleset: Ruleset
) -> list[BIDSFilePath]:

    initial_result: list[BIDSFilePath] = []
    # When comparing the entities of a data file to those of this metadata file,
    #   want to be able to quickly and efficiently check whether the corresponding
    #   entity is present in the metadata file,
    #   and if so, whether the value is identical;
    #   pre-converting from list to dict should make these comparisons faster
    metafile_entities_dict = {entity.key: entity.value for entity in metafile.entities}
    for root, _, files in os.walk(bids_dir / metafile.relpath.parent):
        rootpath = pathlib.Path(root)
        if rootpath.name in EXCLUSIONS:
            continue
        root_is_bids_dir = rootpath == bids_dir
        for item in files:
            # Skip reserved BIDS files at root level
            if root_is_bids_dir and item in EXCLUSIONS:
                continue
            datafile = BIDSFilePath(bids_dir, pathlib.Path(root, item))
            if datafile.extension in EXTENSIONS_STR:
                continue
            # Metadata file does not apply to this data file if:
            # - Metadata file contains a suffix, and it doesn't match the data file
            # - Data file contains any entities that are *present* in the metadata file
            #   but for which the value doesn't match
            if metafile.suffix is not None and datafile.suffix != metafile.suffix:
                continue
            if any(
                entity.key in metafile_entities_dict
                and entity.value != metafile_entities_dict[entity.key]
                for entity in datafile.entities
            ):
                continue
            initial_result.append(datafile)

    # Perform further pruning of set of data files if necessary
    if EXTENSIONS[metafile.extension].inheritance_behaviour == InheritanceBehaviour.merge:
        return initial_result
    result: list[BIDSFilePath] = []
    for candidate in initial_result:
        try:
            reverse_mapping = metafiles_for_datafile(bids_dir, candidate, ruleset)
        except InheritanceError as e:
            raise InheritanceError(
                "Error in finalising association"
                f" of metadata file {metafile}"
                f" with data file {candidate}"
            ) from e
        assert metafile.extension in reverse_mapping
        if any(
            filepath == candidate for filepath in reverse_mapping[metafile.extension]
        ):
            result.append(candidate)

    return result
