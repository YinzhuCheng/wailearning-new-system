from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
STATE_DIR = REPO_ROOT / ".agent-run" / "validation-daemon"
LAUNCH_LOG = STATE_DIR / "WAI-VALID-launcher.log"
MONITOR_LAUNCHER_CMD = STATE_DIR / "WAI-VALID-launch-monitor.cmd"
SUPERVISOR_SCRIPT = REPO_ROOT / "ops" / "scripts" / "dev" / "wai_valid_supervisor.py"
SUPERVISOR_LAUNCH_LOG = STATE_DIR / "WAI-VALID-supervisor-launch.log"
SUPERVISOR_PID_PATH = STATE_DIR / "WAI-VALID-supervisor-detached.pid"
SUPERVISOR_STDOUT_LOG = STATE_DIR / "WAI-VALID-supervisor-stdout.log"
SUPERVISOR_STDERR_LOG = STATE_DIR / "WAI-VALID-supervisor-stderr.log"


def _windows_creation_flags(*flags: int) -> int:
    value = 0
    for flag in flags:
        value |= flag
    return value


DETACHED_FLAGS = _windows_creation_flags(
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008),
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200),
)
BACKGROUND_FLAGS = DETACHED_FLAGS | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
VISIBLE_FLAGS = DETACHED_FLAGS | getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)


def write_launch_log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LAUNCH_LOG.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    supervisor = subparsers.add_parser("supervisor", help="Start the validation supervisor detached.")
    supervisor.add_argument(
        "--args-file",
        help="Optional JSON file containing the full wai_valid_supervisor.py argument array.",
    )
    supervisor.add_argument("supervisor_args", nargs=argparse.REMAINDER, help="Arguments for wai_valid_supervisor.py.")

    background = subparsers.add_parser("background", help="Start a detached background process.")
    background.add_argument("script_path", help="Absolute or repository-relative script path to launch.")
    background.add_argument("script_args", nargs=argparse.REMAINDER, help="Optional script arguments.")

    return parser.parse_args()


def _normalize_script_path(path_text: str) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_background_wrapper(script: Path, script_args: list[str]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = STATE_DIR / f"WAI-VALID-background-launch-{int(time.time() * 1000)}.ps1"
    wrapper_lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$scriptPath = {_ps_single_quote(str(script))}",
        "$scriptArgs = @(",
    ]
    wrapper_lines.extend(f"    {_ps_single_quote(arg)}" for arg in script_args)
    wrapper_lines.extend(
        [
            ")",
            "& $scriptPath @scriptArgs",
            "",
        ]
    )
    wrapper_path.write_text("\n".join(wrapper_lines), encoding="utf-8")
    return wrapper_path


def _resolve_supervisor_args(raw_args: list[str]) -> list[str]:
    resolved = list(raw_args)
    while len(resolved) >= 2 and resolved[0] == "--args-file":
        args_path = Path(resolved[1])
        if not args_path.is_absolute():
            args_path = REPO_ROOT / args_path
        payload = args_path.read_text(encoding="utf-8")
        import json  # noqa: WPS433

        parsed = json.loads(payload)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise SystemExit(f"Invalid supervisor args file: {args_path}")
        resolved = [*parsed, *resolved[2:]]
    return resolved


def launch_supervisor(supervisor_args: list[str], args_file: str | None = None) -> int:
    if not PYTHON_EXE.exists():
        raise SystemExit(f"Missing repository venv interpreter: {PYTHON_EXE}")
    if not SUPERVISOR_SCRIPT.exists():
        raise SystemExit(f"Missing supervisor script: {SUPERVISOR_SCRIPT}")
    raw_args = list(supervisor_args)
    if args_file:
        raw_args = ["--args-file", args_file, *raw_args]
    resolved_args = _resolve_supervisor_args(raw_args)
    proc_args = [str(PYTHON_EXE), "-u", str(SUPERVISOR_SCRIPT), *resolved_args]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    write_launch_log(f"supervisor args={proc_args!r}")
    with SUPERVISOR_LAUNCH_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"START {time.strftime('%Y-%m-%dT%H:%M:%S%z')} python={PYTHON_EXE}\n")
        handle.write(f"ARGS  {' '.join(proc_args[1:])}\n")
    stdout_handle = SUPERVISOR_STDOUT_LOG.open("ab")
    stderr_handle = SUPERVISOR_STDERR_LOG.open("ab")
    proc = subprocess.Popen(
        proc_args,
        cwd=str(REPO_ROOT),
        creationflags=BACKGROUND_FLAGS,
        close_fds=True,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
    )
    SUPERVISOR_PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    with SUPERVISOR_LAUNCH_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"PID   {proc.pid}\n")
    return 0


def launch_background(script_path: str, script_args: list[str]) -> int:
    script = _normalize_script_path(script_path)
    if not script.exists():
        raise SystemExit(f"Script not found: {script}")
    wrapper = _build_background_wrapper(script, script_args)
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(wrapper),
    ]
    write_launch_log(f"background script={script}")
    write_launch_log(f"background wrapper={wrapper}")
    write_launch_log(f"background script_args={script_args!r}")
    write_launch_log(f"background args={args!r}")
    subprocess.Popen(
        args,
        cwd=str(REPO_ROOT),
        creationflags=BACKGROUND_FLAGS,
        close_fds=True,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "supervisor":
        return launch_supervisor(args.supervisor_args, args.args_file)
    if args.command == "background":
        return launch_background(args.script_path, args.script_args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
