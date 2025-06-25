import os
import pathlib
from .. import InheritanceError
from .. import EXCLUSIONS
from ..filepath import BIDSFilePath
from ..filepath import BIDSFilePathList
from ..extensions import EXTENSIONS
from ..extensions import EXTENSIONS_STR
from ..extensions import InheritanceBehaviour
from ..ruleset import MetaPathCheck
from ..ruleset import RULESETS
from .applicability import is_applicable
from .sidecar import is_sidecar_pair


def metafiles_for_datafile(
    bids_dir: pathlib.Path, datafile: BIDSFilePath, **kwargs
) -> dict[str, BIDSFilePathList]:

    single_extension = kwargs.pop("extension", None)
    extensions = kwargs.pop("extensions", None)
    prune = bool(kwargs.pop("prune", True))
    ruleset = kwargs.pop("ruleset", None)
    if kwargs:
        raise TypeError(
            "Unrecognised kwargs to metafiles_for_datafile():" f" {kwargs.keys()}"
        )
    if single_extension is not None and extensions is not None:
        raise TypeError(
            'Do not specify both "extension=" and "extensions="'
            " to metafiles_for_datafile()"
        )
    if single_extension is not None:
        assert single_extension in EXTENSIONS_STR
        extensions = {single_extension: EXTENSIONS[single_extension]}
    if extensions is None:
        extensions = EXTENSIONS
    else:
        assert all(item in EXTENSIONS_STR for item in extensions)
        extensions = dict([item, EXTENSIONS[item]] for item in extensions)
    if ruleset is not None:
        try:
            ruleset = RULESETS[ruleset]
        except KeyError:
            # pylint: disable=raise-missing-from
            raise TypeError(
                f'Invalid IP ruleset "{ruleset}"'
                " nominated for metafiles_for_datafile()"
            )

    # Generate a list of directories in which the search will occur
    # This is all parents of the data file,
    #   including the directory in which it resides,
    #   but does not include anything beyond the BIDS root directory
    parents = [bids_dir / parent for parent in datafile.relpath.parents]

    initial_result: dict[str, BIDSFilePathList] = {}

    # Start at the highest level in the filesystem hierarchy
    for parent in reversed(parents):

        # Get all matches just at this level of the filesystem hierarchy
        dir_matches: dict[str, BIDSFilePathList] = {}

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
            if extension in initial_result:
                initial_result[extension].extend(BIDSFilePathList(sorted(filepaths)))
            else:
                initial_result[extension] = BIDSFilePathList(sorted(filepaths))

    # Ensure that the IP was not violated
    #   in the process of ascribing these metadata file paths to this data file
    if ruleset is not None:
        for extension, metapaths in initial_result:
            if metapaths.has_order_ambiguity(
                ruleset.json_inheritance_within_dir
                if extension == ".json"
                else ruleset.nonjson_inheritance_within_dir
            ):
                raise InheritanceError
            if not ruleset.permit_multiple_metadata_per_data and len(metapaths) > 1:
                raise InheritanceError
        if not ruleset.permit_multiple_data_per_metadata:
            for metapath in metapaths:
                d4m = datafiles_for_metafile(bids_dir, metapath, ruleset=None)
                if not (len(d4m) == 1 and d4m[0] == datafile):
                    raise InheritanceError
        if not ruleset.permit_nonsidecar and not (
            len(metapaths) == 1 and is_sidecar_pair(datafile, metapaths[0])
        ):
            raise InheritanceError
        if ruleset.meta_path_check == MetaPathCheck.ver112:
            for metapath in metapaths:
                if metapath.entities and metapath.entities[0].key == "sub":
                    if len(metapath.relpath.parents) == 1:
                        raise InheritanceError
                elif len(metapath.relpath.parents) != 1:
                    raise InheritanceError
        # Rules in 1.7.0 regarding relative paths between data and metadata files
        #   too expensive to be checking for each file individually here

    if not prune:
        return initial_result
    result: dict[str] = {}
    for extension, metapaths in initial_result.items():
        if (
            EXTENSIONS[extension].inheritance_behaviour
            == InheritanceBehaviour.forbidden
        ):
            if len(metapaths) != 1:
                raise InheritanceError
            result[extension] = metapaths[0]
        elif (
            EXTENSIONS[extension].inheritance_behaviour == InheritanceBehaviour.nearest
        ):
            result[extension] = metapaths[-1]
        elif EXTENSIONS[extension].inheritance_behaviour == InheritanceBehaviour.merge:
            result[extension] = metapaths
        else:
            assert False
    return result


def datafiles_for_metafile(
    bids_dir: pathlib.Path, metafile: BIDSFilePath, **kwargs
) -> BIDSFilePathList:

    prune = bool(kwargs.pop("prune", True))
    ruleset = kwargs.pop("ruleset", None)
    if kwargs:
        raise TypeError(
            "Unrecognised kwargs to datafiles_for_metafile():" f" {kwargs.keys()}"
        )
    if ruleset is not None:
        try:
            ruleset = RULESETS[ruleset]
        except KeyError:
            raise TypeError("Invalid IP ruleset nominated for metafiles_for_datafile()")

    if ruleset is not None and ruleset.meta_path_check == MetaPathCheck.ver112:
        if metafile.entities and metafile.entities[0].key == "sub":
            if len(metafile.relpath.parents) == 1:
                raise InheritanceError
        elif len(metafile.relpath.parents) != 1:
            raise InheritanceError

    initial_result: BIDSFilePathList = []
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
            if not is_applicable(datafile, metafile):
                continue
            initial_result.append(datafile)

    # Ensure that the IP was not violated
    #   in the process of ascribing these metadata files to this data file
    if (
        ruleset is not None
        and (
            not ruleset.permit_multiple_metadata_per_data
            or not ruleset.permit_nonsidecar
        )
        and len(initial_result) > 1
    ):
        raise InheritanceError

    if ruleset is None and (
        not prune
        or EXTENSIONS[metafile.extension].inheritance_behaviour
        == InheritanceBehaviour.merge
    ):
        return initial_result

    result: BIDSFilePathList = []
    for datapath in initial_result:
        try:
            m4d = metafiles_for_datafile(bids_dir, datapath, ruleset=None)
        except InheritanceError as e:
            raise InheritanceError(
                "Error in finalising association"
                f" of metadata file {metafile}"
                f" with data file {datapath}"
            ) from e
        assert metafile.extension in m4d
        m4d = m4d[metafile.extension]
        if (
            ruleset is not None
            and not ruleset.permit_multiple_metadata_per_data
            and len(m4d) != 1
        ):
            raise InheritanceError
        if isinstance(m4d, BIDSFilePath):
            if m4d == metafile:
                result.append(datapath)
        elif isinstance(m4d, BIDSFilePathList):
            if any(filepath == datapath for filepath in m4d):
                result.append(datapath)
        else:
            assert False
    return result
