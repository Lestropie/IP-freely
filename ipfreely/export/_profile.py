"""Optional cProfile instrumentation of the export pipeline.

Export is the only computationally expensive operation in the tool: the greedy
strategies solve a set-cover problem whose candidate space grows combinatorially
with entity count, so its cost is worth being able to attribute to individual
functions. Graph construction and evaluation are linear in dataset size and have
never warranted measurement.

Profiling is off unless `run.py --profile` is given, so that measured export
runtimes otherwise reflect real work rather than the interpreter's tracing
overhead (which inflates the greedy strategies several-fold).
"""

from contextlib import contextmanager
import pathlib
import sys
from typing import Optional


# Number of functions listed in the stderr summary. Long enough to reach past the
#   set-cover inner loop into the BIDSFilePath primitives it calls.
SUMMARY_ENTRIES = 25


@contextmanager
def profiled(destination: Optional[pathlib.Path]):
    # A no-op passthrough when `destination` is None, so that callers need no
    #   conditional of their own around the code being measured.
    if destination is None:
        yield
        return

    # Imported lazily: cProfile and pstats are absent from some minimal Python
    #   builds, and are of no interest to the overwhelmingly common unprofiled run.
    from cProfile import Profile  # pylint: disable=import-outside-toplevel
    from pstats import SortKey, Stats  # pylint: disable=import-outside-toplevel

    with Profile() as profile:
        yield

    stats = Stats(profile)
    stats.dump_stats(str(destination))
    sys.stderr.write(f"Profile written to {destination}\n")
    stats.strip_dirs().sort_stats(SortKey.CUMULATIVE).print_stats(SUMMARY_ENTRIES)
