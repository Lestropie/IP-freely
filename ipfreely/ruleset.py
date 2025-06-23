# This enum controls how multiple JSONs within a single filesystem level
#   are permitted to be associated with a single data file.
# - "Unique": No more than one metadata file may be applicable
#   at a single filesystem level.
# - "Ordered": There can be multiple metadata files applicable
#   at a single filesystem level, but *only* if they can be
#   unambiguously ordered based on the number of entities.
# - "Any": Any number of metadata files with any file names
#   can be applicable at a single filesystem level;
#   this rule would need to be accompanied with forbidding metadata overloading
#   in order for the ambiguity in metadata loading order to be obviated.
# INHERITANCE_PER_DIRECTORY = ('unique',
#                             'ordered',
#                             'any')
from dataclasses import dataclass
from enum import Enum

InheritanceWithinDir = Enum("InheritanceWithinDir", "unique ordered any")


@dataclass
class Ruleset:
    name: str
    compulsory_suffix: bool
    json_inheritance_within_dir: InheritanceWithinDir
    nonjson_inheritance_within_dir: InheritanceWithinDir
    permit_jsonfield_overwrite: bool
    permit_multiple_metadata_per_data: bool
    permit_multiple_data_per_metadata: bool
    permit_nonsidecar: bool


RULESETS = {
    # Current BIDS 1.x Inheritance Principle:
    "1.x": Ruleset(
        "1.x",
        # Suffix must be present in all files, including metadata files
        True,
        # Data file can't have more than one applicable JSON in a single directory
        InheritanceWithinDir.unique,
        # Data file can't have more than one of any other metadata file of any extension
        #   in a single directory
        InheritanceWithinDir.unique,
        # JSON metadata fields can be overloaded from distant
        # to nearest applicable JSON metadata files
        True,
        # No limit on one data file having more than one applicable metadata file
        True,
        # No limit on one metadata file being applicable to more than one data file
        True,
        # Metadata files don't strictly have to be sidecars
        True,
    ),
    # What was proposed in bids-standard PR #1003:
    "PR1003": Ruleset(
        "PR1003",
        # No change to compulsory suffixes
        True,
        # Permit multiple applicable JSON files at one filesystem level
        #   only if they can be unambiguously ordered
        InheritanceWithinDir.ordered,
        # Same for metadata files that aren't JSON;
        #   fine as long as one is unambiguously "nearest"
        InheritanceWithinDir.ordered,
        # No change to JSON field overloading
        True,
        # No change to multi-inheritance
        True,
        True,
        # Still possible for metadata files to not be sidecars
        True,
    ),
    # What was discussed in BIDS specification repository Issue #1195
    # What was implemented in Lestropie/bids-specification#5
    #   was actually that the overloading of metadata keys was only forbidden
    #   in the specific scenario where the key clash occurred between two source files
    #   that were equally proximal to the data file
    #   (same level of filesystem hierarchy, same number of entities)
    # I think that implementing support for this would be more trouble than it's worth;
    #   outright precluding overloading makes far more sense
    "I1195": Ruleset(
        "I1195",
        # No change to compulsory suffixes
        True,
        # Can be any number of applicable JSONs in one directory;
        #   don't have to deal with the order problem for precedence
        InheritanceWithinDir.any,
        # This however doesn't apply to metadata files other than JSON;
        #   there it's still necessary to be able to unambiguously choose
        #   just one such file based on filesystem path proximity
        InheritanceWithinDir.ordered,
        # Key distinction: No longer permit JSON field overloading
        False,
        # No change to multi-inheritance
        True,
        True,
        # Still possible for metadata files to not be sidecars
        True,
    ),
    # Precluding any and all use of Inheritance Principle, expressed as a ruleset
    # This permits use of the software tool to detect any presence of any aspect
    #   of the Inheritance Principle and report on that presence
    #   via the command return code
    "forbidden": Ruleset(
        "forbidden",
        # No change to compulsory suffixes
        True,
        # One data file can't have more than one applicable metadata file
        #   of any given file extension,
        #   regardless of position within filesystem
        InheritanceWithinDir.unique,
        InheritanceWithinDir.unique,
        # No JSON field overloading
        #   (not that it would matter: can't merge multiple JSON dicts anyway)
        False,
        # Prohibit any multi-inheritance
        False,
        False,
        # Force that all metadata files must be a sidecar to a data file
        # While technically it would be possible to satisfy no multi-inheritance
        #   and yet have non-sidecar metadata files,
        #   having one metadata file map to one data file
        #   yet not have equivalent entities
        #   would be problematic usage within such a ruleset,
        #   so more likely such a ruleset would explicitly require this
        False,
    ),
}
