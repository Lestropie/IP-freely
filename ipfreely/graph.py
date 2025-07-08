import json
import os
import pathlib

# import sys
from . import BIDSError
from . import EXCLUSIONS
from .extensions import EXTENSIONS
from .extensions import InheritanceBehaviour
from .filepath import BIDSFilePath
from .filepath import BIDSFilePathList
from .utils.get import metafiles_for_datafile


class Graph:
    def __init__(self, bids_dir: pathlib.Path):
        self.bids_dir = bids_dir
        # "m4d" is a lookup by data file path
        # The resulting dictionary indexes by metadata file extension:
        #   the contents of each of those is then a list of metadata file paths
        #   that are associated with that data file
        self.m4d: dict[BIDSFilePath, dict[str, BIDSFilePathList]] = {}
        # "d4m" is a lookup by metadata file path
        # The contents of each of those fields is a list of data file paths
        #   for which that metadata file is applicable
        self.d4m: dict[BIDSFilePath, BIDSFilePathList] = {}
        for root, _, files in os.walk(bids_dir):
            rootpath = pathlib.Path(root)
            if rootpath.name in EXCLUSIONS:
                continue
            root_is_bids_dir = rootpath == bids_dir
            for item in files:
                if root_is_bids_dir and item in EXCLUSIONS:
                    continue
                filepath = BIDSFilePath(bids_dir, rootpath / item)
                if filepath.is_metadata():
                    if filepath not in self.d4m:
                        self.d4m[filepath] = []
                    continue
                # Default: Function accesses all metadata file extensions
                all_metapaths = metafiles_for_datafile(
                    bids_dir, filepath, prune=False, ruleset=None
                )
                self.m4d[filepath] = all_metapaths
                # Add the inverse mapping
                for _, metapaths in all_metapaths.items():
                    for metapath in metapaths:
                        if metapath in self.d4m:
                            self.d4m[metapath].append(filepath)
                        else:
                            self.d4m[metapath] = [filepath]

    # Function to prune graph
    # This needs to happen *after* graph construction,
    #   as it needs to be possible to detect occurrences of inheritance clashes
    #   in case that would be a violation of the ruleset
    # This also changes eg. m4d[datapath][".bvec"]
    #   to be a BIDSFilePath rather than BIDSFilePathList
    def prune(self) -> None:
        # Identify data file - metadata extension associations
        #   for which only the last metadata file is applicable
        new_m4d: dict[BIDSFilePath, dict[str, BIDSFilePathList]] = {}
        # All metadata files need to remain in this mapping,
        #   even if after pruning it does not map to any data files
        self.d4m = {metapath: [] for metapath in self.d4m}
        for datapath, by_extension in self.m4d.items():
            new_m4d[datapath] = {}
            for extension, metapaths in by_extension.items():
                if (
                    EXTENSIONS[extension].inheritance_behaviour
                    == InheritanceBehaviour.merge
                ):
                    new_m4d[datapath][extension] = metapaths
                    for metapath in metapaths:
                        self.d4m[metapath].append(datapath)
                    continue
                if (
                    EXTENSIONS[extension].inheritance_behaviour
                    == InheritanceBehaviour.forbidden
                ):
                    if len(self.m4d[datapath][extension]) > 1:
                        raise BIDSError(
                            "Attempt to prune invalid metadata association graph:"
                            f" ({datapath.relpath} has multiple applicable"
                            f" {extension} metadata files)"
                        )
                    # Change from a list of metapaths of length 1 to a metapath
                    new_m4d[datapath][extension] = metapaths[0]
                    self.d4m[metapaths[0]].append(datapath)
                    continue
                if (
                    EXTENSIONS[extension].inheritance_behaviour
                    == InheritanceBehaviour.nearest
                ):
                    # Make sure there isn't any ambiguity in which to select
                    if (
                        len(metapaths) > 1
                        and not (metapaths[-2] < metapaths[-1])
                        and not (metapaths[-1] < metapaths[-2])
                    ):
                        raise BIDSError(
                            "Attempt to prune invalid metadata association graph:"
                            f" ({datapath.relpath} has ambiguous applicable"
                            f"{extension} file"
                        )
                    new_m4d[datapath][extension] = metapaths[-1]
                    self.d4m[metapaths[-1]].append(datapath)
                    continue
                assert False
        self.m4d = new_m4d

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

    def __eq__(self, ref: dict[str]) -> bool:
        # Note that "ref" here is a dictionary
        #   that is no longer split by direction of association
        for datafile, by_extension in self.m4d.items():
            if str(datafile) not in ref:
                # sys.stderr.write(f"{datafile} not in reference\n")
                return False
            ref_by_extension = ref[str(datafile)]
            missing_extensions = [
                extension
                for extension in ref_by_extension.keys()
                if extension not in by_extension
            ]
            if missing_extensions:
                # sys.stderr.write(f"For {datafile}, extensions {missing_extensions} in reference not in graph\n")
                return False
            for extension, metafiles in by_extension.items():
                if extension not in ref_by_extension:
                    # sys.stderr.write(f"For {datafile}, extension {extension} in graph not in reference\n")
                    return False
                if isinstance(metafiles, BIDSFilePath):
                    if str(metafiles) != ref_by_extension[extension]:
                        # sys.stderr.write(f"For {datafile}, extension {extension},"
                        #                  f" graph file {metafiles} != reference file {ref_by_extension[extension]}\n")
                        return False
                    continue
                assert isinstance(metafiles, BIDSFilePathList)
                # Perform test for equivalence of lists,
                #   accounting for arbitrary ordering of items that are tied
                #   in filesystem location and # entities
                ref_paths: BIDSFilePathList = [
                    BIDSFilePath(pathlib.Path(os.sep), pathlib.Path(os.sep, ref_path))
                    for ref_path in ref_by_extension[extension]
                ]
                if not metafiles == ref_paths:
                    # sys.stderr.write(f"For {datafile}, extension {extension},"
                    #                  f" graph files {metafiles} != reference files {ref_paths}\n")
                    return False
        for metafile, datafiles in self.d4m.items():
            if str(metafile) not in ref:
                # sys.stderr.write(f"Metadata file {metafile} not in reference\n")
                return False
            ref_datafiles = ref[str(metafile)]
            if any(str(datafile) not in ref_datafiles for datafile in datafiles) or any(
                not any(ref_datafile == str(datafile) for datafile in datafiles)
                for ref_datafile in ref_datafiles
            ):
                # sys.stderr.write(f"Metadata file {metafile}, graph and reference inequal:\n"
                #                  f"  {datafiles} != {ref_datafiles}\n")
                return False
        # Any files (data or metadata) in the reference graph absent in this graph
        if any(
            (
                not any(ref_originfile == str(datafile) for datafile in self.m4d)
                and not any(ref_originfile == str(metafile) for metafile in self.d4m)
            )
            for ref_originfile in ref
        ):
            # sys.stderr.write(f"Files in reference absent from graph:\n"
            #                  f"  {self.m4d.keys() + self.d4m.keys()}\n"
            #                  "  !=\n"
            #                  f"  {ref.keys()}\n")
            return False
        return True
