"""
pvt.py — Modernized Psychomotor Vigilance Test (PVT)
Accepts a config dict from the launcher OR runs standalone.
Writes each trial row immediately to Excel (crash-safe).
"""
import sys
import os
import json
import random
import math
import statistics
from datetime import datetime

# Allow import of data_writer when run as subprocess from PsychSuite dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_writer import IncrementalExcelWriter, make_excel_path
from pause_menu import show_pause_menu, request_suite_abort
from timing_quality import FrameTimingMonitor, timing_row_fields, timing_run_fields
from randomization import derive_seed
from metrics_writer import write_derived_metrics
from display_compat import macos_window_compat_kwargs

from psychopy import visual, event, core, gui

SHEET_NAME = 'PVT'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scale(win_size):
    return min(win_size[0] / 1920, win_size[1] / 1080)


# ---------------------------------------------------------------------------
# Main test function
# ---------------------------------------------------------------------------

def run_pvt(config: dict, writer: IncrementalExcelWriter):
    writer.log_session_event('PVT task started')
    pid       = config.get('participant_id', 'unknown')
    treatment = config.get('treatment', '')
    screen_w  = config.get('screen_width', 1920)
    screen_h  = config.get('screen_height', 1080)
    fullscr   = config.get('fullscreen', True)

    duration_min    = float(config.get('pvt_duration_minutes', 5.0))
    isi_min         = float(config.get('pvt_isi_min', 2.0))
    isi_max         = float(config.get('pvt_isi_max', 10.0))
    lapse_threshold = float(config.get('pvt_lapse_threshold_ms', 500))
    timeout_ms      = float(config.get('pvt_timeout_ms', 3000))
    practice_min_valid = int(config.get('pvt_practice_min_valid_responses', 3))
    test_duration   = duration_min * 60
    master_seed     = int(config.get('master_seed', random.SystemRandom().randint(1, 2**31 - 2)))
    replay_exact    = bool(config.get('replay_exact_sequence', False))
    task_seed       = derive_seed(master_seed, 'PVT')
    practice_seed   = derive_seed(task_seed, 'PRACTICE')
    main_seed       = derive_seed(task_seed, 'MAIN')
    practice_rng    = random.Random(practice_seed)
    main_rng        = random.Random(main_seed)

    win = visual.Window(
        size=[screen_w, screen_h],
        fullscr=fullscr,
        monitor='testMonitor',
        units='pix',
        allowGUI=False,
        color='black',
        **macos_window_compat_kwargs(),
    )
    win.mouseVisible = True
    # Use configured resolution for UI scaling (more stable on macOS HiDPI).
    sf = _scale((screen_w, screen_h))
    abort_flag_path = config.get('abort_flag_path')
    timing = FrameTimingMonitor(win)

    led_counter = visual.TextStim(win, text='', pos=(0, 0),
                                  height=int(120 * sf), color='red', bold=True)
    msg = visual.TextStim(win, text='', pos=(0, 0),
                          height=int(36 * sf), color='white',
                          wrapWidth=int(1200 * sf))

    try:
        writer.log_session_event(
            f"SEED task=PVT replay={replay_exact} master={master_seed} task={task_seed}"
        )
        writer.log_session_event(
            f"DISPLAY task=PVT requested={screen_w}x{screen_h} fullscr={fullscr} actual={win.size[0]}x{win.size[1]} useRetina={getattr(win, 'useRetina', 'na')}"
        )
        writer.log_session_event(f"SEED task=PVT block=PRACTICE seed={practice_seed}")
        writer.log_session_event(f"SEED task=PVT block=MAIN seed={main_seed}")
        early_exit_shown = False
        paused_total = 0.0
        valid_rts_ms = []
        lapse_count = 0
        false_start_count = 0

        def now():
            return core.getTime() - paused_total

        def _show_early_exit_message(mode_text: str):
            nonlocal early_exit_shown
            early_exit_shown = True
            msg.setText(
                f"PVT Ended Early\n\n{mode_text}\n\nData has been saved.\n\nPress any key to continue."
            )
            msg.draw()
            win.flip()
            event.waitKeys()

        def _pause_or_exit():
            nonlocal paused_total
            action, pause_s = show_pause_menu(
                win, title='PVT', scale_factor=sf, return_pause_seconds=True
            )
            paused_total += pause_s
            if action == 'resume':
                return 'resume'
            if action == 'quit_battery':
                request_suite_abort(abort_flag_path)
                _show_early_exit_message('Battery stopped by experimenter.')
            elif action == 'quit_task':
                _show_early_exit_message('Task ended by experimenter.')
            return 'quit'

        def _run_practice_gate():
            """
            Mandatory short practice:
            - at least `practice_min_valid` valid responses
            - no repeated false starts (no 2 consecutive false starts)
            """
            while True:
                msg.setText(
                    "PVT Practice Check\n\n"
                    "Please complete a short practice first.\n"
                    "Take as much time as you need on this part.\n\n"
                    f"Pass criteria:\n"
                    f"• At least {practice_min_valid} valid responses\n"
                    f"• No repeated false starts\n\n"
                    "Press SPACEBAR to begin practice."
                )
                msg.draw(); win.flip()
                keys = event.waitKeys(keyList=['space', 'escape'])
                if 'escape' in keys:
                    if _pause_or_exit() == 'quit':
                        return False
                    continue

                valid = 0
                consecutive_false_starts = 0
                practice_trials = 0
                failed = False
                max_practice_trials = max(8, practice_min_valid * 3)

                while practice_trials < max_practice_trials and valid < practice_min_valid and not failed:
                    practice_trials += 1
                    isi = practice_rng.uniform(1.5, 3.0)
                    isi_start = now()
                    false_start = False

                    while (now() - isi_start) < isi:
                        win.flip()
                        keys = event.getKeys(keyList=['space', 'escape'])
                        if 'escape' in keys:
                            if _pause_or_exit() == 'quit':
                                return False
                            continue
                        if 'space' in keys:
                            false_start = True
                            consecutive_false_starts += 1
                            fs = visual.TextStim(
                                win, text='FALSE START\nWait for the number!',
                                pos=(0, 0), height=int(60 * sf), color='orange', bold=True
                            )
                            fs.draw(); win.flip(); core.wait(1.0)
                            if consecutive_false_starts >= 2:
                                failed = True
                            break
                        core.wait(0.01)

                    if failed:
                        break
                    if false_start:
                        continue

                    stim_onset = now()
                    responded = False
                    while not responded:
                        elapsed_ms = (now() - stim_onset) * 1000
                        led_counter.setText(f'{int(elapsed_ms)}')
                        led_counter.draw()
                        win.flip()
                        keys = event.getKeys(keyList=['space', 'escape'])
                        if 'escape' in keys:
                            if _pause_or_exit() == 'quit':
                                return False
                            continue
                        if 'space' in keys:
                            valid += 1
                            consecutive_false_starts = 0
                            responded = True
                        elif elapsed_ms > max(timeout_ms, 3000):
                            consecutive_false_starts = 0
                            responded = True

                    core.wait(0.08)

                if valid >= practice_min_valid and not failed:
                    msg.setText(
                        "Practice passed.\n\n"
                        "Great job. You are ready for the full test.\n\n"
                        "Press SPACEBAR to continue."
                    )
                    msg.draw(); win.flip()
                    event.waitKeys(keyList=['space'])
                    return True

                msg.setText(
                    "Practice not passed yet.\n\n"
                    "Remember: wait for the number, then respond quickly.\n"
                    "Take as much time as you need on this practice part.\n\n"
                    "Press SPACEBAR to retry."
                )
                msg.draw(); win.flip()
                keys = event.waitKeys(keyList=['space', 'escape'])
                if 'escape' in keys and _pause_or_exit() == 'quit':
                    return False

        # ── Instructions ──────────────────────────────────────────────────
        msg.setText(
            f"Psychomotor Vigilance Test\n\n"
            f"Watch the center of the screen.\n"
            f"When a RED NUMBER appears, press SPACEBAR as fast as possible.\n\n"
            f"Duration: {duration_min:.0f} min  |  Lapse threshold: {lapse_threshold:.0f} ms\n\n"
            f"Press ESCAPE for the pause menu at any time.\n"
            f"Press SPACEBAR to begin."
        )
        msg.pos = (0, 0)
        msg.draw()
        win.flip()

        while True:
            keys = event.waitKeys(keyList=['space', 'escape'])
            if 'space' in keys:
                break
            if 'escape' in keys:
                if _pause_or_exit() == 'quit':
                    return

        if not _run_practice_gate():
            return

        # ── Countdown ─────────────────────────────────────────────────────
        for n in [3, 2, 1]:
            cd = visual.TextStim(win, text=str(n), pos=(0, 0),
                                 height=int(200 * sf), color='white', bold=True)
            cd.draw(); win.flip()
            core.wait(0.5)
            if event.getKeys(keyList=['escape']):
                if _pause_or_exit() == 'quit':
                    return
            core.wait(0.5)

        go = visual.TextStim(win, text='BEGIN', pos=(0, 0),
                             height=int(150 * sf), color='green', bold=True)
        go.draw(); win.flip()
        core.wait(1.0)

        # ── Main loop ─────────────────────────────────────────────────────
        start_time    = now()
        trial_number  = 0
        test_aborted  = False

        win.flip()  # blank screen

        while (now() - start_time) < test_duration and not test_aborted:
            trial_number += 1
            isi       = main_rng.uniform(isi_min, isi_max)
            isi_start = now()
            premature = False
            trial_seg = {
                'frame_count': 0,
                'dropped_frames': 0,
                'max_interval_ms': 0.0,
                'threshold_ms': 0.0,
                'expected_frame_ms': 0.0,
                'exceeded_threshold': False,
            }
            timing.start_segment()

            # ISI wait
            while (now() - isi_start) < isi and not test_aborted:
                win.flip()
                keys = event.getKeys(keyList=['space', 'escape'])
                if 'escape' in keys:
                    m = timing.end_segment()
                    trial_seg['frame_count'] += m['frame_count']
                    trial_seg['dropped_frames'] += m['dropped_frames']
                    trial_seg['max_interval_ms'] = max(trial_seg['max_interval_ms'], m['max_interval_ms'])
                    trial_seg['threshold_ms'] = m['threshold_ms']
                    trial_seg['expected_frame_ms'] = m['expected_frame_ms']
                    trial_seg['exceeded_threshold'] = trial_seg['exceeded_threshold'] or m['exceeded_threshold']
                    if _pause_or_exit() == 'quit':
                        test_aborted = True
                        break
                    timing.start_segment()
                if 'space' in keys:
                    m = timing.end_segment()
                    trial_seg['frame_count'] += m['frame_count']
                    trial_seg['dropped_frames'] += m['dropped_frames']
                    trial_seg['max_interval_ms'] = max(trial_seg['max_interval_ms'], m['max_interval_ms'])
                    trial_seg['threshold_ms'] = m['threshold_ms']
                    trial_seg['expected_frame_ms'] = m['expected_frame_ms']
                    trial_seg['exceeded_threshold'] = trial_seg['exceeded_threshold'] or m['exceeded_threshold']
                    premature = True
                    row = {
                        'Timestamp':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'ID':           pid,
                        'Treatment':    treatment,
                        'Trial':        trial_number,
                        'ISI_ms':       round(isi * 1000, 2),
                        'RT_ms':        'FALSE_START',
                        'Lapse':        False,
                        'FalseStart':   True,
                        'TimeInTest_s': round(now() - start_time, 3),
                    }
                    row.update(timing_row_fields(trial_seg))
                    writer.write_row(row)
                    false_start_count += 1
                    fs = visual.TextStim(win, text='FALSE START\nWait for the number!',
                                        pos=(0, 0), height=int(60 * sf),
                                        color='orange', bold=True)
                    fs.draw(); win.flip()
                    core.wait(1.5)
                    break
                core.wait(0.01)

            if premature or test_aborted:
                continue

            # Stimulus
            stim_onset  = now()
            responded   = False
            response_rt = None
            timing.start_segment()

            while not responded and not test_aborted:
                elapsed_ms = (now() - stim_onset) * 1000
                led_counter.setText(f'{int(elapsed_ms)}')
                led_counter.draw()
                win.flip()

                keys = event.getKeys(keyList=['space', 'escape'])
                for key in keys:
                    if key == 'escape':
                        m = timing.end_segment()
                        trial_seg['frame_count'] += m['frame_count']
                        trial_seg['dropped_frames'] += m['dropped_frames']
                        trial_seg['max_interval_ms'] = max(trial_seg['max_interval_ms'], m['max_interval_ms'])
                        trial_seg['threshold_ms'] = m['threshold_ms']
                        trial_seg['expected_frame_ms'] = m['expected_frame_ms']
                        trial_seg['exceeded_threshold'] = trial_seg['exceeded_threshold'] or m['exceeded_threshold']
                        if _pause_or_exit() == 'quit':
                            test_aborted = True
                            break
                        timing.start_segment()
                        continue
                    if key == 'space':
                        m = timing.end_segment()
                        trial_seg['frame_count'] += m['frame_count']
                        trial_seg['dropped_frames'] += m['dropped_frames']
                        trial_seg['max_interval_ms'] = max(trial_seg['max_interval_ms'], m['max_interval_ms'])
                        trial_seg['threshold_ms'] = m['threshold_ms']
                        trial_seg['expected_frame_ms'] = m['expected_frame_ms']
                        trial_seg['exceeded_threshold'] = trial_seg['exceeded_threshold'] or m['exceeded_threshold']
                        response_rt = elapsed_ms
                        responded = True; break

                if elapsed_ms > timeout_ms:
                    m = timing.end_segment()
                    trial_seg['frame_count'] += m['frame_count']
                    trial_seg['dropped_frames'] += m['dropped_frames']
                    trial_seg['max_interval_ms'] = max(trial_seg['max_interval_ms'], m['max_interval_ms'])
                    trial_seg['threshold_ms'] = m['threshold_ms']
                    trial_seg['expected_frame_ms'] = m['expected_frame_ms']
                    trial_seg['exceeded_threshold'] = trial_seg['exceeded_threshold'] or m['exceeded_threshold']
                    responded = True

            if test_aborted:
                break

            is_lapse = (response_rt is None) or (response_rt > lapse_threshold)
            row = {
                'Timestamp':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ID':           pid,
                'Treatment':    treatment,
                'Trial':        trial_number,
                'ISI_ms':       round(isi * 1000, 2),
                'RT_ms':        round(response_rt, 2) if response_rt is not None else 'NO_RESPONSE',
                'Lapse':        is_lapse,
                'FalseStart':   False,
                'TimeInTest_s': round(now() - start_time, 3),
            }
            row.update(timing_row_fields(trial_seg))
            writer.write_row(row)
            if response_rt is not None:
                valid_rts_ms.append(float(response_rt))
            if is_lapse:
                lapse_count += 1

            win.flip()
            core.wait(0.1)

        # ── Results ───────────────────────────────────────────────────────
        actual_dur = now() - start_time
        status = "ABORTED" if test_aborted else "COMPLETED"
        run_summary = timing.run_summary()
        writer.write_row({
            'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ID': pid,
            'Treatment': treatment,
            'Trial': '__RUN_SUMMARY__',
            'ISI_ms': '',
            'RT_ms': '',
            'Lapse': '',
            'FalseStart': '',
            'TimeInTest_s': round(actual_dur, 3),
            **timing_row_fields({
                'dropped_frames': '',
                'max_interval_ms': '',
                'exceeded_threshold': '',
                'threshold_ms': '',
                'expected_frame_ms': '',
            }, run_fields_blank=False),
            **timing_run_fields(run_summary),
        })
        if valid_rts_ms:
            sorted_rts = sorted(valid_rts_ms)
            k = max(1, int(math.ceil(len(sorted_rts) * 0.10)))
            fastest10 = sorted_rts[:k]
            slowest10 = sorted_rts[-k:]
            median_rt = statistics.median(sorted_rts)
            fastest10_mean = statistics.mean(fastest10)
            slowest10_mean = statistics.mean(slowest10)
        else:
            median_rt = fastest10_mean = slowest10_mean = ""
        write_derived_metrics(
            excel_path=config["excel_path"],
            task="PVT",
            participant_id=pid,
            treatment=treatment,
            metrics={
                "Completion_Status": status,
                "PVT_Median_RT_ms": round(median_rt, 3) if median_rt != "" else "",
                "PVT_Lapses": lapse_count,
                "PVT_False_Starts": false_start_count,
                "PVT_Fastest10_Mean_RT_ms": round(fastest10_mean, 3) if fastest10_mean != "" else "",
                "PVT_Slowest10_Mean_RT_ms": round(slowest10_mean, 3) if slowest10_mean != "" else "",
                "PVT_Valid_Response_Count": len(valid_rts_ms),
            },
        )
        if not early_exit_shown:
            msg.setText(
                f"PVT {status}\n\n"
                f"Duration: {actual_dur:.1f} s\n\n"
                f"Timing Quality Score: {run_summary['run_quality_score']:.2f}\n\n"
                f"Data saved to Excel.\n\n"
                f"Press any key to continue."
            )
            msg.draw(); win.flip()
            event.waitKeys()

    finally:
        try:
            writer.log_session_event('PVT ended (session closed)')
        except Exception:
            pass
        win.close()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _standalone_config():
    info = {'Participant ID': '', 'Treatment': ''}
    dlg = gui.DlgFromDict(info, title='PVT — Standalone')
    if not dlg.OK:
        core.quit()
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data')
    return {
        'participant_id': info['Participant ID'],
        'treatment':      info['Treatment'],
        'screen_width': 1920, 'screen_height': 1080, 'fullscreen': True,
        'pvt_duration_minutes': 5.0,
        'pvt_isi_min': 2.0, 'pvt_isi_max': 10.0,
        'pvt_lapse_threshold_ms': 500, 'pvt_timeout_ms': 3000,
        'excel_path': make_excel_path(data_dir, info['Participant ID'], info['Treatment']),
    }


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            config = json.load(f)
    else:
        config = _standalone_config()

    writer = IncrementalExcelWriter(config['excel_path'], SHEET_NAME)
    try:
        run_pvt(config, writer)
    finally:
        writer.close()
