"""
Master entry point for the PsychTest Suite (BART, PVT, Trail Making Test).

Usage:
  python master.py

Or from PsychSuite:
  python launcher.py
"""
import os
import sys
import platform
import shutil
import subprocess
import re

_SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PsychSuite')
os.chdir(_SUITE)
sys.path.insert(0, _SUITE)

from launcher import PsychLauncher  # noqa: E402

def _set_macos_resolution_4k():
    """Best-effort: set primary macOS display to 3840x2160 before launch."""
    if platform.system() != 'Darwin':
        return
    if shutil.which('displayplacer') is None:
        print("[master] macOS 4K mode skipped: install 'displayplacer' via Homebrew.")
        return
    try:
        listed = subprocess.run(
            ['displayplacer', 'list'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if listed.returncode != 0:
            detail = listed.stderr.strip() or listed.stdout.strip() or "unknown error"
            print(f"[master] macOS 4K mode skipped: could not read displays ({detail}).")
            return

        match = re.search(r'Persistent screen id:\s*([^\s]+)', listed.stdout)
        if not match:
            print("[master] macOS 4K mode skipped: no display id found.")
            return

        display_id = match.group(1)
        cmd = f"id:{display_id} res:3840x2160 scaling:on"
        set_mode = subprocess.run(
            ['displayplacer', cmd],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if set_mode.returncode != 0:
            detail = set_mode.stderr.strip() or set_mode.stdout.strip() or "unknown error"
            print(f"[master] macOS 4K mode failed: {detail}")
            return
        print("[master] macOS display set to 3840x2160.")
    except Exception as exc:
        print(f"[master] macOS 4K mode failed: {exc}")

if __name__ == '__main__':
    _set_macos_resolution_4k()
    PsychLauncher().mainloop()
