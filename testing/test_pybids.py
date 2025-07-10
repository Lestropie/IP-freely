#!/usr/bin/env python3
import argparse
import bids
from dataclasses import dataclass
from enum import Enum
import json
import logging
import pathlib
import shutil
import sys
import numpy

logger = logging.getLogger(__name__)


TestOutcome = Enum("TestOutcome", "match warning violation mismatch")


@dataclass
class Test:
    bids_version: str
    expectation: TestOutcome


DATASETS = {
    "ip112e1bad": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ip112e1good": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip112e2v1": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip112e2v2": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip112e3v1": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip112e3v2": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.warning),
    ],
    "ip112badmetapathe1": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip112badmetapathe2v1": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ip112badmetapathe2v2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip170e1": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.warning),
    ],
    "ip170e2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ip170e3": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.warning),
    ],
    "ip170e4": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ipabsent": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ip170badrelpath": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ipexclnonsc": [
        Test("1.1.2", TestOutcome.warning),
        Test("1.7.0", TestOutcome.warning),
        # Test("1.11.0", TestOutcome.warning),
    ],
    "ipi1195v1": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ipi1195v2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ipdwi001": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ipdwi002": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ipdwi003": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "iploosemeta": [
        Test("1.1.2", TestOutcome.warning),
        Test("1.7.0", TestOutcome.warning),
        # Test("1.11.0", TestOutcome.warning),
    ],
    "ipmultielfce1v1": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ipmultielfce1v2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ippr1003ae1": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ippr1003ae2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
    "ippr1003e1v1": [
        Test("1.1.2", TestOutcome.match),
        Test("1.7.0", TestOutcome.match),
        # Test("1.11.0", TestOutcome.match),
    ],
    "ippr1003e1v2": [
        Test("1.1.2", TestOutcome.violation),
        Test("1.7.0", TestOutcome.violation),
        # Test("1.11.0", TestOutcome.violation),
    ],
}


# TODO Determine whether these exclusions of what's expected to be detected
#   apply to pybids just as it does to the ipfreely per-file functions
# DATASETS_SKIP_FN_TESTS = (
#    "ip170badrelpath",
#    "ip112badmetapathe2v1",
#    "ipexclnonsc",
# )


# For some datasets, a metadata graph may be intinsically ambiguous;
#   this will be flagged in the relevant reference metadata,
#   and the tests should correctly identify as such
# TODO Ideally pybids should *not* yield one of the two possibilities for these metadata
# DATASETS_AMBIGUOUS_METADATA = [
#    "ipi1195v2",
# ]


