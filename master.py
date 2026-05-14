"""
Master entry point for the PsychTest Suite (BART, PVT, Trail Making Test).

Usage:
  python master.py

Or from PsychSuite:
  python launcher.py
"""
import os
import sys

_SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PsychSuite')
os.chdir(_SUITE)
sys.path.insert(0, _SUITE)

from launcher import PsychLauncher  # noqa: E402

if __name__ == '__main__':
    PsychLauncher().mainloop()
