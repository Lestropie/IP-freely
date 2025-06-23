import sys

# Codebase uses subscripted type hints
if sys.version_info < (3, 9):
    sys.stderr.write("Requies Python version 3.9 or later\n")
    sys.exit(1)

class BIDSError(Exception):
    pass


class InheritanceError(Exception):
    pass


EXCLUSIONS = (
    "dataset_description.json",
    "participants.json",
    "participants.tsv",
    "sourcedata",
    "README.md",
    "README.rst",
    "README.txt",
)
