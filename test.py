#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from enum import Enum
import json
import pathlib
import sys
from ipfreely import BIDSError
from ipfreely import InheritanceError
from ipfreely.evaluate import evaluate
from ipfreely.graph import Graph
from ipfreely.filepath import BIDSFilePath
from ipfreely.returncodes import ReturnCodes
from ipfreely.ruleset import Ruleset
from ipfreely.ruleset import RULESETS
from ipfreely.utils.get import datafiles_for_metafile
from ipfreely.utils.get import metafiles_for_datafile
from ipfreely.utils.keyvalues import find_overrides
from ipfreely.utils.keyvalues import has_override
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
    testname: str
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


# There are some potential IP issues for which it is not reasonable
#   for the functions that just query a single file in the dataset individually
#   to be able to detect;
# In those scenarios, skip just the testing of those functions
# Any additions to this list need to be accompanied by justification
DATASETS_SKIP_FN_TESTS = (
    # A metadata file that is applicable to a data file by name,
    #   but it is not within the parents of that data file
    # Detecting this would require scouring the entire dataset for such candidates
    #   for every individual file query
    "ip170badrelpath",
    "ip112badmetapathe2v1",
    # A data file and a metadata file are an exclusive pairing,
    #   ie. each is only associated to the other,
    #   yet they are not a sidecar pair.
    # Detecting this would mean running the query for the file matched.
    # This wouldn't be terribly expensive,
    #   but it would only be done for the purpose of this validation
    "ipexclnonsc",
)


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


def run_test_fromgraph(
    bids_dir: pathlib.Path, graph: Graph, ruleset: Ruleset
) -> TestOutcome:
    return_code = evaluate(bids_dir, ruleset, graph, warnings_as_errors=False)
    if return_code != ReturnCodes.SUCCESS:
        return TestOutcome.violation
    outcome = (
        TestOutcome.warning
        if evaluate(bids_dir, ruleset, graph, warnings_as_errors=True)
        == ReturnCodes.WARNINGS_AS_ERRORS
        else TestOutcome.success
    )
    return outcome


def run_test_fromfns(
    bids_dir: pathlib.Path, graph: Graph, ruleset: Ruleset
) -> TestOutcome:
    try:
        outcome = TestOutcome.success
        for datapath in graph.m4d:
            metafiles = metafiles_for_datafile(bids_dir, datapath, ruleset=ruleset.name)
            if ".json" in metafiles and has_override(bids_dir, metafiles[".json"]):
                outcome = TestOutcome.warning
        for metapath in graph.d4m:
            datapaths = datafiles_for_metafile(bids_dir, metapath, ruleset=ruleset.name)
            if not datapaths:
                if not ruleset.permit_nonsidecar:
                    return TestOutcome.violation
                outcome = TestOutcome.warning
        return outcome
    except InheritanceError:
        return TestOutcome.violation


def run_dataset_tests(
    bids_dir: pathlib.Path, graph: Graph, tests: list[Test]
) -> list[tuple[str, TestOutcome, TestOutcome]]:
    mismatches: list[tuple[str, TestOutcome, TestOutcome]] = []
    for test in tests:
        ruleset: Ruleset = RULESETS[test.testname]
        outcome_fromgraph = run_test_fromgraph(bids_dir, graph, ruleset)
        if outcome_fromgraph != test.expectation:
            mismatches.append(
                (f"{test.testname}_fromgraph", test.expectation, outcome_fromgraph)
            )
        if bids_dir.name in DATASETS_SKIP_FN_TESTS:
            continue
        outcome_fromfns = run_test_fromfns(bids_dir, graph, ruleset)
        if outcome_fromfns != test.expectation:
            mismatches.append(
                (f"{test.testname}_fromfns", test.expectation, outcome_fromfns)
            )
    return mismatches


def functions_match_graph(bids_dir: pathlib.Path, graph: Graph) -> bool:
    # Note that the graph has already been pruned
    f2graph: dict = {}
    for datapath in graph.m4d.keys():
        f2graph[str(datapath)] = {}
        from_fn = metafiles_for_datafile(bids_dir, datapath, prune=True, ruleset=None)
        for extension, metapaths in from_fn.items():
            f2graph[str(datapath)][extension] = (
                str(metapaths)
                if isinstance(metapaths, BIDSFilePath)
                else list(map(str, metapaths))
            )
    for metapath in graph.d4m.keys():
        from_fn = datafiles_for_metafile(bids_dir, metapath, prune=True, ruleset=None)
        f2graph[str(metapath)] = list(map(str, from_fn))
    return graph == f2graph


def run_datasets(examples_dir: pathlib.Path) -> int:
    # For any test for which the outcome does not match expectation,
    #   store the test along with the actual outcome
    mismatches: list[tuple[str, str, TestOutcome, TestOutcome]] = []
    for dataset, tests in DATASETS.items():
        bids_dir = examples_dir / dataset
        if not bids_dir.is_dir():
            raise FileNotFoundError(f"Missing example BIDS dataset" f" {dataset}")
        graph = Graph(bids_dir)
        dataset_mismatches = run_dataset_tests(bids_dir, graph, tests)
        for dataset_mismatch in dataset_mismatches:
            assert dataset_mismatch[1] != dataset_mismatch[2]
            mismatches.append(
                (dataset, dataset_mismatch[0], dataset_mismatch[1], dataset_mismatch[2])
            )
        graph.prune()
        if not check_dataset_graph(bids_dir, graph):
            mismatches.append(
                (
                    dataset,
                    "verify_graph",
                    TestOutcome.success,
                    TestOutcome.failure,
                )
            )
        if not functions_match_graph(bids_dir, graph):
            mismatches.append(
                (
                    dataset,
                    "get_functions",
                    TestOutcome.success,
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
                f" test: {mismatch[1]},"
                f" expected {outcome2str(mismatch[2])};"
                f" actual outcome {outcome2str(mismatch[3])}\n"
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
