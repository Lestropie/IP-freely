#!/usr/bin/env python3

import argparse
import json
import logging
import os
import pathlib
import sys
from ipfreely.evaluate import evaluate
from ipfreely.export import export
from ipfreely.extensions import EXTENSIONS
from ipfreely.filepath import BIDSError
from ipfreely.filepath import BIDSFilePath
from ipfreely.graph import Graph
from ipfreely.returncodes import ReturnCodes
from ipfreely.ruleset import RULESETS
from ipfreely.utils.get import metafiles_for_datafile
from ipfreely.utils.get import datafiles_for_metafile
from ipfreely.utils.keyvalues import load_keyvalues
from ipfreely.utils.metadata import load_metadata
from ipfreely.utils.metadata import load_numerical_matrix
from ipfreely.utils.metadata import load_tsv

logger = logging.getLogger(__name__)

__version__ = open(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "version"),
    encoding="ascii",
).read()  # pylint: disable=consider-using-with


def graph2json_manual(bids_dir: pathlib.Path, graph: Graph, outpath: str) -> None:
    data = {}
    for datapath in graph.m4d.keys():
        metapaths_by_extension = metafiles_for_datafile(bids_dir, datapath)
        data[str(datapath)] = {}
        for extension, metapaths in metapaths_by_extension.items():
            data[str(datapath)][extension] = (
                str(metapaths)
                if isinstance(metapaths, BIDSFilePath)
                else list(map(str, metapaths))
            )
    for metapath in graph.d4m.keys():
        data[str(metapath)] = list(map(str, datafiles_for_metafile(bids_dir, metapath)))
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def metadata2json_manual(bids_dir: pathlib.Path, graph: Graph, outpath: str) -> None:
    data = {}
    for datapath in graph.m4d.keys():
        data[str(datapath)] = {}
        metapaths_by_extension = metafiles_for_datafile(bids_dir, datapath)
        for extension, metapaths in metapaths_by_extension.items():
            if extension not in metapaths_by_extension:
                continue
            if extension == ".json":
                data[str(datapath)][".json"] = load_keyvalues(bids_dir, metapaths)
            elif EXTENSIONS[extension].is_numerical_matrix():
                data[str(datapath)][extension] = load_numerical_matrix(
                    bids_dir,
                    metapaths if isinstance(metapaths, BIDSFilePath) else metapaths[-1],
                )
            elif extension == ".tsv":
                data[str(datapath)][extension] = load_tsv(
                    bids_dir,
                    metapaths if isinstance(metapaths, BIDSFilePath) else metapaths[-1],
                )
            else:
                assert False
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def main():

    parser = argparse.ArgumentParser(
        description="IP-Freely: BIDS Inheritance Principle tooling"
    )
    parser.add_argument(
        "bids_dir",
        help="A directory containing a dataset "
        "formatted according to the BIDS standard.",
    )
    # TODO Eventually give opportunity to modify in-place
    # TODO Eventually give opportunity to create the new dataset
    #   by softlinking to the input dataset rather than duplicating data files
    parser.add_argument(
        "-c",
        "--convert",
        help="Convert a dataset to conform to a different Inheritance Principle ruleset",
        nargs=2,
        metavar=["ruleset", "path"],
    )
    parser.add_argument(
        "-g",
        "--graph",
        help="Save the full data-metadata filesystem association graph"
        " to a JSON file.",
    )
    parser.add_argument("-l", "--log", help=("Write a detailed log to file"))
    parser.add_argument(
        "-m",
        "--metadata",
        help="Save the aggregate metadata associated with all data files"
        " to a JSON file.",
    )
    parser.add_argument(
        "-o",
        "--overrides",
        help="Save information about presence of key-value metadata field overrides"
        " to a JSON file.",
    )
    parser.add_argument(
        "-r",
        "--ruleset",
        help="Analyse the dataset under a specific IP ruleset.",
        choices=RULESETS.keys(),
    )
    parser.add_argument(
        "-w",
        "--warnings-as-errors",
        action="store_true",
        help="Treat warnings as errors by yielding a non-zero return code.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"IP-Freely version {__version__}",
    )

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        sys.stderr.write(f"Error parsing command-line: {e}\n")
        sys.exit()

    bids_dir = pathlib.Path(args.bids_dir)
    if not bids_dir.is_dir():
        sys.stderr.write(f"Input BIDS directory {args.bids_dir} not found\n")
        sys.exit(ReturnCodes.NO_DATASET)

    logger_kwargs: dict[str] = {"level": logging.INFO}
    if args.log:
        logger_kwargs["filename"] = args.log
    logging.basicConfig(**logger_kwargs)

    if args.ruleset:
        ruleset = RULESETS[args.ruleset]
    else:
        dataset_description_path = bids_dir / "dataset_description.json"
        try:
            with open(dataset_description_path, "r") as f:
                bids_version_string = json.load(f)["BIDSVersion"]
        except FileNotFoundError:
            sys.stderr.write(
                f'No "dataset_desciption.json" found for BIDS dataset {bids_dir}'
                " and no ruleset requested at command-line;"
                " do not know what ruleset to apply"
            )
            sys.exit(ReturnCodes.NO_RULESET)
        except KeyError:
            sys.stderr.write(
                'No "BIDSVersion" key in file dataset_description.json'
                f" for BIDS dataset {bids_dir};"
                " and no ruleset requested at command-line;"
                " do not know what ruleset to apply"
            )
            sys.exit(ReturnCodes.NO_RULESET)
        if bids_version_string == "Pull Request 1003":
            ruleset = RULESETS["PR1003"]
        elif bids_version_string == "Issue 1195":
            ruleset = RULESETS["I1195"]
        else:
            try:
                bids_version = tuple(int(i) for i in bids_version_string.split("."))
            except TypeError:
                sys.stderr.write(
                    "Unable to determine appropriate ruleset"
                    f' based on BIDSVersion string "{bids_version_string}"'
                    f" for BIDS dataset {bids_dir}"
                )
                sys.exit(ReturnCodes.NO_RULESET)
            if bids_version < (1, 7):
                ruleset_str = "1.1.x"
            elif bids_version < (1, 11):
                ruleset_str = "1.7.x"
            else:
                ruleset_str = "1.11.x"
            ruleset = RULESETS[ruleset_str]
            logger.info(
                f"For BIDSVersion of {bids_version_string},"
                f" chose ruleset {ruleset.name}"
            )

    if args.convert is not None:
        if args.convert[0] not in RULESETS:
            sys.stderr.write(
                f'Unsupported ruleset "{args.convert[0]}" nominated for conversion\n'
            )
            sys.exit(1)
        args.convert[1] = pathlib.Path(args.convert[1])
        if args.convert[1].exists():
            sys.stderr.write(
                f'Output conversion path "{args.convert[1]}" already exists\n'
            )
            sys.exit(1)

    evaluate_kwargs = {}
    if args.overrides is not None:
        evaluate_kwargs["export_overrides"] = args.overrides
    if args.warnings_as_errors is not None:
        evaluate_kwargs["warnings_as_errors"] = args.warnings_as_errors

    try:
        graph: Graph = Graph(bids_dir)
        return_code: ReturnCodes = evaluate(bids_dir, ruleset, graph, **evaluate_kwargs)
    except BIDSError as e:
        logger.critical(f"Error parsing BIDS dataset: {e}\n")
        sys.exit(ReturnCodes.MALFORMED_DATASET)

    if args.graph is not None:
        graph.save(args.graph)
        # graph2json_manual(bids_dir, graph, args.graph)

    if args.convert is not None or args.metadata is not None:
        metadata = load_metadata(bids_dir, graph)

    if args.metadata is not None:
        temp = {str(datapath): contents for datapath, contents in metadata.items()}
        with open(args.metadata, "w", encoding="utf-8") as f:
            json.dump(temp, f, indent=4)
        # metadata2json_manual(bids_dir, graph, args.metadata)

    if args.convert is not None:
        export(bids_dir, metadata, RULESETS[args.convert[0]], args.convert[1])

    return return_code


if __name__ == "__main__":
    main()
