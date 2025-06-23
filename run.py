#!/usr/bin/env python3

import argparse
import json
import os
import pathlib
import sys
from ipfreely.evaluate import evaluate
from ipfreely.filepath import BIDSError
from ipfreely.graph import Graph
from ipfreely.returncodes import ReturnCodes
from ipfreely.ruleset import RULESETS
from ipfreely.utils.keyvalues import load_all


__version__ = open(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "version"),
    encoding="ascii",
).read()  # pylint: disable=consider-using-with


def main():

    parser = argparse.ArgumentParser(
        description="IP-Freely: BIDS Inheritance Principle tooling"
    )
    parser.add_argument(
        "bids_dir",
        help="A directory containing a dataset "
        "formatted according to the BIDS standard.",
    )
    parser.add_argument(
        "-g",
        "--graph",
        help="Save the full data-metadata filesystem association graph"
        " to a JSON file.",
    )
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
        sys.stderr.write(f"{e}\n")
        sys.exit()

    bids_dir = pathlib.Path(args.bids_dir)
    if not bids_dir.is_dir():
        sys.stderr.write(f"Input BIDS directory {args.bids_dir} not found")
        sys.exit(ReturnCodes.NO_DATASET)

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
                bids_version = tuple(int(i) for i in bids_version_string.aplit("."))
            except TypeError:
                sys.stderr.write(
                    "Unable to determine appropriate ruleset"
                    f' based on BIDSVersion string "{bids_version_string}"'
                    f" for BIDS dataset {bids_dir}"
                )
                sys.exit(ReturnCodes.NO_RULESET)
            ruleset = RULESETS["1.1.x"] if bids_version < (1, 7) else RULESETS["1.7.x"]

    evaluate_kwargs = {}
    if args.overrides is not None:
        evaluate_kwargs["export_overrides"] = args.overrides
    if args.warnings_as_errors is not None:
        evaluate_kwargs["warnings_as_errors"] = args.warnings_as_errors

    try:
        graph: Graph = Graph(bids_dir, ruleset)
        return_code: ReturnCodes = evaluate(bids_dir, ruleset, graph, **evaluate_kwargs)
    except BIDSError as e:
        sys.stderr.write(f"Error parsing BIDS dataset: {e}\n")
        sys.exit(ReturnCodes.MALFORMED_DATASET)

    if args.graph is not None:
        graph.save(args.graph)

    if args.metadata is not None:
        data = load_all(bids_dir, graph)
        with open(args.metadata, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    return return_code


if __name__ == "__main__":
    main()
