import csv
import json
from itertools import chain, combinations
import logging
import pathlib
import shutil

# import sys
import numpy
from ipfreely.extensions import EXTENSIONS
from ipfreely.filepath import BIDSFilePath
from ipfreely.filepath import BIDSFilePathList
from ipfreely.ruleset import Ruleset
from ipfreely.utils.applicability import is_applicable

logger = logging.getLogger(__name__)


COPY_UNMODIFIED = [
    "code",
    # "dataset_description.json",
    # "derivatives",
    "participants.json",
    "participants.tsv",
    "phenotype",
    "samples.json",
    "samples.tsv",
    "sourcedata",
    # "README.md",
    # "README.rst",
    # "README.txt"
]


CONVERSION_RULESETS = [
    "forbidden",
    # "I1195"
]


def export_forbidden(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:

    for datapath, by_extension in metadata.items():
        parent = out_dir / datapath.relpath.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)
        for extension, content in by_extension.items():
            fullpath = out_dir / datapath.relpath.parent / f"{datapath.stem}{extension}"
            with open(fullpath, "w", encoding="utf-8") as f:
                if EXTENSIONS[extension].is_numerical_matrix:
                    numpy.savetxt(f, numpy.array(content))
                else:
                    if extension == ".json":
                        json.dump(sorted(content), f, indent=4)
                    elif extension == ".tsv":
                        for row in content:
                            f.write("\t".join(row) + "\n")
                    else:
                        assert False


def export_I1195(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    out_dir: pathlib.Path,
) -> None:

    for datapath, by_extension in metadata.items():
        parent = out_dir / datapath.relpath.parent
        if not parent.exists():
            parent.mkdir(parents=True)
        shutil.copyfile(bids_dir / datapath.relpath, out_dir / datapath.relpath)

    # First step: For every unique key-value pair, generate a list of BIDSFilePaths to which it applies
    # Note: This applies exclusively to JSON; will need to do separate for non-JSON
    revkeyvalue: dict[tuple, BIDSFilePathList] = {}
    # For other metadata extensions, key by a tuple of file extension and contents
    revother: dict[tuple, BIDSFilePathList] = {}
    for datapath, by_extension in metadata.items():
        for extension, contents in by_extension.items():
            if extension == ".json":
                for key, value in contents.items():
                    if isinstance(value, list):
                        if isinstance(value[0], list):
                            value = tuple(tuple(row) for row in value)
                        else:
                            value = tuple(value)
                    if (key, value) in revkeyvalue:
                        revkeyvalue[(key, value)].append(datapath)
                    else:
                        revkeyvalue[(key, value)] = [datapath]
            else:
                if isinstance(contents, list):
                    if isinstance(contents[0], list):
                        contents = tuple(tuple(row) for row in contents)
                    else:
                        contents = tuple(contents)
                if (extension, contents) in revother:
                    revother[(extension, contents)].append(datapath)
                else:
                    revother[(extension, contents)] = [datapath]

    # Algorithm presumably will not be of the form of
    #   "find the smallest / largest filename that captures all of these",
    #   since there's no guarantee that there will in fact be a location
    #   that will encapsulate 100% of these files and 0% of other files
    # Consider instead:
    # - Generate a comprehensive list of all candidate metadata file paths
    #   that would capture at least one of these files
    # - For each of these:
    #   - If a data file not in this list would match, reject the candidate immediately
    #   - If no such match, add candidate to a set
    #     indexed by the number of data files in the list that it would be applicable to
    # - Choose the candidate that becomes applicable to the greatest number of such files
    #   (if there's a tie, should choose higher or lower parent? Fewer or more entities?
    #
    # - Remove these from the list, and repeat

    def best_metadata_path(
        remaining_datapaths: list[BIDSFilePath], extension: str
    ) -> BIDSFilePath:

        def all_subsets(ss):
            return chain(*map(lambda x: combinations(ss, x), range(0, len(ss) + 1)))

        # From the set of files left in this list,
        #   generate a list of all plausible metadata paths
        #   that would apply to at least one of these files
        # TODO Eventually, keep track of candidate file paths rejected in previous iterations
        #   for this particular key-value pair
        # TODO Perhaps better: Generate a list of all entities & suffixes across all data files,
        #   and only generate the full set of all subsets of such once.
        # TODO Might be tricky to get the ordering of entities correct in this instance
        # How to deal with data files with the same entity key but different value?
        # Could just concatenate all unique key-value pairs, then look for duplicates in any candidate
        # TODO It's potentially possible that with this current approach,
        #   generating all possible file names in all parents,
        #   that one of the canididates may in fact violate the part of the IP where a metadata file
        #   can't be applicable by name to a file but inapplicable by location
        candidates: set[BIDSFilePath] = set()
        for datapath in remaining_datapaths:
            for parent in datapath.relpath.parents:
                for entities in all_subsets(datapath.entities):
                    candidates.add(
                        BIDSFilePath(parent, list(entities), datapath.suffix, extension)
                    )
        refined_candidates: BIDSFilePathList = {}
        max_matches: int = 0
        for candidate in candidates:
            candidate_eligible: bool = True
            datafile_matches: int = 0
            for datapath in metadata:
                if datapath in remaining_datapaths:
                    if is_applicable(datapath, candidate):
                        datafile_matches += 1
                elif is_applicable(datapath, candidate):
                    candidate_eligible = False
                    break
            if candidate_eligible:
                if datafile_matches > max_matches:
                    max_matches = datafile_matches
                    refined_candidates = [candidate]
                elif datafile_matches == max_matches:
                    refined_candidates.append(candidate)
        # At the very worst this should give a list of sidecars
        #   for the remaining data files;
        #   if it is somehow empty then there's a deficit
        #   in the generation of candidates
        assert refined_candidates

        # Now we need to choose one of the candidates from this list
        # What should our order of selection be?
        # For now, going to go with:
        #   - Lowest in the filesystem hierarchy (ie. modality directory)
        #   - But shortest file name
        # TODO If generating a proposal ruleset where suffixes are optional,
        #   may need to refine this accordingly
        def priority(item: BIDSFilePath) -> int:
            return len(item.entities) - 1024 * len(item.relpath.parents)

        candidate = sorted(refined_candidates, key=priority)[0]
        # TODO If the nominated path is higher in the filesystem hierarchy
        #   than is necessary to capture all datafiles to which it applies,
        #   push it to the lowest common parent
        # TODO Does the change in priority() above resolve?
        return candidate

    # TODO This is currently too slow to be practical
    # What are some hypothetical ways in which this could be sped up?
    # - Generate candidate paths in highest filesystem level only;
    #   if zero plausible candidates are found, choose all directories at the next level down
    # - Limit generation of plausible filesystem paths
    #   Currently every data file generates a full set of all possible entity subsets,
    #   and are relying on rejection of redundant entries after they have been generated;
    #   better would be to generate all possible sets of entities based on all data files
    #   in a single go

    new_json_data: dict[BIDSFilePath, dict] = {}
    for (key, value), datapaths in revkeyvalue.items():
        # Item iterated over should remain immutable
        remaining_datapaths = list(datapaths)
        # Exit loop once there are no data files left to which this key-value metadata should be ascribed
        while remaining_datapaths:
            metapath: BIDSFilePath = best_metadata_path(remaining_datapaths, ".json")
            if metapath in new_json_data:
                assert key not in new_json_data[metapath]
                new_json_data[metapath][key] = value
            else:
                new_json_data[metapath] = {key: value}
            old_count: int = len(remaining_datapaths)
            remaining_datapaths = [
                item
                for item in remaining_datapaths
                if not is_applicable(item, metapath)
            ]
            assert len(remaining_datapaths) < old_count

    new_other_data: dict[BIDSFilePath] = {}
    for (extension, contents), datapaths in revother.items():
        remaining_datapaths = list(datapaths)
        while remaining_datapaths:
            metapath: BIDSFilePath = best_metadata_path(remaining_datapaths, extension)
            assert metapath not in new_other_data
            new_other_data[metapath] = contents
            old_count: int = len(remaining_datapaths)
            remaining_datapaths = [
                item
                for item in remaining_datapaths
                if not is_applicable(item, metapath)
            ]
            assert len(remaining_datapaths) < old_count

    for new_json_filepath, keyvalues in new_json_data.items():
        with open(out_dir / new_json_filepath.relpath, "w", encoding="utf-8") as f:
            json.dump(keyvalues, f, indent=4)
    for new_metapath, content in new_other_data.items():
        with open(out_dir / new_metapath.relpath, "w", encoding="utf-8") as f:
            if EXTENSIONS[new_metapath.extension].is_numerical_matrix:
                numpy.savetxt(f, numpy.array(content))
            else:
                if new_metapath.extension == ".tsv":
                    for row in content:
                        f.write("\t".join(row) + "\n")
                else:
                    assert False


