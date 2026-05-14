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

        # Parse each display block and prefer exact 4K modes advertised by displayplacer.
        blocks = re.split(r'(?=Persistent screen id:)', listed.stdout)
        candidates = []
        for block in blocks:
            id_match = re.search(r'Persistent screen id:\s*([^\s]+)', block)
            if not id_match:
                continue
            display_id = id_match.group(1)
            mode_specs = re.findall(
                r'^\s*mode\s+\d+:\s*(.*res:3840x2160[^\n]*)$',
                block,
                flags=re.MULTILINE,
            )
            for mode in mode_specs:
                mode_spec = " ".join(mode.strip().split())
                rank = 1 if 'scaling:on' in mode_spec else 2
                candidates.append((rank, f"id:{display_id} {mode_spec}"))

        # Fallbacks for setups where list output does not expose full mode detail.
        fallback_ids = re.findall(r'Persistent screen id:\s*([^\s]+)', listed.stdout)
        for display_id in fallback_ids:
            candidates.append((10, f"id:{display_id} res:3840x2160 scaling:on"))
            candidates.append((11, f"id:{display_id} res:3840x2160 scaling:off"))
            candidates.append((12, f"id:{display_id} res:3840x2160"))

        if not candidates:
            print("[master] macOS 4K mode skipped: no displays found in displayplacer output.")
            return

        candidates.sort(key=lambda item: item[0])
        for _, cmd in candidates:
            set_mode = subprocess.run(
                ['displayplacer', cmd],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if set_mode.returncode == 0:
                print("[master] macOS display set to 3840x2160.")
                return

        detail = set_mode.stderr.strip() or set_mode.stdout.strip() or "unknown error"
        print(f"[master] macOS 4K mode failed: {detail}")
    except Exception as exc:
        print(f"[master] macOS 4K mode failed: {exc}")

if __name__ == '__main__':
    _set_macos_resolution_4k()
    PsychLauncher().mainloop()