def check_versioned_dataset(
    bids_dir: pathlib.Path, ref_metadata: dict[str]
) -> TestOutcome:
    sys.stderr.write(f"Reference metadata: {ref_metadata}\n")
    try:
        layout = bids.BIDSLayout(bids_dir)
        metadata_read: set[str] = set()
        for filepath, content in layout.get_files().items():
            sys.stderr.write(f"Checking file {filepath} of type {type(content)}\n")
            if not isinstance(content, bids.layout.models.BIDSImageFile):
                continue
            relpath = pathlib.PurePath(filepath).relative_to(bids_dir)
            metadata_read.add(str(relpath))
            # JSON key-value metadata
            file_keyvalues = layout.get_metadata(filepath)
            sys.stderr.write(f"Metadata for file {relpath}: {file_keyvalues}\n")
            if not ref_metadata:
                sys.stderr.write(
                    "  Comparing valid metadata to empty reference metadata\n"
                )
                return TestOutcome.mismatch
            if str(relpath) not in ref_metadata:
                sys.stderr.write("  Data file absent from reference metadata\n")
                return TestOutcome.mismatch
            ref_file_metadata = ref_metadata[str(relpath)]
            if ".json" in ref_file_metadata:
                if file_keyvalues != ref_file_metadata[".json"]:
                    sys.stderr.write(
                        "  Mismatch of JSON key-values to reference metadata:"
                        f" {file_keyvalues} != {ref_file_metadata['.json']}\n"
                    )
                    return TestOutcome.mismatch
            elif file_keyvalues:
                sys.stderr.write("  No JSON key-values in reference metadata\n")
                return TestOutcome.mismatch
            if ".bvec" and ".bval" in ref_file_metadata:
                try:
                    file_bvecpath = layout.get_bvec(filepath)
                    file_bvalpath = layout.get_bval(filepath)
                except IndexError:
                    sys.stderr.write(
                        "  DWI gradient table in reference metadata absent from pybids\n"
                    )
                    return TestOutcome.mismatch
                file_bvec = numpy.loadtxt(file_bvecpath).tolist()
                file_bval = numpy.loadtxt(file_bvalpath).tolist()
                if (
                    file_bvec != ref_file_metadata[".bvec"]
                    or file_bval != ref_file_metadata[".bval"]
                ):
                    sys.stderr.write("  DWI gradient table does not match reference\n")
                    return TestOutcome.mismatch
            else:
                # If pybids reports bvec / bval absent from the reference metadata,
                #   treat that as a mismatch
                try:
                    file_bvecpath = layout.get_bvec(filepath)
                    sys.stderr.write("  DWI gradient table read not in reference\n")
                    return TestOutcome.mismatch
                except IndexError:
                    pass
                try:
                    file_bvalpath = layout.get_bval(filepath)
                    sys.stderr.write("  DWI gradient table read not in reference\n")
                    return TestOutcome.mismatch
                except IndexError:
                    pass

    except Exception:
        return TestOutcome.violation
    # Are there any data files in the reference metadata
    #   for which metadata has not been loaded by pybids?
    if ref_metadata:
        ref_unread = [key for key in ref_metadata if key not in metadata_read]
        if ref_unread:
            sys.stderr.write(
                f"  Data file in reference metadata not read: {ref_unread}\n"
            )
            return TestOutcome.mismatch
    return TestOutcome.match


def run_datasets(examples_dir: pathlib.Path, scratch_dir: pathlib.Path) -> int:
    # For any test for which the outcome does not match expectation,
    #   store the test along with the actual outcome
    mismatches: list[tuple[str, str, TestOutcome, TestOutcome]] = []
    for dataset, tests in DATASETS.items():
        bids_dir = examples_dir / dataset
        if not bids_dir.is_dir():
            raise FileNotFoundError(f"Missing example BIDS dataset" f" {dataset}")
        metadata_path = bids_dir / "sourcedata" / "ip_metadata.json"
        metadata = None
        if metadata_path.is_file():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            logging.debug(
                f"No precomputed metadata for dataset {dataset};"
                " expect violation under all BIDS versions"
            )
        logging.debug(f"Commencing tests of dataset {dataset}")
        for test in tests:
            bids_dir = scratch_dir / f"{dataset}_{test.bids_version}"
            shutil.copytree(examples_dir / dataset, bids_dir)
            dataset_description_path = bids_dir / "dataset_description.json"
            with open(dataset_description_path, "r", encoding="utf-8") as f:
                dataset_description_data = json.load(f)
            dataset_description_data["BIDSVersion"] = test.bids_version
            with open(dataset_description_path, "w", encoding="utf-8") as f:
                json.dump(dataset_description_data, f, indent=4)
            outcome = check_versioned_dataset(bids_dir, metadata)
            if outcome != test.expectation:
                mismatches.append(
                    (dataset, test.bids_version, test.expectation, outcome)
                )

    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stderr:
            handler.setLevel(logging.INFO)

    if mismatches:
        logger.info(f"{len(mismatches)} discrepancies in test outcomes")

        for mismatch in mismatches:
            logger.error(
                f"Dataset: {mismatch[0]},"
                f" BIDS version: {mismatch[1]},"
                f" expected {mismatch[2].name};"
                f" actual outcome {mismatch[3].name}"
            )
        return 1
    else:
        logger.info("All tests passed OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Test suite for IP-Freely")
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
        sys.stderr.write(f"Input BIDS examples directory {args.examples_dir} not found")
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

    return run_datasets(examples_dir, scratch_dir)


if __name__ == "__main__":
    main()
