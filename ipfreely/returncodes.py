from enum import IntEnum


class ReturnCodes(IntEnum):
    SUCCESS = 0
    # 1 = Catchall for general errors
    # 2 = Misuse of shell builtins
    USAGE = 3
    NO_DATASET = 4
    NO_RULESET = 5
    MALFORMED_DATASET = 6
    IP_VIOLATION = 7
    # Putting this last given it is inherently non-specific
    WARNINGS_AS_ERRORS = 125
