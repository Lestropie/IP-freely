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

MetaPathCheck = Enum("MetaPathCheck", "ver112 ver170")

KeyvalueOverride = Enum("OverrideVerbosity", "permitted warning violation")


@dataclass
class Ruleset:
    name: str
    # Whether metadata files are required to possess a suffix.
    # Data files always require a datatype suffix, in every ruleset; this flag
    #   governs metadata files only. Set False by rulesets that permit a metadata
    #   file whose stem consists entirely of entities with no trailing suffix.
    compulsory_suffix: bool
    json_inheritance_within_dir: InheritanceWithinDir
    nonjson_inheritance_within_dir: InheritanceWithinDir
    keyvalue_override: KeyvalueOverride
    permit_multiple_metadata_per_data: bool
    permit_multiple_data_per_metadata: bool
    permit_nonsidecar: bool
    meta_path_check: MetaPathCheck


RULESETS = {
    # BIDS Inheritance Principle from 1.1.2 until 1.6.x:
    "1.1.x": Ruleset(
        "1.1.x",
        # Metadata files are required to possess a suffix
        #   (data files always require a datatype suffix, in every ruleset)
        True,
        # Data file can't have more than one applicable JSON in a single directory
        InheritanceWithinDir.unique,
        # Data file can't have more than one of any other metadata file of any extension
        #   in a single directory
        InheritanceWithinDir.unique,
        # JSON metadata fields can be overloaded from distant
        # to nearest applicable JSON metadata files
        KeyvalueOverride.permitted,
        # No limit on one data file having more than one applicable metadata file
        True,
        # No limit on one metadata file being applicable to more than one data file
        True,
        # Metadata files don't strictly have to be sidecars
        True,
        # Checking whether relative paths of metadata files are valid
        #   is based solely on:
        # - Is it *subject-speific*, ie. has "sub-",
        #   but is not in a subject-specific directory?
        # - Is it *not* subject-specific, ie. *doesn't* have "sub-",
        #   but is anywhere other than the root of the BIDS dataset?
        MetaPathCheck.ver112,
    ),
    # BIDS Inheritance Principle from 1.7.0 onwards:
    "1.7.x": Ruleset(
        "1.7.x",
        # All are identical to 1.1.x ...
        True,
        InheritanceWithinDir.unique,
        InheritanceWithinDir.unique,
        KeyvalueOverride.permitted,
        True,
        True,
        True,
        # ... except for the check on illegitimate metadata file
        #   location within the filesystem hierarchy
        MetaPathCheck.ver170,
    ),
    # BIDS Inheritance Principle coming in 1.11.x:
    "1.11.x": Ruleset(
        "1.11.x",
        # All are identical to 1.7.x ...
        True,
        InheritanceWithinDir.unique,
        InheritanceWithinDir.unique,
        # ... except that keyvalue overrides are now RECOMMENDED to avoid,
        #   and should therefore result in a warning
        KeyvalueOverride.warning,
        True,
        True,
        True,
        MetaPathCheck.ver170,
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
        KeyvalueOverride.permitted,
        # No change to multi-inheritance
        True,
        True,
        # Still possible for metadata files to not be sidecars
        True,
        # No proposed change to metadata file path location check
        MetaPathCheck.ver170,
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
        KeyvalueOverride.violation,
        # No change to multi-inheritance
        True,
        True,
        # Still possible for metadata files to not be sidecars
        True,
        # No proposed change to metadata file path location check
        MetaPathCheck.ver170,
    ),
    # Prospective future ruleset under discussion in the BIDS 2.0 development
    #   repository, Issue #75.
    # Identical to I1195 in every inheritance rule, with a single key distinction:
    #   metadata files are NO LONGER required to possess a trailing suffix. A
    #   metadata file's stem may consist entirely of entities (e.g.
    #   "sub-01_ses-1.json"), in which case it is applicable to any data file
    #   whose entities are a superset, irrespective of the data file's suffix.
    #   Data files still require a datatype suffix (enforced in every ruleset).
    "BIDS2I75": Ruleset(
        "BIDS2I75",
        # Key distinction from I1195: metadata files need NOT carry a suffix
        False,
        # All remaining rules are identical to I1195 ...
        # Any number of applicable JSONs in one directory
        InheritanceWithinDir.any,
        # Non-JSON metadata files must still be unambiguously orderable
        InheritanceWithinDir.ordered,
        # No JSON field overloading
        KeyvalueOverride.violation,
        # No change to multi-inheritance
        True,
        True,
        # Still possible for metadata files to not be sidecars
        True,
        # No change to metadata file path location check
        MetaPathCheck.ver170,
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
        KeyvalueOverride.violation,
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
        # Choice here should be irrelevant
        #   (not possible for a dataset to violate just this criterion exclusively
        #   given the other restrictions in the ruleset);
        #   1.1.2 rule is chosen just because it is computationally cheaper
        MetaPathCheck.ver112,
    ),
}
