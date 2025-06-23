import json
import pathlib
import sys
import numpy
from ..filepath import BIDSFilePath
from ..graph import Graph


def inherit_jsons(bids_dir: pathlib.Path, jsonfiles: list[BIDSFilePath]) -> dict[str]:
    sys.stderr.write(
        "Loading multiple JSONs in order:" f" [{list(map(str, jsonfiles))}]\n"
    )
    result: dict[str] = {}
    for jsonfile in jsonfiles:
        with open(bids_dir / jsonfile.relpath, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        for key, value in json_data.items():
            result[key] = value
    return result


def all_metadata(bids_dir: pathlib.Path, graph: Graph) -> dict[str]:
    result: dict[str] = {}
    for datafile, by_extension in graph.m4d.items():
        datafile_metadata: dict[str] = {}
        for extension, metafiles in by_extension.items():
            sys.stderr.write(f"Metafiles to be loaded: {list(map(str, metafiles))}\n")
            if extension == ".json":
                datafile_metadata[".json"] = inherit_jsons(bids_dir, metafiles)
            else:
                # For all other metadata types,
                #   only the last item in the list is used
                metafile = metafiles[-1]
                if extension in (".bvec", ".bval"):
                    datafile_metadata[extension] = numpy.loadtxt(bids_dir / metafile)
                elif extension == ".tsv":
                    datafile_metadata[extension] = str(metafile)
        result[str(datafile)] = datafile_metadata
    return result


def sort_files(metafiles: list[BIDSFilePath]) -> list[BIDSFilePath]:
    def first(one: BIDSFilePath, two: BIDSFilePath) -> bool:
        if two.filepath.parent.is_relative_to(one.filepath.parent):
            return True
        if one.filepath.parent.is_relative_to(two.filepath.parent):
            return False
        return len(one.entities) < len(two.entities)

    return sorted(metafiles, key=first)
