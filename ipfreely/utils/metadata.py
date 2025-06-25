import csv
import pathlib
import numpy
from .. import BIDSError
from ..extensions import EXTENSIONS
from ..filepath import BIDSFilePath
from ..graph import Graph
from .keyvalues import load_keyvalues


def load_metadata(bids_dir: pathlib.Path, graph: Graph) -> dict[str]:

    def nearest_metapath(metapaths) -> BIDSFilePath:
        if isinstance(metapaths, BIDSFilePath):
            return metapaths
        if isinstance(metapaths, list):
            if not isinstance(metapaths[0], BIDSFilePath):
                raise TypeError
            return metapaths[-1]
        raise TypeError

    result: dict[str] = {}
    for datafile, by_extension in graph.m4d.items():
        datafile_metadata: dict[str] = {}
        for extension, metapaths in by_extension.items():
            # For JSON key-value metadata,
            #   need to load data from across all of these files;
            #   for all other metadata types,
            #   only the last item in the list is used
            if extension == ".json":
                datafile_metadata[".json"] = load_keyvalues(bids_dir, metapaths)
            elif extension == ".tsv":
                datafile_metadata[extension] = load_tsv(
                    bids_dir, nearest_metapath(metapaths)
                )
            elif EXTENSIONS[extension].is_numerical_matrix:
                datafile_metadata[extension] = load_numerical_matrix(
                    bids_dir, nearest_metapath(metapaths)
                )
            else:
                assert False
        result[str(datafile)] = datafile_metadata
    return result


def load_numerical_matrix(bids_dir: pathlib.Path, metapath: BIDSFilePath) -> list:
    try:
        # numpy.ndarray not JSON serialisable;
        #   convert to Python native list / list-of-lists
        return numpy.loadtxt(bids_dir / metapath.relpath).tolist()
    except ValueError as e:
        raise BIDSError(f"Malformed numerical matrix metadata file {metapath}") from e


def load_tsv(bids_dir: pathlib.Path, metapath: BIDSFilePath) -> list:
    result = []
    with open(bids_dir / metapath, "r", encoding="utf-8") as f:
        rd = csv.reader(f, delimiter="\t")
        for row in rd:
            result.append(row)
    if not (len(row) == len(result[0]) for row in result[1:]):
        raise BIDSError(
            f"Malformed .tsv metadata file {metapath}"
            " (inconsistent number of columns)"
        )
    return result
