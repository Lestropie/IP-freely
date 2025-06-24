import json
import pathlib
import sys
from .. import BIDSError
from ..filepath import BIDSFilePath
from ..graph import Graph


def load_keyvalues(bids_dir: pathlib.Path, jsonfiles: list[BIDSFilePath]) -> dict[str]:
    result: dict[str] = {}
    for jsonfile in jsonfiles:
        try:
            with open(bids_dir / jsonfile.relpath, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except json.JSONDecodeError as e:
            raise BIDSError(f"Malformed key-value metadata file {jsonfile}") from e
        for key, value in json_data.items():
            result[key] = value
    return result


# Returns a dictionary,
#   whose cardinality is the number of data files
#   that experience JSON metadata field overrides,
#   and each filepath contains a set of those metadata keys with overrides
def find_overrides(
    bids_dir: pathlib.Path, graph: Graph
) -> dict[BIDSFilePath, set[str]]:
    all_results: dict[BIDSFilePath, set[str]] = {}
    for datafile, by_extension in graph.m4d.items():
        if ".json" not in by_extension:
            continue
        if len(by_extension[".json"]) < 2:
            continue
        # Don't care about what the actual contents of the metadata fields are;
        #   only care about whether the same key is specified more than once
        fields: set[str] = set()
        clashes: set[str] = set()
        for metafile in by_extension[".json"]:
            with open(bids_dir / metafile.relpath, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            for field in json_data.keys():
                if field in fields:
                    clashes.add(field)
                fields.add(field)
        if clashes:
            all_results[datafile] = clashes
    return all_results


def save_overrides(filepath: pathlib.Path, data: dict[BIDSFilePath, set[str]]) -> None:
    json_data = {}
    for datapath, clashes in data.items():
        json_data[str(datapath)] = sorted(clashes)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(json_data, f, sort_keys=True, indent=4)
