#!/usr/bin/env python3
"""Check object keys in JSON files are sorted alphabetically.

Run: python3 src/json_key_sort_checker.py config.json
     python3 src/json_key_sort_checker.py data/
     python3 src/json_key_sort_checker.py --stdin < config.json

Sorted keys give cleaner diffs and make a duplicate
or misplaced key obvious at a glance — and nobody
sorts a long config file by hand reliably. This tool
reads each JSON file, checks the keys of every
object — at every nesting level — are in
alphabetical order, case-insensitively, and reports
each key that is out of order, with the file and the
line number. It exits 1 when any key is out of
order, so it can fail a CI run. A file whose keys
are all sorted exits 0.

A file given directly on the command line is always
checked, whatever its name. A folder is walked for
files ending in .json only, recursively by default
(--no-recursive stops at the top level). .git
folders are never walked, and directory links are
never followed.

Two keys that differ only in case — "Name" and
"name" — count as equal, so either order passes.
A key is out of order when it sorts before the
largest key seen so far in the same object. A file
that is not valid JSON is reported, not passed:
sorting is meaningless when the file does not parse.

It never rewrites a file, never touches the network,
and reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"

JSON_SUFFIXES = (".json",)


class JsonObject(list):
    """A JSON object: a list of (key, value) pairs, in order.

    A plain list is a JSON array; this subclass marks a
    list that came from a JSON object, so the walker can
    tell the two apart.
    """


def _object_pairs(pairs):
    return JsonObject(pairs)


def scan_key_lines(text):
    """Find every object key and the line it sits on.

    In valid JSON a string followed by a colon is always
    an object key — a string value is followed by a
    comma, a closing bracket, or a closing brace, never
    a colon. So a small string-aware scan over the raw
    text gives the keys in document order, one per key,
    matching the order the parsed structure walks in.
    """
    keys = []
    line = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch == '"':
            start_line = line
            start = i
            i += 1
            while i < n:
                c = text[i]
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    break
                if c == "\n":
                    line += 1
                i += 1
            i += 1
            j = i
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] == ":":
                raw = text[start + 1:i - 1]
                try:
                    key = json.loads('"' + raw + '"')
                except ValueError:
                    key = raw
                keys.append((key, start_line))
        else:
            i += 1
    return keys


def check_text(text):
    """Check one document's text.

    Returns (findings, error): findings is a list of
    {"line": int, "reason": str} in document order, and
    error is None or a string saying why the file could
    not be checked at all.
    """
    try:
        parsed = json.loads(
            text, object_pairs_hook=_object_pairs)
    except ValueError as exc:
        return [], "not valid JSON: %s" % exc
    key_lines = scan_key_lines(text)
    findings = []
    index = [0]

    def walk(value):
        if isinstance(value, JsonObject):
            seen = None
            for key, item in value:
                if index[0] < len(key_lines):
                    _scanned, line = key_lines[index[0]]
                    index[0] += 1
                else:
                    line = 1
                lowered = key.lower()
                if seen is not None and lowered < seen:
                    findings.append({
                        "line": line,
                        "reason": (
                            'key "%s" is out of order '
                            '(keys sort alphabetically, '
                            'case-insensitively)' % key),
                    })
                if seen is None or lowered > seen:
                    seen = lowered
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(parsed)
    return findings, None


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    return check_text(text)


def _is_json_file(path):
    return Path(path).name.lower().endswith(JSON_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of JSON files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .json
    only. .git folders are never walked, and directory
    links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_json_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one key out of order."""
    return ("FAIL %s: key line %d %s"
            % (path, finding["line"], finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no JSON files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d key(s) out of order "
                  "in %d file(s)." % (len(files), findings,
                                      files_with_findings))
        else:
            print("OK — %d file(s) checked, every key is sorted."
                  % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one JSON document read from standard input."""
    text = sys.stdin.read()
    bad, error = check_text(text)
    findings = len(bad) + (1 if error else 0)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": error}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        if error:
            print("FAIL <stdin>: %s" % error)
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d key(s) out of order "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every key is sorted.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="json_key_sort_checker",
        description="Check object keys in JSON files are sorted "
                    "alphabetically, fail CI when one is not.")
    parser.add_argument("paths", nargs="*",
                        help="JSON files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one JSON document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one JSON file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