def export(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    ruleset: Ruleset,
    out_dir: pathlib.Path,
) -> None:

    if ruleset.name not in CONVERSION_RULESETS:
        raise TypeError(
            "Only rulesets currently supported for conversion are: "
            + str(CONVERSION_RULESETS)
        )

    out_dir.mkdir()

    for copy_unmodified in COPY_UNMODIFIED:
        fullpath = bids_dir / copy_unmodified
        if fullpath.exists():
            if fullpath.is_file():
                shutil.copyfile(fullpath, out_dir / copy_unmodified)
            elif fullpath.is_dir():
                shutil.copytree(fullpath, out_dir / copy_unmodified)
            else:
                assert False

    with open(bids_dir / "dataset_description.json", "r", encoding="utf-8") as f:
        dataset_description_data = json.load(f)
    if "GeneratedBy" in dataset_description_data:
        dataset_description_data["GeneratedBy"].append("BIDS IP-Freely")
    else:
        dataset_description_data["GeneratedBy"] = ["BIDS IP-Freely"]
    if "SourceDatasets" in dataset_description_data:
        dataset_description_data["SourceDatasets"].append(str(bids_dir))
    else:
        dataset_description_data["SourceDatasets"] = [str(bids_dir)]
    with open(out_dir / "dataset_description.json", "w", encoding="utf-8") as f:
        json.dump(dataset_description_data, f)

    if ruleset.name == "forbidden":
        export_forbidden(bids_dir, metadata, out_dir)
    # elif ruleset.name == "I1195":
    #     export_I1195(bids_dir, metadata, out_dir)
    else:
        assert False
