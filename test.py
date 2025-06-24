#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from enum import Enum
import json
import pathlib
import sys
from ipfreely import BIDSError
from ipfreely.evaluate import evaluate
from ipfreely.graph import Graph
from ipfreely.returncodes import ReturnCodes
from ipfreely.ruleset import Ruleset
from ipfreely.ruleset import RULESETS
from ipfreely.utils.keyvalues import find_overrides
from ipfreely.utils.metadata import load_metadata

# Run through a batch of tests,
#   making sure that the outcomes across the set of sample datasets match expectations
# To the greatest extent possible,
#   generate the target outcomes blinded to the behaviour of the software
# If a manually-specified graph is stored in the example dataset,
#   compare the generated graph against it
# For example datasets where the behaviour with respect to
#   metadata file contents is important,
#   verify what is generated from the graph
#   against that manually generated from the expected associated metadata per data file

TestOutcome = Enum("TestOutcome", "success warning violation failure")


@dataclass
class Test:
    ruleset: str
    expectation: TestOutcome


DATASETS = {
    "ip112e1bad": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112e1good": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112e2v1": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112e2v2": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112e3v1": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112e3v2": [
        Test("1.1.x", TestOutcome.warning),
        Test("1.7.x", TestOutcome.warning),
        Test("PR1003", TestOutcome.warning),
        Test("I1195", TestOutcome.warning),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112badmetapathe1": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112badmetapathe2v1": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.violation),
        Test("I1195", TestOutcome.violation),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip112badmetapathe2v2": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip170e1": [
        Test("1.1.x", TestOutcome.warning),
        Test("1.7.x", TestOutcome.warning),
        Test("PR1003", TestOutcome.warning),
        Test("I1195", TestOutcome.warning),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip170e2": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip170e3": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ip170e4": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipabsent": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.success),
    ],
    "ip170badrelpath": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.violation),
        Test("I1195", TestOutcome.violation),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipexclnonsc": [
        Test("1.1.x", TestOutcome.warning),
        Test("1.7.x", TestOutcome.warning),
        Test("PR1003", TestOutcome.warning),
        Test("I1195", TestOutcome.warning),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipi1195e1": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.violation),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipdwi001": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipdwi002": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ipdwi003": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "iploosemeta": [
        Test("1.1.x", TestOutcome.warning),
        Test("1.7.x", TestOutcome.warning),
        Test("PR1003", TestOutcome.warning),
        Test("I1195", TestOutcome.warning),
        Test("forbidden", TestOutcome.violation),
    ],
    "ippr1003ae1": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ippr1003ae2": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.violation),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ippr1003e1v1": [
        Test("1.1.x", TestOutcome.success),
        Test("1.7.x", TestOutcome.success),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
    "ippr1003e1v2": [
        Test("1.1.x", TestOutcome.violation),
        Test("1.7.x", TestOutcome.violation),
        Test("PR1003", TestOutcome.success),
        Test("I1195", TestOutcome.success),
        Test("forbidden", TestOutcome.violation),
    ],
}


def check_dataset_graph(bids_dir: pathlib.Path, graph: Graph) -> bool:
    graph_path = bids_dir / "sourcedata" / "ip_graph.json"
    if graph_path.is_file():
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                ref_graph = json.load(f)
        except json.JSONDecodeError:
            sys.stderr.write(f'Error reading reference graph JSON "{graph_path}"\n')
            raise
        if not graph == ref_graph:
            return False
    metadata_path = bids_dir / "sourcedata" / "ip_metadata.json"
    if metadata_path.is_file():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                ref_metadata = json.load(f)
        except json.JSONDecodeError:
            sys.stderr.write(
                f'Error reading reference metadata JSON "{metadata_path}"\n'
            )
            raise
        data = load_metadata(bids_dir, graph)
        if data != ref_metadata:
            return False
    overrides_path = bids_dir / "sourcedata" / "ip_overrides.json"
    if overrides_path.is_file():
        try:
            with open(overrides_path, "r", encoding="utf-8") as f:
                ref_overrides = json.load(f)
        except json.JSONDecodeError:
            sys.stderr.write(
                f'Error reading reference overrides JSON "{overrides_path}"\n'
            )
            raise
        data = find_overrides(bids_dir, graph)
        data = {str(datapath): list(keys) for datapath, keys in data.items()}
        if data != ref_overrides:
            return False
    return True


def run_test(bids_dir: pathlib.Path, graph: Graph, ruleset: Ruleset) -> TestOutcome:
    return_code = evaluate(bids_dir, ruleset, graph, warnings_as_errors=False)
    if return_code != ReturnCodes.SUCCESS:
        return TestOutcome.violation
    return (
        TestOutcome.warning
        if evaluate(bids_dir, ruleset, graph, warnings_as_errors=True)
        == ReturnCodes.WARNINGS_AS_ERRORS
        else TestOutcome.success
    )
    # TODO For specifically testing,
    #   should ensure that operation of individual functions within utils module
    #   arrive at the same outcomes as does construction of the full graph


def run_dataset_tests(
    bids_dir: pathlib.Path, graph: Graph, tests: list[Test]
) -> list[tuple[Test, TestOutcome]]:
    mismatches: list[tuple[Test, TestOutcome]] = []
    for test in tests:
        ruleset: Ruleset = RULESETS[test.ruleset]
        outcome = run_test(bids_dir, graph, ruleset)
        if outcome != test.expectation:
            mismatches.append((test, outcome))
    return mismatches


def run_datasets(examples_dir: pathlib.Path) -> int:
    # For any test for which the outcome does not match expectation,
    #   store the test along with the actual outcome
    mismatches: list[tuple[str, Test, TestOutcome]] = []
    for dataset, tests in DATASETS.items():
        bids_dir = examples_dir / dataset
        if not bids_dir.is_dir():
            raise FileNotFoundError(f"Missing example BIDS dataset" f" {dataset}")
        graph = Graph(bids_dir)
        dataset_mismatches = run_dataset_tests(bids_dir, graph, tests)
        for dataset_mismatch in dataset_mismatches:
            mismatches.append((dataset, dataset_mismatch[0], dataset_mismatch[1]))
        graph.prune()
        if not check_dataset_graph(bids_dir, graph):
            mismatches.append(
                (
                    dataset,
                    Test("verify_graph", TestOutcome.success),
                    TestOutcome.failure,
                )
            )

    if mismatches:
        sys.stderr.write(f"{len(mismatches)} discrepancies in test outcomes:\n")

        def outcome2str(outcome: TestOutcome) -> str:
            if outcome is TestOutcome.success:
                return "success"
            if outcome is TestOutcome.warning:
                return "warning"
            if outcome is TestOutcome.violation:
                return "violation"
            if outcome is TestOutcome.failure:
                return "failure"
            assert False

        for mismatch in mismatches:
            sys.stderr.write(
                f"    Dataset: {mismatch[0]},"
                f" ruleset: {mismatch[1].ruleset},"
                f" expected {outcome2str(mismatch[1].expectation)};"
                f" actual outcome {outcome2str(mismatch[2])}\n"
            )
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Test suite for IP-Freely")
    parser.add_argument(
        "examples_dir",
        help="A directory containing the BIDS example datasets",
    )

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit()

    examples_dir = pathlib.Path(args.examples_dir)
    if not examples_dir.is_dir():
        sys.stderr.write(f"Input BIDS examples directory {args.examples_dir} not found")
        sys.exit(1)

    return run_datasets(examples_dir)


if __name__ == "__main__":
    main()
