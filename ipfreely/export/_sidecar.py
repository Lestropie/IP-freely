"""Sidecar-only exporter: the `forbidden` ruleset.

`forbidden` permits no inheritance whatsoever, so there is no placement decision to
make: every data file's fully-resolved metadata is written to its own sidecar. This is
the de-inherited baseline against which the inheritance-exploiting exporters
(``_tiered``, ``_greedy``) are measured.
"""

from ._common import ExportContext
from ._common import write_metafile


def export_sidecar(context: ExportContext) -> None:
    context.copy_datafiles()
    for datapath, by_extension in context.metadata.items():
        for extension, content in by_extension.items():
            # The sidecar name is the data file's own parsed stem; deriving it from
            #   the entity list instead would risk drifting from the literal name.
            write_metafile(
                context.out_dir
                / datapath.relpath.parent
                / f"{datapath.stem}{extension}",
                extension,
                content,
            )
