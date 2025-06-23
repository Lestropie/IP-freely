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
from ipfreely.utils.keyvalues import load_all

# Run through a batch of tests,
#   making sure that the outcomes across the set of sample datasets match expectations
# To the greatest extent possible,
#   generate the target outcomes blinded to the behaviour of the software
# TODO If a manually-specified graph is stored in the example dataset,
#   compare the generated graph against it
# TODO For example datasets where the behaviour with respect to
#   metadata file contents is important,
#   manually generate the expected associated metadata per data file,
#   and verify that against what is generated from the graph

TestOutcome = Enum("TestOutcome", "success warning violation failure")


@dataclass
class Test:
    dataset_name: str
    ruleset: str
    expectation: TestOutcome


TESTS = [
    # ip112e1bad
    Test("ip112e1bad", "1.1.x", TestOutcome.violation),
    Test("ip112e1bad", "1.7.x", TestOutcome.violation),
    Test("ip112e1bad", "PR1003", TestOutcome.success),
    Test("ip112e1bad", "I1195", TestOutcome.success),
    Test("ip112e1bad", "forbidden", TestOutcome.violation),
    # ip112e1good
    Test("ip112e1good", "1.1.x", TestOutcome.success),
    Test("ip112e1good", "1.7.x", TestOutcome.success),
    Test("ip112e1good", "PR1003", TestOutcome.success),
    Test("ip112e1good", "I1195", TestOutcome.success),
    Test("ip112e1good", "forbidden", TestOutcome.violation),
    # ip112e2v1
    Test("ip112e2v1", "1.1.x", TestOutcome.success),
    Test("ip112e2v1", "1.7.x", TestOutcome.success),
    Test("ip112e2v1", "PR1003", TestOutcome.success),
    Test("ip112e2v1", "I1195", TestOutcome.success),
    Test("ip112e2v1", "forbidden", TestOutcome.violation),
    # ip112e2v2
    Test("ip112e2v2", "1.1.x", TestOutcome.success),
    Test("ip112e2v2", "1.7.x", TestOutcome.success),
    Test("ip112e2v2", "PR1003", TestOutcome.success),
    Test("ip112e2v2", "I1195", TestOutcome.success),
    Test("ip112e2v2", "forbidden", TestOutcome.violation),
    # ip112e3v1
    Test("ip112e3v1", "1.1.x", TestOutcome.success),
    Test("ip112e3v1", "1.7.x", TestOutcome.success),
    Test("ip112e3v1", "PR1003", TestOutcome.success),
    Test("ip112e3v1", "I1195", TestOutcome.success),
    Test("ip112e3v1", "forbidden", TestOutcome.violation),
    # ip112e3v2
    Test("ip112e3v2", "1.1.x", TestOutcome.warning),
    Test("ip112e3v2", "1.7.x", TestOutcome.warning),
    Test("ip112e3v2", "PR1003", TestOutcome.warning),
    Test("ip112e3v2", "I1195", TestOutcome.warning),
    Test("ip112e3v2", "forbidden", TestOutcome.violation),
    # ip112badmetapathe1
    Test("ip112badmetapathe1", "1.1.x", TestOutcome.violation),
    Test("ip112badmetapathe1", "1.7.x", TestOutcome.success),
    Test("ip112badmetapathe1", "PR1003", TestOutcome.success),
    Test("ip112badmetapathe1", "I1195", TestOutcome.success),
    Test("ip112badmetapathe1", "forbidden", TestOutcome.violation),
    # ip112badmetapathe2v1
    Test("ip112badmetapathe2v1", "1.1.x", TestOutcome.violation),
    Test("ip112badmetapathe2v1", "1.7.x", TestOutcome.violation),
    Test("ip112badmetapathe2v1", "PR1003", TestOutcome.violation),
    Test("ip112badmetapathe2v1", "I1195", TestOutcome.violation),
    Test("ip112badmetapathe2v1", "forbidden", TestOutcome.violation),
    # ip112badmetapathe2v2
    Test("ip112badmetapathe2v2", "1.1.x", TestOutcome.violation),
    Test("ip112badmetapathe2v2", "1.7.x", TestOutcome.success),
    Test("ip112badmetapathe2v2", "PR1003", TestOutcome.success),
    Test("ip112badmetapathe2v2", "I1195", TestOutcome.success),
    Test("ip112badmetapathe2v2", "forbidden", TestOutcome.violation),
    # ip170e1
    Test("ip170e1", "1.1.x", TestOutcome.warning),
    Test("ip170e1", "1.7.x", TestOutcome.warning),
    Test("ip170e1", "PR1003", TestOutcome.warning),
    Test("ip170e1", "I1195", TestOutcome.warning),
    Test("ip170e1", "forbidden", TestOutcome.violation),
    # ip170e2
    Test("ip170e2", "1.1.x", TestOutcome.violation),
    Test("ip170e2", "1.7.x", TestOutcome.violation),
    Test("ip170e2", "PR1003", TestOutcome.success),
    Test("ip170e2", "I1195", TestOutcome.success),
    Test("ip170e2", "forbidden", TestOutcome.violation),
    # ip170e3
    Test("ip170e3", "1.1.x", TestOutcome.success),
    Test("ip170e3", "1.7.x", TestOutcome.success),
    Test("ip170e3", "PR1003", TestOutcome.success),
    Test("ip170e3", "I1195", TestOutcome.success),
    Test("ip170e3", "forbidden", TestOutcome.violation),
    # ip170e4
    Test("ip170e4", "1.1.x", TestOutcome.success),
    Test("ip170e4", "1.7.x", TestOutcome.success),
    Test("ip170e4", "PR1003", TestOutcome.success),
    Test("ip170e4", "I1195", TestOutcome.success),
    Test("ip170e4", "forbidden", TestOutcome.violation),
    # ipabsent
    Test("ipabsent", "1.1.x", TestOutcome.success),
    Test("ipabsent", "1.7.x", TestOutcome.success),
    Test("ipabsent", "PR1003", TestOutcome.success),
    Test("ipabsent", "I1195", TestOutcome.success),
    Test("ipabsent", "forbidden", TestOutcome.success),
    # ip170badrelpath
    Test("ip170badrelpath", "1.1.x", TestOutcome.success),
    Test("ip170badrelpath", "1.7.x", TestOutcome.violation),
    Test("ip170badrelpath", "PR1003", TestOutcome.violation),
    Test("ip170badrelpath", "I1195", TestOutcome.violation),
    Test("ip170badrelpath", "forbidden", TestOutcome.violation),
    # ipexclnonsc
    Test("ipexclnonsc", "1.1.x", TestOutcome.warning),
    Test("ipexclnonsc", "1.7.x", TestOutcome.warning),
    Test("ipexclnonsc", "PR1003", TestOutcome.warning),
    Test("ipexclnonsc", "I1195", TestOutcome.warning),
    Test("ipexclnonsc", "forbidden", TestOutcome.violation),
    # ipi1195e1
    Test("ipi1195e1", "1.1.x", TestOutcome.violation),
    Test("ipi1195e1", "1.7.x", TestOutcome.violation),
    Test("ipi1195e1", "PR1003", TestOutcome.violation),
    Test("ipi1195e1", "I1195", TestOutcome.success),
    Test("ipi1195e1", "forbidden", TestOutcome.violation),
    # iploosemeta
    Test("iploosemeta", "1.1.x", TestOutcome.warning),
    Test("iploosemeta", "1.7.x", TestOutcome.warning),
    Test("iploosemeta", "PR1003", TestOutcome.warning),
    Test("iploosemeta", "I1195", TestOutcome.warning),
    Test("iploosemeta", "forbidden", TestOutcome.violation),
    # ippr1003ae1
    Test("ippr1003ae1", "1.1.x", TestOutcome.violation),
    Test("ippr1003ae1", "1.7.x", TestOutcome.violation),
    Test("ippr1003ae1", "PR1003", TestOutcome.success),
    Test("ippr1003ae1", "I1195", TestOutcome.success),
    Test("ippr1003ae1", "forbidden", TestOutcome.violation),
    # ippr1003ae2
    Test("ippr1003ae2", "1.1.x", TestOutcome.violation),
    Test("ippr1003ae2", "1.7.x", TestOutcome.violation),
    Test("ippr1003ae2", "PR1003", TestOutcome.violation),
    Test("ippr1003ae2", "I1195", TestOutcome.success),
    Test("ippr1003ae2", "forbidden", TestOutcome.violation),
    # ippr1003e1v1
    Test("ippr1003e1v1", "1.1.x", TestOutcome.success),
    Test("ippr1003e1v1", "1.7.x", TestOutcome.success),
    Test("ippr1003e1v1", "PR1003", TestOutcome.success),
    Test("ippr1003e1v1", "I1195", TestOutcome.success),
    Test("ippr1003e1v1", "forbidden", TestOutcome.violation),
    # ippr1003e1v2
    Test("ippr1003e1v2", "1.1.x", TestOutcome.violation),
    Test("ippr1003e1v2", "1.7.x", TestOutcome.violation),
    Test("ippr1003e1v2", "PR1003", TestOutcome.success),
    Test("ippr1003e1v2", "I1195", TestOutcome.success),
    Test("ippr1003e1v2", "forbidden", TestOutcome.violation),
]


