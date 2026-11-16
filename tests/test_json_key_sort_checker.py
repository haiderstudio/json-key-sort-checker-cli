#!/usr/bin/env python3
"""Tests for json_key_sort_checker — stdlib unittest only.

Every JSON document in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json_key_sort_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/json_key_sort_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    findings, error = checker.check_text(text)
    assert error is None, error
    return findings


class TestKeyOrder(unittest.TestCase):
    def test_sorted_keys_pass(self):
        self.assertEqual(
            findings_of('{"apple": 1, "banana": 2, "cherry": 3}'), [])

    def test_unsorted_key_fails_with_line(self):
        bad = findings_of('{"banana": 1, "apple": 2}')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn('"apple"', bad[0]["reason"])

    def test_case_insensitive_order(self):
        self.assertEqual(
            findings_of('{"Apricot": 1, "banana": 2, "Cherry": 3}'), [])
        bad = findings_of('{"banana": 1, "Apple": 2}')
        self.assertEqual(len(bad), 1)

    def test_keys_differing_only_by_case_pass(self):
        self.assertEqual(
            findings_of('{"Name": "a", "name": "b"}'), [])

    def test_nested_objects_checked_per_level(self):
        text = ('{\n'
                '  "outer": {\n'
                '    "zebra": true,\n'
                '    "yak": false\n'
                '  }\n'
                '}\n')
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_each_level_sorted_independently(self):
        text = ('{\n'
                '  "b": {"d": 1, "e": 2},\n'
                '  "a": {"y": 1, "z": 2}\n'
                '}\n')
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [3])

    def test_objects_inside_arrays_checked(self):
        text = ('[\n'
                '  {"mango": 1, "lemon": 2}\n'
                ']\n')
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_multiple_out_of_order_keys_all_reported(self):
        text = ('{\n'
                '  "c": 1,\n'
                '  "b": 2,\n'
                '  "a": 3\n'
                '}\n')
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [3, 4])

    def test_key_after_a_larger_key_stays_flagged(self):
        # "apple" after "zebra" is out of order even though it
        # comes after another out-of-order key ("yak").
        text = ('{\n'
                '  "zebra": 1,\n'
                '  "yak": 2,\n'
                '  "apple": 3\n'
                '}\n')
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [3, 4])

    def test_empty_object_passes(self):
        self.assertEqual(findings_of("{}"), [])
        self.assertEqual(findings_of('{"a": {}}'), [])

    def test_single_key_passes(self):
        self.assertEqual(findings_of('{"only": 1}'), [])

    def test_top_level_array_passes(self):
        self.assertEqual(findings_of('[3, 1, 2]'), [])

    def test_top_level_scalar_passes(self):
        self.assertEqual(findings_of('"hello"'), [])
        self.assertEqual(findings_of("42"), [])

    def test_colon_inside_string_value_not_a_key(self):
        text = ('{\n'
                '  "a": "a string: with a colon",\n'
                '  "b": 1\n'
                '}\n')
        self.assertEqual(findings_of(text), [])

    def test_escaped_quote_in_key(self):
        text = '{"a\\"b": 1, "c": 2}'
        self.assertEqual(findings_of(text), [])
        bad = findings_of('{"c": 1, "a\\"b": 2}')
        self.assertEqual(len(bad), 1)

    def test_unicode_keys_sort_by_codepoint(self):
        # "zebra" sorts before "éclair" by codepoint, so this
        # order passes; reversed, the later key fails.
        self.assertEqual(
            findings_of('{"zebra": 1, "éclair": 2}'), [])
        bad = findings_of('{"éclair": 1, "zebra": 2}')
        self.assertEqual(len(bad), 1)

    def test_keys_with_spaces_and_digits(self):
        self.assertEqual(
            findings_of('{"a 1": 1, "a 2": 2, "b": 3}'), [])
        bad = findings_of('{"b": 1, "a 1": 2}')
        self.assertEqual(len(bad), 1)

    def test_duplicate_keys_do_not_hide_order(self):
        # Duplicates are repo #48's job, not this tool's — but
        # unsorted keys next to a duplicate are still found:
        # both "a" keys sort before the "b" that came first.
        bad = findings_of('{"b": 1, "a": 2, "a": 3}')
        self.assertEqual(len(bad), 2)

    def test_deeply_nested_objects(self):
        text = ('{"a": {"b": {"c": {"z": 1, "y": 2}}}}')
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)

    def test_multiline_key_reports_its_own_line(self):
        text = ('{\n'
                '  "banana": 1,\n'
                '  "apple": 2\n'
                '}\n')
        bad = findings_of(text)
        self.assertEqual(bad[0]["line"], 3)

    def test_invalid_json_is_an_error_not_a_pass(self):
        findings, error = checker.check_text('{"a": 1,')
        self.assertEqual(findings, [])
        self.assertIn("not valid JSON", error)

    def test_trailing_comma_is_an_error(self):
        findings, error = checker.check_text('{"a": 1,}')
        self.assertEqual(findings, [])
        self.assertIn("not valid JSON", error)


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"a": 1, "b": 2}\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("every key is sorted", out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 1", out)
            self.assertIn('"a"', out)
            self.assertIn(path, out)

    def test_folder_walk_finds_json_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"a": 1}\n')
            write(tmp, "b.json", '{"b": 1, "a": 2}\n')
            write(tmp, "notes.txt", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("b.json", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"a": 1}\n')
            write(tmp, "sub/b.json", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"a": 1}\n')
            write(tmp, "b.json", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([tmp, "--exclude", "b.json"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"a": 1}\n')
            write(tmp, ".git/b.json", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.txt", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("config.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"a": 1}\n')
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"b": 1, "a": 2}\n')
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 1)
            self.assertIn('"a"',
                          data["files"][0]["findings"][0]["reason"])
            self.assertIsNone(data["files"][0]["error"])

    def test_invalid_json_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"a": 1,\n')
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid JSON", out)

    def test_stdin_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input='{"a": 1, "b": 2}\n', cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every key is sorted", result.stdout)

    def test_stdin_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input='{"b": 1, "a": 2}\n', cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('FAIL <stdin>: key line 1 key "a"',
                          result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "a.json"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no JSON files found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("json_key_sort_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", b"\xff\xfe{}")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"b": 1, "a": 2}\n')
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.json", '{"a": 1}\n')
            result = subprocess.run(
                [sys.executable, str(SRC), "a.json"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every key is sorted", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.json", '{"a": 1}\n')
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/json_key_sort_checker.py",
             "examples/clean.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/json_key_sort_checker.py",
             "examples/flagged.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/json_key_sort_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 4 key(s) out of order "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 4 key(s) out of order "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/json_key_sort_checker.py",
             "examples/edge.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/json_key_sort_checker.py",
             "--json", "examples/flagged.json"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/json_key_sort_checker.py",
                       REPO / "tests/test_json_key_sort_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"json_key_sort_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/json_key_sort_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_json_key_sort_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("json-formatter-validator-cli", readme)
        self.assertIn("json-duplicate-key-checker-cli", readme)
        self.assertIn("yaml-key-sort-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
