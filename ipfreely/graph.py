import json
import os
import pathlib
from . import EXCLUSIONS
from .filepath import BIDSFilePath
from .ruleset import Ruleset
from .utils.get import metafiles_for_datafile


class Graph:
    def __init__(self, bids_dir: pathlib.Path):
        self.bids_dir = bids_dir
        # "m4d" is a lookup by data file path
        # The resulting dictionary indexes by metadata file extension:
        #   the contents of each of those is then a list of metadata file paths
        #   that are associated with that data file
        self.m4d: dict[BIDSFilePath, dict[str, list[BIDSFilePath]]] = {}
        # "d4m" is a lookup by metadata file path
        # The contents of each of those fields is a list of data file paths
        #   for which that metadata file is applicable
        self.d4m: dict[BIDSFilePath, list[BIDSFilePath]] = {}
        for root, _, files in os.walk(bids_dir):
            rootpath = pathlib.Path(root)
            if rootpath.name in EXCLUSIONS:
                continue
            root_is_bids_dir = rootpath == bids_dir
            for item in files:
                if root_is_bids_dir and item in EXCLUSIONS:
                    continue
                datapath = BIDSFilePath(bids_dir, rootpath / item)
                if datapath.is_metadata():
                    # This is just a convenient initialisation of all required lists
                    #   for the second part of the class initialiser
                    self.d4m[datapath] = []
                    continue
                # Default: Function accesses all metadata file extensions
                self.m4d[datapath] = metafiles_for_datafile(bids_dir, datapath)

        # Invert the metadata-for-data mapping
        #   to produce the data-for-metadata mapping
        for datapath, m4d in self.m4d.items():
            for _, metapaths in m4d.items():
                for metapath in metapaths:
                    assert metapath in self.d4m
                    self.d4m[metapath].append(datapath)

    # TODO Function to prune graph (/ yield a pruned graph)
    # This needs to happen *after* graph construction,
    #   as it needs to be possible to detect occurrences of inheritance clashes
    #   in case that would be a violation of the ruleset
    # This could possibly also change eg. m4d[datapath][".bvec"]
    #   to be a BIDSFilePath rather than list[BIDSFilePath]

    def save(self, outpath: pathlib.Path) -> None:
        json_data = {}
        for datafile, by_extension in sorted(self.m4d.items()):
            if by_extension is None:
                json_data[str(datafile)] = None
                continue
            json_data[str(datafile)] = {}
            for extension, metafiles in sorted(by_extension.items()):
                json_data[str(datafile)][extension] = list(map(str, sorted(metafiles)))
        for metafile, datafiles in sorted(self.d4m.items()):
            json_data[str(metafile)] = list(map(str, sorted(datafiles)))
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)

    # TODO Is knowledge of the ruleset really required here?
    # Could permit ambiguity where possible regardless,
    #   with the invalidity of the graph handled elsewhere?
    def is_equal(self, ref: dict[str], _: Ruleset) -> bool:
        # Note that "ref" here is a dictionary
        #   that is no longer split by direction of association
        for datafile, by_extension in self.m4d.items():
            if str(datafile) not in ref:
                return False
            ref_by_extension = ref[str(datafile)]
            if any(
                extension not in by_extension for extension in ref_by_extension.keys()
            ):
                return False
            for extension, metafiles in by_extension.items():
                if extension not in ref_by_extension:
                    return False
                if any(
                    str(metafile) not in ref_by_extension[extension]
                    for metafile in metafiles
                ) or any(
                    not any(ref_metafile == str(metafile) for metafile in metafiles)
                    for ref_metafile in ref_by_extension[extension]
                ):
                    return False
                # TODO Implement check for equivalent ordering (if necessary)
        for metafile, datafiles in self.d4m.items():
            if str(metafile) not in ref:
                return False
            ref_datafiles = ref[str(metafile)]
            if any(str(datafile) not in ref_datafiles for datafile in datafiles) or any(
                not any(ref_datafile == str(datafile) for datafile in datafiles)
                for ref_datafile in ref_datafiles
            ):
                return False
        # Any files (data or metadata) in the reference graph absent in this graph
        if any(
            (
                not any(ref_originfile == str(datafile) for datafile in self.m4d)
                and not any(ref_originfile == str(metafile) for metafile in self.d4m)
            )
            for ref_originfile in ref
        ):
            return False
        return True
