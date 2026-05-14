"""
Shared pause menu utilities for PsychSuite tasks.
"""
from datetime import datetime
import os

from psychopy import visual, event, core


def request_suite_abort(abort_flag_path: str | None):
    """Create an abort flag file so launcher stops remaining tasks."""
    if not abort_flag_path:
        return
    try:
        os.makedirs(os.path.dirname(abort_flag_path), exist_ok=True)
    except Exception:
        pass
    try:
        with open(abort_flag_path, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass


def show_pause_menu(win, title: str, scale_factor: float = 1.0, return_pause_seconds: bool = False):
    """
    Block and return one of:
    - 'resume'
    - 'quit_task'
    - 'quit_battery'
    """
    event.clearEvents()
    prev_mouse_visible = getattr(win, "mouseVisible", True)
    win.mouseVisible = True
    mouse = event.Mouse(win=win)
    was_pressed = False

    btn_w = int(win.size[0] * 0.22)
    btn_h = max(48, int(70 * scale_factor))
    btn_y = -int(130 * scale_factor)
    gap = int(btn_w * 1.1)

    resume_btn = visual.Rect(
        win, width=btn_w, height=btn_h, pos=(-gap, btn_y),
        fillColor="#2d7f2d", lineColor="white"
    )
    quit_btn = visual.Rect(
        win, width=btn_w, height=btn_h, pos=(0, btn_y),
        fillColor="#a36c1f", lineColor="white"
    )
    battery_btn = visual.Rect(
        win, width=btn_w, height=btn_h, pos=(gap, btn_y),
        fillColor="#9f2c2c", lineColor="white"
    )
    resume_lbl = visual.TextStim(
        win, text="Resume (R)", pos=resume_btn.pos,
        height=max(16, int(28 * scale_factor)), color="white", bold=True
    )
    quit_lbl = visual.TextStim(
        win, text="Quit Test (Q)", pos=quit_btn.pos,
        height=max(16, int(28 * scale_factor)), color="white", bold=True
    )
    battery_lbl = visual.TextStim(
        win, text="Quit Battery (X)", pos=battery_btn.pos,
        height=max(16, int(28 * scale_factor)), color="white", bold=True
    )

    pause_start = core.getTime()

    def _finalize(action: str):
        # Prevent key-repeat / held ESC from immediately re-triggering pause.
        event.clearEvents(eventType="keyboard")
        event.clearEvents(eventType="mouse")
        core.wait(0.12)
        try:
            win.mouseVisible = prev_mouse_visible
        except Exception:
            pass
        paused_for = max(0.0, core.getTime() - pause_start)
        if return_pause_seconds:
            return action, paused_for
        return action

    while True:
        bg = visual.Rect(
            win,
            width=win.size[0] * 0.85,
            height=win.size[1] * 0.65,
            fillColor="black",
            lineColor="white",
            opacity=0.88,
        )
        header = visual.TextStim(
            win,
            text=f"{title} Paused",
            pos=(0, int(180 * scale_factor)),
            height=max(24, int(52 * scale_factor)),
            color="yellow",
            bold=True,
        )
        body = visual.TextStim(
            win,
            text=(
                "Use keyboard or click a button.\n\n"
                "R = Resume   |   Q = Quit current test   |   X = Quit entire battery"
            ),
            pos=(0, int(35 * scale_factor)),
            height=max(18, int(34 * scale_factor)),
            wrapWidth=int(win.size[0] * 0.75),
            color="white",
        )
        bg.draw()
        header.draw()
        body.draw()
        resume_btn.draw()
        quit_btn.draw()
        battery_btn.draw()
        resume_lbl.draw()
        quit_lbl.draw()
        battery_lbl.draw()
        win.flip()

        keys = event.getKeys()
        if keys:
            for key in reversed(keys):
                k = str(key).lower()
                if k in ("r", "escape"):
                    return _finalize("resume")
                if k == "q":
                    return _finalize("quit_task")
                if k == "x":
                    return _finalize("quit_battery")

        pressed = mouse.getPressed()[0]
        if pressed and not was_pressed:
            pos = mouse.getPos()
            if resume_btn.contains(pos):
                return _finalize("resume")
            if quit_btn.contains(pos):
                return _finalize("quit_task")
            if battery_btn.contains(pos):
                return _finalize("quit_battery")
        was_pressed = pressed
        core.wait(0.01)
