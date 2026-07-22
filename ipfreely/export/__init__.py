"""Conversion of a resolved BIDS dataset into a metadata layout valid under a ruleset.

Every exporter shares the same four-phase pipeline (see ``_common``); they differ only
in how they decide where each metadata field should live. Three placement strategies
cover all seven supported rulesets:

- ``_sidecar`` — no inheritance at all (`forbidden`).
- ``_tiered``  — per-field height-first hoisting (`1.1.x`, `1.7.x`, `1.11.x`, `PR1003`).
- ``_greedy``  — set cover over applicability sets (`I1195`, `BIDS2I75`).

`EXPORTERS` names the strategy and its behaviour modifiers for each ruleset.
`_profile` provides the opt-in cProfile instrumentation of the strategy call.
"""

from functools import partial
import json
import pathlib
import shutil
from typing import Optional

from .. import BIDSError
from ..filepath import BIDSFilePath
from ..ruleset import Ruleset
from ._common import ExportContext
from ._greedy import export_greedy
from ._profile import profiled
from ._sidecar import export_sidecar
from ._tiered import export_tiered


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


# Placement strategy, plus its behaviour modifiers, for each convertible ruleset.
# The modifiers correspond directly to Ruleset flags: `expand` to
#   json_inheritance_within_dir == InheritanceWithinDir.ordered, and `allow_suffixless`
#   to compulsory_suffix == False. They are stated explicitly here rather than derived,
#   so that adding a ruleset to RULESETS cannot silently acquire an exporter.
EXPORTERS = {
    "forbidden": export_sidecar,
    "I1195": partial(export_greedy, allow_suffixless=False),
    "PR1003": partial(export_tiered, expand=True),
    "1.1.x": export_tiered,
    "1.7.x": export_tiered,
    "1.11.x": export_tiered,
    "BIDS2I75": partial(export_greedy, allow_suffixless=True),
}


CONVERSION_RULESETS = list(EXPORTERS)


# BIDSVersion string to declare in the output dataset_description.json, for those
#   rulesets that are identified by a non-numeric BIDSVersion. Writing it means the
#   converted dataset auto-selects the same ruleset on re-evaluation (the inverse of
#   run.py's BIDSVersion -> ruleset mapping).
OUTPUT_BIDSVERSION = {
    "BIDS2I75": "BIDS 2.0 Issue 75",
}


def _append_or_create(mapping: dict, key: str, value) -> None:
    if key in mapping:
        mapping[key].append(value)
    else:
        mapping[key] = [value]


def export(
    bids_dir: pathlib.Path,
    metadata: dict[BIDSFilePath, dict[str]],
    ruleset: Ruleset,
    out_dir: pathlib.Path,
    profile: Optional[pathlib.Path] = None,
) -> None:

    if ruleset.name not in EXPORTERS:
        raise TypeError(
            "Only rulesets currently supported for conversion are: "
            + str(CONVERSION_RULESETS)
        )

    # Every output metadata file path is derived from a data file's suffix (its
    #   suffix must match that of the data file it describes), so a suffixless
    #   data file would yield a suffixless output metadata path. Output metadata
    #   files must always carry a suffix, and a data file lacking a datatype
    #   suffix is malformed regardless of ruleset, so refuse to proceed.
    suffixless_datafiles = [
        datapath for datapath in metadata if datapath.suffix is None
    ]
    if suffixless_datafiles:
        raise BIDSError(
            "Cannot determine suffixed output metadata file paths:"
            f" {len(suffixless_datafiles)} data"
            f" file{'s' if len(suffixless_datafiles) > 1 else ''}"
            " lacking a datatype suffix:"
            f" [{'; '.join(map(str, suffixless_datafiles))}]"
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
    _append_or_create(dataset_description_data, "GeneratedBy", "BIDS IP-Freely")
    _append_or_create(dataset_description_data, "SourceDatasets", str(bids_dir))
    if ruleset.name in OUTPUT_BIDSVERSION:
        dataset_description_data["BIDSVersion"] = OUTPUT_BIDSVERSION[ruleset.name]
    with open(out_dir / "dataset_description.json", "w", encoding="utf-8") as f:
        json.dump(dataset_description_data, f)

    # Only the exporter itself is profiled: the preamble above is a fixed handful of
    #   file copies, whereas the four-phase pipeline is where all scaling behaviour is.
    with profiled(profile):
        EXPORTERS[ruleset.name](ExportContext(bids_dir, metadata, out_dir))
