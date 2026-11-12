#!/usr/bin/env python3
"""watchdo: a zero-dependency file watcher that reruns a command on changes."""
from __future__ import annotations
import argparse
import fnmatch
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.0.0"
DEFAULT_IGNORES = (".git/**", "__pycache__/**", ".venv/**", "venv/**", "*.pyc", ".mypy_cache/**", ".pytest_cache/**")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="watchdo", description="Re-run a command whenever watched files change.")
    parser.add_argument("-w", "--watch", action="append", default=[], metavar="PATH", help="file or directory to watch (repeatable; default: .)")
    parser.add_argument("-i", "--ignore", action="append", default=[], metavar="GLOB", help="relative path glob to ignore (repeatable)")
    parser.add_argument("-d", "--debounce", type=float, default=0.25, help="quiet time before rerunning, in seconds (default: 0.25)")
    parser.add_argument("-p", "--poll-interval", type=float, default=0.5, help="poll interval in seconds (default: 0.5)")
    parser.add_argument("--clear", action="store_true", help="clear the terminal before each run")
    parser.add_argument("--once", action="store_true", help="run the command once and exit")
    parser.add_argument("--version", action="version", version="watchdo " + __version__)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run; separate options with --")
    args = parser.parse_args(argv)
    if args.debounce < 0:
        parser.error("--debounce must be >= 0")
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be > 0")
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if len(command) == 1:
        command = shlex.split(command[0], posix=(os.name != "nt"))
    if not command:
        parser.error("a command is required (example: watchdo -- python app.py)")
    args.command = command
    args.watch = args.watch or ["."]
    args.ignore = list(DEFAULT_IGNORES) + args.ignore
    return args


def _ignored(relative, patterns):
    normalized = relative.replace(os.sep, "/")
    return any(fnmatch.fnmatchcase(normalized, pat) or fnmatch.fnmatchcase(Path(normalized).name, pat) for pat in patterns)


def snapshot(paths, ignore_patterns=DEFAULT_IGNORES):
    """Return a stable mapping of relative path to (size, mtime_ns)."""
    result = {}
    cwd = Path.cwd()
    for raw in paths:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            root = cwd / root
        try:
            if root.is_file() and not root.is_symlink():
                candidates = (root,)
            elif root.is_dir() and not root.is_symlink():
                candidates = (p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
            else:
                continue
            for path in candidates:
                try:
                    rel = path.relative_to(cwd).as_posix()
                except ValueError:
                    try:
                        rel = path.relative_to(root if root.is_dir() else root.parent).as_posix()
                    except ValueError:
                        rel = path.name
                if _ignored(rel, ignore_patterns):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                result[rel] = (stat.st_size, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
        except OSError:
            continue
    return result


def stop_process(process, grace=2.0):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass


def run(args):
    process = None
    try:
        current = snapshot(args.watch, args.ignore)
        print("watchdo: watching " + ", ".join(args.watch), flush=True)
        while True:
            if args.clear:
                print("\033[2J\033[H", end="", flush=True)
            print("\n[watchdo] $ " + subprocess.list2cmdline(args.command), flush=True)
            try:
                process = subprocess.Popen(args.command, start_new_session=(os.name != "nt"))
            except FileNotFoundError:
                print("watchdo: command not found: %s" % args.command[0], file=sys.stderr)
                return 127
            except OSError as exc:
                print("watchdo: could not start command: %s" % exc, file=sys.stderr)
                return 1
            if args.once:
                return process.wait()
            process.wait()
            process = None
            print("[watchdo] process exited; waiting for file changes...", flush=True)
            changed_at = None
            while True:
                time.sleep(args.poll_interval)
                updated = snapshot(args.watch, args.ignore)
                if updated != current:
                    current = updated
                    changed_at = time.monotonic()
                if changed_at is not None and time.monotonic() - changed_at >= args.debounce:
                    break
    except KeyboardInterrupt:
        print("\nwatchdo: stopped", flush=True)
        return 130
    finally:
        stop_process(process)


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
