"""Scaffolding shared by every dataset exporter.

All exporters realise the same four-phase pipeline:

1. copy every data file into the output directory (ExportContext.copy_datafiles);
2. build the indices that make applicability queries cheap (ExportContext.parent_sets,
   .json_by_datafile, .applicable_datafiles);
3. decide, per metadata field, which metadata file(s) should carry it — the *only*
   phase that differs between rulesets, implemented in `_sidecar` / `_tiered` /
   `_greedy`;
4. serialise the chosen metadata files (write_metafiles).

Phases 1, 2 and 4 live here so that each exporter module contains nothing but its own
placement strategy.
"""

from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from itertools import chain
from itertools import combinations
import json
import pathlib
import shutil

import numpy

from ..extensions import EXTENSIONS
from ..filepath import BIDSFilePath
from ..utils.applicability import is_applicable


@dataclass
class ExportContext:
    # The inputs common to every exporter, plus the derived indices they share.
    # Indices are computed lazily: the tiered exporters are the only consumers of
    #   json_by_datafile, and the sidecar exporter needs neither index.
    bids_dir: pathlib.Path
    metadata: dict[BIDSFilePath, dict[str]]
    out_dir: pathlib.Path
    _applicable_cache: dict[BIDSFilePath, "list[BIDSFilePath]"] = field(
        default_factory=dict, init=False, repr=False
    )

    @cached_property
    def parent_sets(self) -> dict[BIDSFilePath, "frozenset[str]"]:
        # Precompute, once per data file, the hashed set of its ancestor-directory
        #   strings. relpath.parents includes the immediate parent as parents[0],
        #   so this covers the same-directory case exactly. Threaded into
        #   is_applicable() to replace per-call pathlib.parents iteration.
        return {
            datapath: frozenset(map(str, datapath.relpath.parents))
            for datapath in self.metadata
        }

    @cached_property
    def json_by_datafile(self) -> dict[BIDSFilePath, dict]:
        # Each data file's resolved JSON key-values, for O(1) leak checks.
        return {
            datapath: by_extension.get(".json", {})
            for datapath, by_extension in self.metadata.items()
        }

    def copy_datafiles(self) -> None:
        for datapath in self.metadata:
            parent = self.out_dir / datapath.relpath.parent
            if not parent.exists():
                parent.mkdir(parents=True)
            shutil.copyfile(
                self.bids_dir / datapath.relpath, self.out_dir / datapath.relpath
            )

    def applicable_datafiles(self, metapath: BIDSFilePath) -> "list[BIDSFilePath]":
        # The data files a candidate metadata file is applicable to, by name AND
        #   filesystem location. The result depends only on the metapath, so it is
        #   shared across every field that probes the same candidate.
        cached = self._applicable_cache.get(metapath)
        if cached is not None:
            return cached
        metapath_parent_str = metapath.parentstr
        result = [
            datapath
            for datapath in self.metadata
            if is_applicable(
                datapath, metapath, self.parent_sets[datapath], metapath_parent_str
            )
        ]
        self._applicable_cache[metapath] = result
        return result


def write_metafile(fullpath: pathlib.Path, extension: str, content) -> None:
    # The sole metadata serialiser: every exporter's emit phase routes through here,
    #   so the on-disk representation of a given extension cannot drift between
    #   rulesets (it silently did, before this was factored out).
    with open(fullpath, "w", encoding="utf-8") as f:
        if EXTENSIONS[extension].is_numerical_matrix:
            numpy.savetxt(f, numpy.array(content))
        elif extension == ".json":
            json.dump(content, f, indent=4, sort_keys=True)
        elif extension == ".tsv":
            for row in content:
                f.write("\t".join(row) + "\n")
        else:
            assert False


def write_metafiles(
    out_dir: pathlib.Path, contents: dict[BIDSFilePath, object]
) -> None:
    for metapath, content in contents.items():
        write_metafile(out_dir / metapath.relpath, metapath.extension, content)


def powerset(items):
    # Every subset of `items`, shortest first, each yielded as a tuple.
    return chain.from_iterable(
        combinations(items, size) for size in range(len(items) + 1)
    )


def hashable(value):
    # Canonicalise a metadata value so that it can be used as a dictionary key:
    #   JSON arrays decode as lists, and lists of lists as nested lists, neither of
    #   which is hashable. Any other value is already hashable and passes through.
    if isinstance(value, list):
        if isinstance(value[0], list):
            return tuple(tuple(row) for row in value)
        return tuple(value)
    return value
