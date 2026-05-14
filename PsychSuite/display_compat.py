"""
Display compatibility helpers for PsychSuite.
"""
import sys


def macos_window_compat_kwargs():
    """
    On macOS external/HiDPI setups, useRetina=True can cause mismatched
    coordinate spaces (blown-up visuals + incorrect hit testing) in fullscreen.
    Disabling Retina backing here keeps drawing and input in one space.
    """
    if sys.platform == "darwin":
        return {"useRetina": False}
    return {}
