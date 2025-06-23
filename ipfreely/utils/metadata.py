import pathlib
import numpy
from ..extensions import EXTENSIONS
from ..graph import Graph
from .keyvalues import load_keyvalues


def load_metadata(bids_dir: pathlib.Path, graph: Graph) -> dict[str]:
    result: dict[str] = {}
    for datafile, by_extension in graph.m4d.items():
        datafile_metadata: dict[str] = {}
        for extension, metafiles in by_extension.items():
            if extension == ".json":
                datafile_metadata[".json"] = load_keyvalues(bids_dir, metafiles)
            else:
                # For all other metadata types,
                #   only the last item in the list is used
                metafile = metafiles[-1]
                if EXTENSIONS[extension].is_numerical_matrix:
                    datafile_metadata[extension] = numpy.loadtxt(bids_dir / metafile)
                else:
                    datafile_metadata[extension] = str(metafile)
        result[str(datafile)] = datafile_metadata
    return result
