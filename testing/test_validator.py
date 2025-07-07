#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from enum import Enum
import json
import logging
import pathlib
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

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
    dataset: str
    bids_version: str
    expectation: TestOutcome


@dataclass
class OutcomeMismatch:
    dataset: str
    bids_version: str
    expectation: TestOutcome
    outcome: TestOutcome


# Description of mismatches between expectation and BIDS validator 1.15.0 outcomes:
# - ip112badmetapath* under 1.7.x: The stipulation that only subject-agnostic files be at root
#   and only subject-specific files be not at root may technically be no longer present.
# - ip112e1bad, ip170e2, ipdwi003, ipmulticfe1v2, ippr1003e1v2:
#   Fails to identify that there are data files for which there are multiple
#   applicable metadata files within a single filesystem hierarchy level.
# - ip170badrelpath: TODO Check whether there are features of the specification
#   outside of the Inheritance Principle that make this structure invalid
# - ippr1003ae2, others: Is it really necessary that *any* file with "bold" suffix have the "_task-" entity?
#   This might make sense for data files but seems to preclude some types of inheritance

TESTS = [
    Test("ip112e1bad", "1.1.2", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ip112e1bad", "1.7.0", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ip112e1good", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip112e1good", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip112e2v1", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip112e2v1", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip112e2v2", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip112e2v2", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip112e3v1", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip112e3v1", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip112e3v2", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip112e3v2", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip112badmetapathe1", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test(
        "ip112badmetapathe1", "1.7.0", TestOutcome.success
    ),  # Result: Violation MISMATCH
    Test("ip112badmetapathe2v1", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test("ip112badmetapathe2v1", "1.7.0", TestOutcome.violation),  # Result: Violation
    Test("ip112badmetapathe2v2", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test(
        "ip112badmetapathe2v2", "1.7.0", TestOutcome.success
    ),  # Result: Violation MISMATCH
    Test("ip170e1", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip170e1", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip170e2", "1.1.2", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ip170e2", "1.7.0", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ip170e3", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip170e3", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ip170e4", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ip170e4", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ipabsent", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ipabsent", "1.7.0", TestOutcome.success),  # Result: Success MISMATCH
    Test(
        "ip170badrelpath", "1.1.2", TestOutcome.success
    ),  # Result: Violation TODO Check
    Test(
        "ip170badrelpath", "1.7.0", TestOutcome.violation
    ),  # Result: Violation TODO Check
    Test("ipexclnonsc", "1.1.2", TestOutcome.warning),  # TODO Check with updated data
    Test("ipexclnonsc", "1.7.0", TestOutcome.warning),  # TODO Check with updated data
    Test("ipi1195v1", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test("ipi1195v1", "1.7.0", TestOutcome.violation),  # Result: Violation
    Test("ipi1195v2", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test("ipi1195v2", "1.7.0", TestOutcome.violation),  # Result: Violation
    Test("ipdwi001", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ipdwi001", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ipdwi002", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ipdwi002", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ipdwi003", "1.1.2", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ipdwi003", "1.7.0", TestOutcome.violation),  # Result: Success MISMATCH
    Test(
        "iploosemeta", "1.1.2", TestOutcome.warning
    ),  # Result: Violation TODO Check specification
    Test(
        "iploosemeta", "1.7.0", TestOutcome.warning
    ),  # Result: Violation TODO Check specification
    Test("ipmultielfce1v1", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ipmultielfce1v1", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ipmultielfce1v2", "1.1.2", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ipmultielfce1v2", "1.7.0", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ippr1003ae1", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test("ippr1003ae1", "1.7.0", TestOutcome.violation),  # Result: Violation
    Test("ippr1003ae2", "1.1.2", TestOutcome.violation),  # Result: Violation
    Test("ippr1003ae2", "1.7.0", TestOutcome.violation),  # Result: Violation
    Test("ippr1003e1v1", "1.1.2", TestOutcome.success),  # Result: Success
    Test("ippr1003e1v1", "1.7.0", TestOutcome.success),  # Result: Success
    Test("ippr1003e1v2", "1.1.2", TestOutcome.violation),  # Result: Success MISMATCH
    Test("ippr1003e1v2", "1.7.0", TestOutcome.violation),  # Result: Success MISMATCH
]


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


def run_tests(examples_dir: pathlib.Path, scratch_dir: pathlib.Path) -> int:
    # For any test for which the outcome does not match expectation,
    #   store the test along with the actual outcome
    mismatches: list[OutcomeMismatch] = []
    for test in TESTS:
        bids_dir = examples_dir / test.dataset
        if not (examples_dir / test.dataset).is_dir():
            raise FileNotFoundError(f"Missing example BIDS dataset" f" {test.dataset}")
        bids_dir = scratch_dir / f"{test.dataset}_{test.bids_version}"
        shutil.copytree(examples_dir / test.dataset, bids_dir)
        dataset_description_path = bids_dir / "dataset_description.json"
        with open(dataset_description_path, "r", encoding="utf-8") as f:
            dataset_description_data = json.load(f)
        dataset_description_data["BIDSVersion"] = test.bids_version
        with open(dataset_description_path, "w", encoding="utf-8") as f:
            json.dump(dataset_description_data, f)
        logging.debug(
            f"Running dataset {test.dataset} under BIDS version {test.bids_version}, expecting {test.expectation}"
        )
        validator_result = subprocess.run(
            ["bids-validator", bids_dir, "--config", "legacy_config.json"],
            capture_output=True,
        )
        # TODO Eventually will need to parse output to determine whether a warning was issued;
        #   for currently tagged BIDS versions there are no warning cases,
        #   but there will be for 1.11.x
        outcome: TestOutcome = (
            TestOutcome.violation
            if validator_result.returncode
            else TestOutcome.success
        )
        if outcome != test.expectation:
            mismatches.append(
                OutcomeMismatch(
                    test.dataset, test.bids_version, test.expectation, outcome
                )
            )

    if mismatches:
        logger.info(f"{len(mismatches)} discrepancies in test outcomes")

        for mismatch in mismatches:
            logger.error(
                f"Dataset: {mismatch.dataset},"
                f" BIDS version: {mismatch.bids_version},"
                f" expected {outcome2str(mismatch.expectation)};"
                f" actual outcome {outcome2str(mismatch.outcome)}"
            )
        return 1
    else:
        logger.info("All tests passed OK")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Test BIDS Validator against Inheritance Principle exemplar datasets"
    )
    parser.add_argument(
        "examples_dir",
        help="A directory containing the BIDS example datasets",
    )
    parser.add_argument(
        "-s",
        "--scratch",
        help="Specify a scratch directory where temporarily modified datasets can be written",
    )
    parser.add_argument("-l", "--log", help="Write a full log to file")

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        sys.stderr.write(f"Error parsing command-line: {e}\n")
        sys.exit()

    examples_dir = pathlib.Path(args.examples_dir)
    if not examples_dir.is_dir():
        sys.stderr.write(
            f"Input BIDS examples directory {args.examples_dir} not found\n"
        )
        sys.exit(1)
    scratch_dir = pathlib.Path.cwd()
    if args.scratch is not None:
        scratch_dir = pathlib.Path(args.scratch)
        if not scratch_dir.is_dir():
            scratch_dir.mkdir(parents=True)

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    if args.log:
        file_handler = logging.FileHandler(args.log)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(name)s |  %(levelname)s: %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    return run_tests(examples_dir, scratch_dir)


if __name__ == "__main__":
    main()
