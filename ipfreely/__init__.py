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
