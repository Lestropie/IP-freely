import pathlib
import sys
from .filepath import BIDSFilePath
from .graph import Graph
from .overrides import get_json_overrides
from .overrides import save_json_overrides
from .returncodes import ReturnCodes
from .ruleset import MetaPathCheck
from .ruleset import Ruleset
from .utils.applicability import is_applicable_nameonly
from .utils.sidecar import is_sidecar_pair


def evaluate(
    bids_dir: pathlib.Path, ruleset: Ruleset, graph: Graph, **kwargs
) -> ReturnCodes:

    export_overrides_path = kwargs.pop("export_overrides", None)
    warnings_as_errors = kwargs.pop("warnings_as_errors", None)
    if kwargs:
        raise TypeError(
            "Unrecognised kwargs passed to ipfreely.evaluate():" f"{kwargs}"
        )

    if graph.errors:
        sys.stderr.write("Errors in building data-metadata association graph:\n")
        for filepath, error_text in graph.errors.items():
            sys.stderr.write(f"    {filepath}:\n        {error_text}\n")
        return ReturnCodes.MALFORMED_DATASET

    return_code: int = ReturnCodes.SUCCESS
    any_inheritance: bool = False
    any_warning: bool = False

    multiinheritance_count_m4d: int = 0
    for _, by_extension in graph.m4d.items():
        multiinheritance_count_m4d += sum(
            (1 if len(metapaths) > 1 else 0) for metapaths in by_extension.values()
        )

    def all_multiinheritance_m4d():
        result: str = ""
        for datapath, by_extension in graph.m4d.items():
            for extension, metapaths in by_extension.items():
                if len(metapaths) > 1:
                    result += (
                        f"    "
                        f"{datapath}: {len(metapaths)} {extension} files:\n"
                        f"        "
                        f"[{'; '.join(str(metapath) for metapath in metapaths)}]\n"
                    )
        return result

    if multiinheritance_count_m4d:
        any_inheritance = True
        instances_found_string: str = (
            f"{multiinheritance_count_m4d}"
            f" instance{'s' if multiinheritance_count_m4d > 1 else ''} found"
            " of multi-metadata-file inheritance for a single data file"
        )
        if ruleset.permit_multiple_metadata_per_data:
            sys.stderr.write(f"{instances_found_string}\n")
        else:
            sys.stderr.write(
                f"{instances_found_string},"
                f" which is not permitted under ruleset {ruleset.name}:\n"
                f"{all_multiinheritance_m4d()}"
            )
            return_code = ReturnCodes.IP_VIOLATION

    multiinheritance_count_d4m: int = sum(
        (1 if len(datapaths) > 1 else 0) for datapaths in graph.d4m.values()
    )
    if multiinheritance_count_d4m:
        any_inheritance = True
        instances_found_string: str = (
            f"{multiinheritance_count_d4m}"
            f" instance{'s' if multiinheritance_count_d4m else ''} found"
            " of metadata files applying to multiple data files"
        )
        if ruleset.permit_multiple_data_per_metadata:
            sys.stderr.write(f"{instances_found_string}\n")
        else:
            sys.stderr.write(
                f"{instances_found_string},"
                f" which is not permitted under ruleset {ruleset.name}:\n"
            )
            for metapath, datapaths in graph.d4m.items():
                if len(datapaths) > 1:
                    sys.stderr.write(
                        f"    {metapath}: {len(datapaths)} files:\n"
                        f"        "
                        f"[{'; '.join(map(str, datapaths))}]\n"
                    )
            return_code = ReturnCodes.IP_VIOLATION

    non_sidecar_exclusive_pairs: list[tuple[BIDSFilePath, BIDSFilePath]] = []
    inapplicable_metafiles: list[BIDSFilePath] = []
    bad_metadata_path: dict[BIDSFilePath, list[BIDSFilePath]] = {}
    for metapath, datapaths in graph.d4m.items():
        if datapaths is not None:
            if not datapaths:
                inapplicable_metafiles.append(metapath)
            elif (
                len(datapaths) == 1
                and len(graph.m4d[datapaths[0]][metapath.extension]) == 1
                and not is_sidecar_pair(metapath, datapaths[0])
            ):
                non_sidecar_exclusive_pairs.append((datapaths[0], metapath))
        # 1.1.2 has a different description to 1.7.0:
        #   Subject-specific files can't be at dataset root,
        #   and subject-agnostic files can't be lower than root
        if ruleset.meta_path_check == MetaPathCheck.ver112:
            if metapath.entities[0].key == "sub":
                if len(metapath.relpath.parents) == 1:
                    bad_metadata_path[metapath] = []
            elif len(metapath.relpath.parents) != 1:
                bad_metadata_path[metapath] = []
        elif ruleset.meta_path_check == MetaPathCheck.ver170:
            # Find any data files to which this metadata file would be applicable
            #   based on file name alone,
            #   but it isn't because it's not in a parent of the data file
            # Unfortunately this is quadratic complexity...
            for datapath in graph.m4d:
                if datapath in datapaths:
                    continue
                # If the metadata path is in a parent directory of the data file,
                #   then we can assume that it was previously checked for applicability,
                #   so the fact that that data file isn't present in "datapaths"
                #   for this metadata file means we don't need to check further
                if metapath.relpath.parent in datapath.relpath.parents:
                    continue
                if is_applicable_nameonly(datapath, metapath):
                    if metapath in bad_metadata_path:
                        bad_metadata_path[metapath].append(datapath)
                    else:
                        bad_metadata_path[metapath] = [datapath]
        else:
            assert False
    if non_sidecar_exclusive_pairs:
        sys.stderr.write(
            f"{len(non_sidecar_exclusive_pairs)} exclusive"
            " data - metadata file pairs that are not sidecars: ["
        )
        for datapath, metapath in non_sidecar_exclusive_pairs:
            sys.stderr.write(f"\n  {datapath} - {metapath}")
        sys.stderr.write("]\n")
        if ruleset.permit_nonsidecar:
            any_warning = True
        else:
            return_code = ReturnCodes.IP_VIOLATION
    if inapplicable_metafiles:
        that_string = (
            "files that are" if len(inapplicable_metafiles) > 1 else "file that is"
        )
        sys.stderr.write(
            f"{len(inapplicable_metafiles)} metadata {that_string}"
            " not applicable to any data file: ["
        )
        for metapath in inapplicable_metafiles:
            sys.stderr.write(f"\n  {metapath}")
        sys.stderr.write("]\n")
        if ruleset.permit_nonsidecar:
            any_warning = True
        else:
            return_code = ReturnCodes.IP_VIOLATION
    if bad_metadata_path:
        sys.stderr.write(
            f"{len(bad_metadata_path)} metadata"
            f" {'file' if len(bad_metadata_path) == 1 else 'files'}"
            " found to match data files in name but not in path: ["
        )
        for metapath, datapaths in bad_metadata_path.items():
            sys.stderr.write(f"\n  {metapath}"
                             f"({len(datapaths)} data"
                             f"{'file' if len(datapaths) == 1 else 'files'})")
        sys.stderr.write("]\n")
        return_code = ReturnCodes.IP_VIOLATION

    json_overrides = get_json_overrides(bids_dir, graph)
    if json_overrides:
        sys.stderr.write(
            f"{len(json_overrides)} data"
            f" {'files have' if len(json_overrides) > 1 else 'file has'}"
            " overridden JSON metadata fields according to Inheritance Principle:"
            f' [{"; ".join(map(str, json_overrides.keys()))}]\n'
        )
        any_warning = True
    if export_overrides_path is not None:
        save_json_overrides(export_overrides_path, json_overrides)

    if not any_inheritance:
        sys.stderr.write("No manifestations of Inheritance Principle found\n")

    if return_code != ReturnCodes.SUCCESS:
        return return_code
    if warnings_as_errors and any_warning:
        sys.stderr.write("Returning non-zero due to treating warnings as errors\n")
        return ReturnCodes.WARNINGS_AS_ERRORS

    return ReturnCodes.SUCCESS
