import tempfile
import unittest
from pathlib import Path
from watchdo import parse_args, snapshot


class WatchdoTests(unittest.TestCase):
    def test_requires_command(self):
        with self.assertRaises(SystemExit):
            parse_args([])

    def test_parses_command_and_watch_paths(self):
        args = parse_args(["-w", "src", "--", "python", "app.py", "--debug"])
        self.assertEqual(args.watch, ["src"])
        self.assertEqual(args.command, ["python", "app.py", "--debug"])

    def test_rejects_invalid_timing(self):
        with self.assertRaises(SystemExit):
            parse_args(["--poll-interval", "0", "--", "echo", "ok"])

    def test_snapshot_detects_changes_and_ignores_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("one", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "app.pyc").write_bytes(b"cache")
            before = snapshot([str(root)])
            self.assertEqual(len(before), 1)
            (root / "app.py").write_text("two and longer", encoding="utf-8")
            after = snapshot([str(root)])
            self.assertNotEqual(before, after)

    def test_custom_ignore_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated.log").write_text("x", encoding="utf-8")
            self.assertEqual(snapshot([str(root)], ["*.log"]), {})


if __name__ == "__main__":
    unittest.main()
