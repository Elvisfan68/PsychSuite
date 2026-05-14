"""
Display compatibility helpers for PsychSuite.
"""
import sys
from psychopy import event, core


def macos_window_compat_kwargs():
    """
    On macOS external/HiDPI setups, useRetina=True can cause mismatched
    coordinate spaces (blown-up visuals + incorrect hit testing) in fullscreen.
    Disabling Retina backing here keeps drawing and input in one space.
    """
    if sys.platform == "darwin":
        return {"useRetina": False}
    return {}


def effective_scale(win_size, cfg_width, cfg_height):
    """
    Stable UI scale across macOS HiDPI/external monitor modes.
    Uses the smaller of actual drawable size and configured size so controls
    never overshoot the visible frame.
    """
    actual = min(win_size[0] / 1920.0, win_size[1] / 1080.0)
    configured = min(float(cfg_width) / 1920.0, float(cfg_height) / 1080.0)
    return min(actual, configured)


def wait_for_continue(win, allow_escape=True):
    """
    Robust "continue" wait:
    - accepts any keyboard key
    - accepts mouse click
    - optionally returns 'escape'
    """
    mouse = event.Mouse(win=win)
    was_pressed = False
    event.clearEvents()
    while True:
        keys = event.getKeys()
        if keys:
            if allow_escape and any(str(k).lower() == "escape" for k in keys):
                return "escape"
            return "continue"
        pressed = mouse.getPressed()[0]
        if pressed and not was_pressed:
            return "continue"
        was_pressed = pressed
        core.wait(0.01)
