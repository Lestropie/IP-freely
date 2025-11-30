# "IP-freely": Free manipulation of BIDS data according to the Inheritance Principle (IP)

The goal of this software project is to create a BIDS tool
that will automatically modify the storage of metadata
predicated on different versions of the Inheritance Principle.

The project has now undergone an initial round of development;
the outcomes of which are shown at https://github.com/Lestropie/IP-freely/pull/15.
To see the future vision of what this App will do,
please check the [Issue list](https://github.com/Lestropie/IP-freely/issues).

## Current capabilities

The tool is currently capable of doing the following:

-   Detect violations of the Inheritance Principle
    that may otherwise be missed by other checks.

-   Report on the prevalence and nature of the various manifestations
    of the Inheritance Principle,
    including overloading of key-value metadata.

-   Generate reporting on all associations between data files and metadata files.

-   Show the impact that different prospective "rule sets" have
    on whether different dataset arrangements / contents are permissible.

-   Provide functions for accessing metadata from within a BIDS dataset
    that is maximally conformant with the Inheritance Principle.

-   Convert an input BIDS dataset into an alternative dataset
    where there is no manifestation of the Inheritance Principle.

-   Report on conformity of both versions of the BIDS validator
    against expected outcomes for example BIDS datasets designed for that purpose.

## Usage

### API for BIDS parsing

The following are the most likely access points for programmers
looking to use this package for query metadata information in BIDS datasets
(note: function names may be subject to change):

-   Function `ipfreely.utils.metafiles_for_datafile()` yields the set of metadata files
    to be associated with a given data file.

-   Function `utils.keyvalues.load_keyvalues()` produces a metadata dictionary
    based on the set of JSONs associated with a given data file.

### Basic usage

The tool can be run natively as a standalone Python executable
(requires Python 3.9 or later):

```ShellSession
python3 run.py bids_dataset/
```
(replacing "`bids_dataset/`" with the path to a BIDS dataset of interest)

Alternatively it can be run using Docker:
```ShellSession
docker build . -t bids/ip-freely:latest
docker run -it --rm -v /path/to/bids_dataset:/bids bids/ip-freely:latest /bids
```

The command will by default yield a zero return code if the input dataset
satisfies all requirements of the Inheritance Principle.
For interpretation of non-zero return codes see file `ipfreely/returncodes.py`.
Note that some command-line options described below modulate this behaviour.

### Validator validation

To compare the outcomes of BIDS validators (both legacy and new schema-based implementations)
against *a priori* expected outcomes for exemplar datasets:
```ShellSession
cd testing/
docker build . -t ip-freely:testing
docker run -it --rm --entrypoint=/usr/bin/python3 bids/ip-freely:testing /test_validators.py /bids-examples
```

### `pybids` validation

To compare the outcomes of `pybids` against *a priori* expected outcomes for exemplar datasets:
```ShellSession
cd testing/
docker build . -t ip-freely:testing
docker run -it --rm --entrypoint=/usr/bin/python3 bids/ip-freely:testing /test_pybids.py /bids-examples
```

### Command-line options

#### Inputs

-   `-r` / `--ruleset`:

    This changes the set of criteria that are applied in determining
    whether or not the dataset is in violation of the Inheritance Principle.
    By default, the ruleset to be imposed is chosen
    based on the content of field "`BIDSVersion`" in file `dataset_description.json`
    (though at time of writing there has only been one such ruleset
    included in a tagged version of BIDS).
    One can optionally choose to override this
    and instead apply some other ruleset;
    these include speculative rulesets under consideration for BIDS 2.0.

-   `-w` / `--warnings-as-errors`:

    If there is some featore of the dataset
    that the tool considers to warrant a warning,
    the presence of this option will result in the command
    yielding a non-zero return code.

#### Outputs

-   `-g` / `--graph`:

    This option produces a JSON file encoding the full relational structure
    between datafiles and metadata files in the dataset:

    -   For each *data file*,
        the output of this option contains a *dictionary*
        where the keys are *metadata file extensions*.
        For each extension for which there is at least one metadata file
        associated with that data file,
        the contents in that dictionary is a list of filesystem paths.
        Most Inheritance Principle rulesets demand that the *order* of these associations
        must be obeyed:
        -   For `.json` files, the data should be loaded
            in the order in which they are presented in the list,
            so that in the case of some metadata key being present in multiple such files,
            it is the value associated with the *last* appearance of that key that takes precedence.
        -   For other metadata file extensions,
            it is *only* the *last* of these files
            that should be associated with that data file.

    -   For each *metadata file*,
        the output of this option is a *list of data files*
        to which that metadata file should be associated.
        The order of entries in these lists is not of consequence.

-   `-m` / `--metadata`:

    This option produces a JSON file encoding the comprehensive set of metadata
    to be associated with *every* data file in the input dataset,
    accounting for the prospect of complex inheritance.
    The values indexed by the data file paths are themselves dictionaries,
    indexed by metadata file extension.
    For each file extension for which there is at least one metadata file
    associated with that particular data file,
    the corresponding dictionary entry provides the corresponding metadata contents;
    in the case of key-value metadata encoded in JSON files,
    this is a key-value dictionary where key collisions between metadata files
    have had the appropriate precedence under the Inheritance Principle applied.

-   `-o` / `--overrides`:

    This option produces a JSON file encoding those key-value metadata entries for which,
    during construction of the metadata to be associated with some data file,
    the value stored in one file was overridden with that stored in another.
    This therefore highlights those circumstances
    where the presence of the Inheritance Principle in any given dataset
    arguably has the greatest prospect of leading to misinterpretation of data.

-   `-c` / `--convert`:

    This option produces a duplicate of the input BIDS dataset
    having been converted to conform to / exploit a specific Inheritance Principle ruleset.
    The first argument following this command-line option is the ruleset
    that the output converted dataset should conform to;
    currently the only permitted ruleset for this option is "forbidden",
    which will produce a dataset that contains no manifestations of the Inheritance Principle.
    The second argument following the command-line option is the output dataset path.

### Common non-default usages

-   To determine whether there is *any* manifestation of the Inheritance Principle
    within a dataset,
    run with `--ruleset forbidden`;
    the command will yield a non-zero return code
    if it detects any such manifestation,
    all of which are expressly forbidden by this ruleset.

-   To detect the presence of key-value metadata overriding in a dataset
    ---where the value associated with a key in one metadata file
    is replaced with a different value originating from another metadata file---
    run with `--warnings-as-errors`.
    Such overloading is always treated as a warning
    (even prior to the BIDS specification
    stating that such overloads are RECOMMENDED to avoid),
    and therefore escalating those warnings to errors allows for the presence of such
    to be detected based on the command return code.

### Testing

File `test.py` runs a large number of tests for verifying that the software
interpretation of the Inheritance Principle matches expectation.
These tests cover a broad range of test datasets
that exemplify various complex dataset configurations,
and additionally test multiple Inheritance Principle rulesets.
The input filesystem path to this command must, at time of writing,
be a specific branch on a specific fork of the `bids-specification/bids-examples` repository,
which can be found at:
https://github.com/Lestropie/bids-examples/pull/1.
The test command will produce a large amount of text at the terminal,
as each individual test currently simply writes all information to `stderr`,
regardless of whether it is just reporting information of potential interest
or error text (and indeed many tests involve ensuring that such errors are encountered).
What is important to note in its current implementation is that,
at the end of the terminal output,
the script does not report any discordances between the expected outcomes of validation tests
and the expectations that are manually pre-programmed.
Note that the test data and the tests on this repository
are not yet robustly version-matched.

## Acknowledgments

RS is supported by fellowship funding from the National Imaging Facility (NIF),
an Australian Government National Collaborative Research Infrastructure Strategy (NCRIS) capability.
The Florey Institute of Neuroscience and Mental Health
acknowledges the strong support from the Victorian Government and,
in particular,
the funding from the Operational Infrastructure Support Grant.