def run_test(bids_dir: pathlib.Path, ruleset: Ruleset) -> TestOutcome:
    try:
        graph = Graph(bids_dir, ruleset)
    except BIDSError:
        return TestOutcome.failure
    # TODO This code structure highlights that evaluate() should be responsible
    #   for determining whether the ruleset is violated,
    #   not the graph construction itself
    return_code = evaluate(bids_dir, ruleset, graph, warnings_as_errors=False)
    if return_code != ReturnCodes.SUCCESS:
        return TestOutcome.violation
    outcome = (
        TestOutcome.warning
        if evaluate(bids_dir, ruleset, graph, warnings_as_errors=True)
        == ReturnCodes.WARNINGS_AS_ERRORS
        else TestOutcome.success
    )
    # TODO For specifically testing,
    #   should ensure that operation of individual functions within utils module
    #   arrive at the same outcomes as does construction of the full graph
    graph_path = bids_dir / "sourcedata" / "ip_graph.json"
    if graph_path.is_file():
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                ref_graph = json.load(f)
        except json.JSONDecodeError:
            sys.stderr.write(f'Error reading reference graph JSON "{graph_path}"\n')
            raise
        if not graph.is_equal(ref_graph, ruleset):
            return TestOutcome.failure
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
        data = load_all(bids_dir, graph)
        if data != ref_metadata:
            return TestOutcome.failure
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
            return TestOutcome.failure
    return outcome


def run_tests(examples_dir: pathlib.Path) -> int:
    # For any test for which the outcome does not match expectation,
    #   store the test along with the actual outcome
    mismatches: list[tuple[Test, TestOutcome]] = []
    for test in TESTS:
        bids_dir = examples_dir / test.dataset_name
        if not bids_dir.is_dir():
            raise FileNotFoundError(
                f"Missing example BIDS dataset" f" {test.dataset_name}"
            )
        ruleset: Ruleset = RULESETS[test.ruleset]
        outcome = run_test(bids_dir, ruleset)
        if outcome != test.expectation:
            mismatches.append((test, outcome))
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
                f"    Dataset: {mismatch[0].dataset_name},"
                f" ruleset: {mismatch[0].ruleset},"
                f" expected {outcome2str(mismatch[0].expectation)};"
                f" actual outcome {outcome2str(mismatch[1])}\n"
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

    return run_tests(examples_dir)


if __name__ == "__main__":
    main()
