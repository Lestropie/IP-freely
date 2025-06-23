import json
import pathlib
from .filepath import BIDSFilePath
from .graph import Graph


# Returns a dictionary,
#   whose cardinality is the number of data files
#   that experience JSON metadata field overrides,
#   and each filepath contains a set of those metadata keys with overrides
def get_json_overrides(
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


def save_json_overrides(
    filepath: pathlib.Path, data: dict[BIDSFilePath, set[str]]
) -> None:
    json_data = {}
    for datapath, clashes in data.items():
        json_data[str(datapath)] = sorted(clashes)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(json_data, f, sort_keys=True, indent=4)
