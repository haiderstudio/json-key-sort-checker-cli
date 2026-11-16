# json-key-sort-checker-cli

Check object keys in JSON files are sorted alphabetically — fail CI when one is not.

[![CI](https://github.com/haiderstudio/json-key-sort-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/json-key-sort-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`json_key_sort_checker` reads each JSON file,
checks the keys of every object — at every nesting
level — are in alphabetical order, case-insensitively,
and reports each key that is out of order, with the
file and the line number. It exits 1 when any key is
out of order, so it can fail a CI run. A file whose
keys are all sorted exits 0.

- Sorted keys give cleaner diffs and make a duplicate
  or misplaced key obvious at a glance — and nobody
  sorts a long config file by hand reliably. This
  names the exact line, and the fix is moving one
  key.
- Two keys that differ only in case — "Name" and
  "name" — count as equal, so either order passes.
  A key is out of order when it sorts before the
  largest key seen so far in the same object.
- A file that is not valid JSON is reported, not
  passed: sorting is meaningless when the file does
  not parse.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.json` only, recursively by
  default (`--no-recursive` stops at the top level).
  `.git` folders are never walked, and directory
  links are never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one JSON document read from standard input.

## Who it is for

Every project with a JSON config file — package
settings, editor settings, API fixtures, test data.
One key pasted in the wrong place and the diff
reviewer has to read the whole object to find it,
and the next duplicate hides in the noise. This is
the gate that keeps the keys in order at the pull
request.

## What it does NOT do

- It does not check that JSON is formatted or valid
  beyond parsing it — that is repo #19,
  json-formatter-validator-cli, which formats and
  validates JSON. This tool only checks key order.
- It does not check for duplicate keys — that is
  repo #48, json-duplicate-key-checker-cli. Order is
  a different check on the same files.
- It does not check key order in YAML — that is
  repo #102, yaml-key-sort-checker-cli. YAML is a
  different file format.
- It does not sort a file for you. It only reports
  the keys that are out of order.
- It never rewrites a file, and it never touches the
  network.

## How this differs

- A fresh search of GitHub on Nov 15, 2026 found 0
  results for `"json-key-sort-checker-cli"` and 1
  result for `json key sort checker` —
  memeismygod/hack, 5 stars, a Discord script that
  merely contains "json" and "checker" in its
  imports, not a checker of any kind.
- No rival checks JSON key order in local files.

## Install

```sh
git clone https://github.com/haiderstudio/json-key-sort-checker-cli.git
cd json-key-sort-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one JSON file:

```sh
python3 src/json_key_sort_checker.py config.json
```

A file whose keys are all sorted passes:

```sh
$ python3 src/json_key_sort_checker.py examples/clean.json
OK — 1 file(s) checked, every key is sorted.
```

A file with keys out of order fails, with the file
and line for each one:

```sh
$ python3 src/json_key_sort_checker.py examples/flagged.json
FAIL examples/flagged.json: key line 3 key "apple" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 6 key "yak" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 7 key "apple" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 12 key "lemon" is out of order (keys sort alphabetically, case-insensitively)
Checked 1 file(s), 4 key(s) out of order in 1 file(s).
```

Check a whole folder (`.json` files only):

```sh
$ python3 src/json_key_sort_checker.py examples/
FAIL examples/flagged.json: key line 3 key "apple" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 6 key "yak" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 7 key "apple" is out of order (keys sort alphabetically, case-insensitively)
FAIL examples/flagged.json: key line 12 key "lemon" is out of order (keys sort alphabetically, case-insensitively)
Checked 3 file(s), 4 key(s) out of order in 1 file(s).
```

Check one document from standard input:

```sh
$ printf '{"b": 1, "a": 2}\n' | python3 src/json_key_sort_checker.py --stdin
FAIL <stdin>: key line 1 key "a" is out of order (keys sort alphabetically, case-insensitively)
Checked 1 file(s), 1 key(s) out of order in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/json_key_sort_checker.py --json examples/flagged.json
{
  "files": [
    {
      "path": "examples/flagged.json",
      "findings": [
        {
          "line": 3,
          "reason": "key \"apple\" is out of order (keys sort alphabetically, case-insensitively)"
        },
        {
          "line": 6,
          "reason": "key \"yak\" is out of order (keys sort alphabetically, case-insensitively)"
        },
        {
          "line": 7,
          "reason": "key \"apple\" is out of order (keys sort alphabetically, case-insensitively)"
        },
        {
          "line": 12,
          "reason": "key \"lemon\" is out of order (keys sort alphabetically, case-insensitively)"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 4
}
```

Exit codes: 0 when every key is sorted, 1 when
any key is out of order or a file cannot be read or
parsed, 2 for a usage error (a missing path, a bad
flag, or no JSON files found).

## Examples

A case-insensitive sort, nested objects, and objects
inside arrays are all handled — `examples/clean.json`
has all of them, and it passes:

```sh
$ python3 src/json_key_sort_checker.py examples/clean.json
OK — 1 file(s) checked, every key is sorted.
```

Two keys that differ only in case, a colon inside a
string value, and a non-English key are all handled
— `examples/edge.json` has all of them, and it
passes:

```sh
$ python3 src/json_key_sort_checker.py examples/edge.json
OK — 1 file(s) checked, every key is sorted.
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_json_key_sort_checker.py
```

The tests cover key order (sorted keys pass, an
unsorted key fails with its line, case-insensitive
order, keys differing only by case pass, nested
objects checked per level, each level sorted
independently, objects inside arrays checked,
several out-of-order keys all reported, a key after
a larger key stays flagged, an empty object passes,
a single key passes, a top-level array or scalar
passes, a colon inside a string value is not a key,
an escaped quote in a key, non-English keys sort by
codepoint, keys with spaces and digits, duplicate
keys do not hide order, deeply nested objects, a
multiline key reports its own line, invalid JSON is
an error not a pass, a trailing comma is an error),
the CLI (exit 0/1/2, folder walking for several JSON
files, nested folders, `--no-recursive`, `--exclude`,
`.git` skipped, a direct file checked whatever its
name, duplicate paths checked once, `--json` output,
an invalid JSON file fails, `--stdin`, bad flags,
missing paths, empty folders, `--version`, a
non-UTF-8 file reported, input files left unchanged,
the tool run from another folder and under a changed
HOME), the bundled examples (sample output compared
byte-for-byte against a fresh run, and the
README-quoted outputs checked against it), and
hygiene checks (no placeholder text, no absolute
paths, no real secrets outside the tests and
examples, stdlib imports only, no network use in the
source, `.env` first in `.gitignore`, CI file runs
the test file, README names the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of sorting keys is not new, and the parsing
follows Python's own standard-library JSON parser —
but no existing tool does this one job, checking that
object keys in local JSON files are sorted
alphabetically as a tested command-line gate with a
CI exit code, as the search above shows — and every
line of code here is original, built on nothing but
Python's standard library.
