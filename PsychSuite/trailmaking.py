"""
trailmaking.py — Modernized Trail Making Test (TMT)
Accepts a config dict from the launcher OR runs standalone.
Writes each click/connection row immediately to Excel (crash-safe).
"""
import sys, os, json, random
from itertools import permutations
import statistics
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_writer import IncrementalExcelWriter, make_excel_path
from pause_menu import show_pause_menu, request_suite_abort
from timing_quality import FrameTimingMonitor, timing_row_fields, timing_run_fields
from randomization import derive_seed
from metrics_writer import write_derived_metrics

from psychopy import visual, event, core, gui

SHEET_NAME = 'TMT'

# ---------------------------------------------------------------------------
# Geometry / stimulus helpers  (unchanged from V4)
# ---------------------------------------------------------------------------

def _scale(win_size):
    return min(win_size[0] / 1920, win_size[1] / 1080)

def check_overlap(new_pos, existing, radius):
    for (x, y) in existing:
        if np.sqrt((new_pos[0]-x)**2 + (new_pos[1]-y)**2) < radius * 2:
            return True
    return False

def generate_positions(n, radius, win_size, reserve_bottom=False, max_attempts=1000):
    positions, attempts = [], 0
    margin = radius * 2
    bot_margin = int(win_size[1] * 0.3) if reserve_bottom else margin
    while len(positions) < n and attempts < max_attempts:
        p = (np.random.randint(-win_size[0]//2 + margin, win_size[0]//2 - margin),
             np.random.randint(-win_size[1]//2 + bot_margin, win_size[1]//2 - margin))
        if not check_overlap(p, positions, radius):
            positions.append(p)
        attempts += 1
    return positions

def get_shape_names(count=6):
    return ['triangle','square','pentagon','hexagon','heptagon','octagon'][:count]

def create_shape(win, shape_name, pos, size=35, lineColor='black', scale_factor=1.0):
    colors = {'triangle':'red','square':'orange','pentagon':'yellow',
              'hexagon':'green','heptagon':'blue','octagon':'indigo'}
    fc = colors.get(shape_name, 'white')
    ss = size * scale_factor
    lw = max(1, int(2 * scale_factor))

    if shape_name == 'triangle':
        verts = [[ss*np.cos(i*2*np.pi/3 - np.pi/2),
                  ss*np.sin(i*2*np.pi/3 - np.pi/2)] for i in range(3)]
        return visual.ShapeStim(win, vertices=verts, pos=pos,
                                fillColor=fc, lineColor=lineColor, lineWidth=lw)
    if shape_name == 'square':
        return visual.Rect(win, width=ss*1.8, height=ss*1.8, pos=pos,
                           fillColor=fc, lineColor=lineColor, lineWidth=lw)
    sides = {'pentagon':5,'hexagon':6,'heptagon':7,'octagon':8}.get(shape_name, 5)
    verts = [[ss*np.cos(i*2*np.pi/sides - np.pi/2),
              ss*np.sin(i*2*np.pi/sides - np.pi/2)] for i in range(sides)]
    return visual.ShapeStim(win, vertices=verts, pos=pos,
                            fillColor=fc, lineColor=lineColor, lineWidth=lw)

def create_sequence(categories, seq_type, n=6):
    nums    = list(range(1, n+1))
    letters = ['A','B','C','D','E','F','G','H','I','J'][:n]
    shapes  = get_shape_names(n)

    if seq_type == 'descending':
        nums = nums[::-1]; letters = letters[::-1]; shapes = shapes[::-1]

    if len(categories) == 1:
        cat = categories[0]
        return nums if cat=='numbers' else (letters if cat=='letters' else shapes)

    # Multi-category: interleave in category order
    pools = {'numbers': nums, 'letters': letters, 'shapes': shapes}
    seq = []
    for i in range(n * len(categories)):
        cat = categories[i % len(categories)]
        idx = i // len(categories)
        if idx < n:
            seq.append(pools[cat][idx])
    return seq

def draw_instruction_visuals(win, categories, seq_type, scale_factor, y_offset=0):
    n = 6
    y_start = (200 + y_offset) * scale_factor
    row_gap  = 80 * scale_factor
    dot_r    = 25 * scale_factor
    th       = 32 * scale_factor
    ss       = 22 * scale_factor
    nums    = list(range(1, n+1))
    letters = ['A','B','C','D','E','F']
    shapes  = get_shape_names(n)
    if seq_type == 'descending':
        nums = nums[::-1]; letters = letters[::-1]; shapes = shapes[::-1]
    pools = {'numbers': nums, 'letters': letters, 'shapes': shapes}

    for idx, cat in enumerate(categories):
        y = y_start - idx * row_gap
        x0 = -180 * scale_factor
        for i, val in enumerate(pools[cat]):
            x = x0 + i * 65 * scale_factor
            if cat == 'shapes':
                create_shape(win, val, (x, y), size=ss, scale_factor=1.0).draw()
            else:
                visual.Circle(win, radius=dot_r, pos=(x, y),
                              fillColor='white', lineColor='black').draw()
                visual.TextStim(win, text=str(val), pos=(x, y),
                                height=th, color='black').draw()
        visual.TextStim(win, text=cat.capitalize(),
                        pos=(x0 - 120*scale_factor, y),
                        height=th, color='red', bold=True).draw()

# ---------------------------------------------------------------------------
# Single trial runner
# ---------------------------------------------------------------------------

def run_trial(win, trial_name, sequence, instructions_text, pid, treatment,
              writer, timing_monitor, abort_flag_path=None, seq_type=None, cat_order=None):
    sf = _scale(win.size)
    circ_r   = int(45 * sf)
    stim_h   = int(40 * sf)
    shape_sz = int(35 * sf)
    lw       = max(1, int(3 * sf))
    instr_h  = int(50 * sf)
    wrap_w   = int(1200 * sf)

    is_mixed = seq_type and cat_order and ('Experimental' in trial_name or 'Mixed' in trial_name)

    # ── Instructions ────────────────────────────────────────────────────────
    instr_stim = visual.TextStim(win, text=instructions_text, height=instr_h,
                                 wrapWidth=wrap_w,
                                 pos=(0, 300*sf) if is_mixed else (0, 0),
                                 color='white')
    instr_stim.draw()
    if is_mixed:
        draw_instruction_visuals(win, cat_order, seq_type, sf, y_offset=-250)
    win.flip()
    while True:
        keys = event.waitKeys()
        if 'escape' not in keys:
            break
        action = show_pause_menu(win, title='Trail Making Test', scale_factor=sf)
        if action == 'resume':
            instr_stim.draw()
            if is_mixed:
                draw_instruction_visuals(win, cat_order, seq_type, sf, y_offset=-250)
            win.flip()
            continue
        if action == 'quit_battery':
            request_suite_abort(abort_flag_path)
            return {'status': 'quit_battery'}
        return {'status': 'quit_task'}

    # ── Build stimuli ────────────────────────────────────────────────────────
    n = len(sequence)
    reserve = bool(is_mixed)
    positions = generate_positions(n, circ_r, win.size, reserve_bottom=reserve)

    bg_circles, stimuli = [], []
    for i in range(n):
        bg = visual.Circle(win, radius=circ_r, pos=positions[i],
                           fillColor='lightgray', lineColor='black',
                           lineWidth=max(1, int(2*sf)))
        bg_circles.append(bg)
        item = sequence[i]
        if isinstance(item, int):
            s = visual.TextStim(win, text=str(item), pos=positions[i],
                                height=stim_h, color='black')
        elif isinstance(item, str) and len(item) == 1:
            s = visual.TextStim(win, text=item, pos=positions[i],
                                height=stim_h, color='black')
        else:
            s = create_shape(win, item, positions[i], size=shape_sz,
                             lineColor='black', scale_factor=1.0)
        stimuli.append(s)

    # Corner labels for mixed/experimental
    corner_labels = []
    if is_mixed:
        ly1 = -win.size[1]//2 + int(120*sf)
        ly2 = -win.size[1]//2 + int(80*sf)
        corner_labels = [
            visual.TextStim(win, text=f"Order: {seq_type.capitalize()}",
                            pos=(0, ly1), height=int(30*sf), color='red', bold=True),
            visual.TextStim(win, text=f"Categories: {' → '.join(cat_order)}",
                            pos=(0, ly2), height=int(30*sf), color='red', bold=True,
                            wrapWidth=win.size[0]),
        ]

    # ── Trial loop ───────────────────────────────────────────────────────────
    mouse         = event.Mouse(win=win)
    paused_total  = 0.0
    def trial_now():
        return core.getTime() - paused_total
    trial_start   = trial_now()
    lines         = []
    responses     = []
    total_errors  = 0
    click_rts_ms  = []
    near_miss_total = 0
    repeated_same_wrong_total = 0
    correction_latency_list_ms = []

    for target_idx in range(n):
        found  = False
        target_start = trial_now()
        wrong_this  = 0
        prev_wrong  = set()
        wrong_clicks_by_index = {}
        repeated_same_wrong_target = 0
        near_miss_count = 0
        wrong_target_clicks_total = 0
        first_wrong_total_time_ms = None
        seg = {
            'frame_count': 0,
            'dropped_frames': 0,
            'max_interval_ms': 0.0,
            'threshold_ms': 0.0,
            'expected_frame_ms': 0.0,
            'exceeded_threshold': False,
        }
        timing_monitor.start_segment()

        while not found:
            if event.getKeys(keyList=['escape']):
                m = timing_monitor.end_segment()
                seg['frame_count'] += m['frame_count']
                seg['dropped_frames'] += m['dropped_frames']
                seg['max_interval_ms'] = max(seg['max_interval_ms'], m['max_interval_ms'])
                seg['threshold_ms'] = m['threshold_ms']
                seg['expected_frame_ms'] = m['expected_frame_ms']
                seg['exceeded_threshold'] = seg['exceeded_threshold'] or m['exceeded_threshold']
                action, pause_s = show_pause_menu(
                    win, title='Trail Making Test', scale_factor=sf, return_pause_seconds=True
                )
                paused_total += pause_s
                if action == 'resume':
                    timing_monitor.start_segment()
                    continue
                if action == 'quit_battery':
                    request_suite_abort(abort_flag_path)
                    return {'status': 'quit_battery'}
                return {'status': 'quit_task'}

            for line in lines:
                line.draw()

            for i, bg in enumerate(bg_circles):
                if i < len(responses):
                    bg.fillColor = 'lightgreen'
                    bg.lineColor = 'yellowgreen' if i == responses[-1] else 'black'
                    bg.lineWidth = max(1, int(8*sf)) if i == responses[-1] else max(1, int(2*sf))
                elif i in prev_wrong:
                    bg.fillColor = 'lightcoral'
                else:
                    bg.fillColor = 'lightgray'
                    bg.lineColor = 'black'
                    bg.lineWidth = max(1, int(2*sf))
                bg.draw()

            for s in stimuli:
                s.draw()
            for lbl in corner_labels:
                lbl.draw()

            mp      = mouse.getPos()
            clicked = mouse.getPressed()[0]
            for i, bg in enumerate(bg_circles):
                if bg.contains(mp):
                    if i == target_idx:
                        bg.fillColor = 'yellow'
                        if clicked:
                            m = timing_monitor.end_segment()
                            seg['frame_count'] += m['frame_count']
                            seg['dropped_frames'] += m['dropped_frames']
                            seg['max_interval_ms'] = max(seg['max_interval_ms'], m['max_interval_ms'])
                            seg['threshold_ms'] = m['threshold_ms']
                            seg['expected_frame_ms'] = m['expected_frame_ms']
                            seg['exceeded_threshold'] = seg['exceeded_threshold'] or m['exceeded_threshold']
                            rt     = (trial_now() - target_start) * 1000
                            t_time = (trial_now() - trial_start) * 1000
                            correction_latency_ms = (
                                (t_time - first_wrong_total_time_ms)
                                if first_wrong_total_time_ms is not None else 0.0
                            )
                            conn   = (f"{sequence[responses[-1]]}-{sequence[i]}"
                                      if responses else f"Start-{sequence[i]}")
                            if responses:
                                lines.append(visual.Line(win,
                                    start=positions[responses[-1]], end=positions[i],
                                    color='red', lineWidth=lw))

                            row = {
                                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'ID': pid,
                                'Treatment': treatment,
                                'Trial_Name': trial_name,
                                'Connection': conn,
                                'Reaction_Time_ms': round(rt, 2),
                                'Total_Time_ms': round(t_time, 2),
                                'Wrong_Guesses_Before_Correct': wrong_this,
                                'Wrong_Target_Clicks_Total': wrong_target_clicks_total,
                                'Near_Miss_Count': near_miss_count,
                                'Repeated_Same_Wrong_Target': repeated_same_wrong_target,
                                'Correction_Latency_ms': round(correction_latency_ms, 2),
                            }
                            row.update(timing_row_fields(seg))

                            writer.write_row(row)
                            click_rts_ms.append(float(rt))
                            near_miss_total += near_miss_count
                            repeated_same_wrong_total += repeated_same_wrong_target
                            correction_latency_list_ms.append(float(correction_latency_ms))
                            responses.append(i)
                            found = True
                            while mouse.getPressed()[0]:
                                core.wait(0.01)
                            break
                    else:
                        if i not in prev_wrong:
                            bg.fillColor = 'orange'
                        if clicked:
                            wrong_target_clicks_total += 1
                            wrong_clicks_by_index[i] = wrong_clicks_by_index.get(i, 0) + 1
                            if wrong_clicks_by_index[i] > 1:
                                repeated_same_wrong_target += 1
                            if first_wrong_total_time_ms is None:
                                first_wrong_total_time_ms = trial_now() * 1000

                            # Near-miss: clicked wrong target is spatially close to current correct target.
                            dx = positions[i][0] - positions[target_idx][0]
                            dy = positions[i][1] - positions[target_idx][1]
                            if float(np.sqrt(dx * dx + dy * dy)) <= (circ_r * 2.0):
                                near_miss_count += 1

                        if clicked and i not in prev_wrong:
                            bg.fillColor = 'lightcoral'
                            wrong_this  += 1
                            total_errors += 1
                            prev_wrong.add(i)
                        if clicked:
                            while mouse.getPressed()[0]:
                                core.wait(0.01)

            win.flip()
            core.wait(0.01)

    comp_t = trial_now() - trial_start
    fb = visual.TextStim(win,
        text=f'Trial Complete!\n\nTime: {comp_t:.2f}s  |  Errors: {total_errors}\n\nPress any key.',
        height=int(50*sf))
    fb.draw(); win.flip()
    event.waitKeys()
    return {
        'status': 'completed',
        'total_errors': total_errors,
        'corrected_error_burden': total_errors,
        'completion_time_s': comp_t,
        'click_rts_ms': click_rts_ms,
        'click_count': len(click_rts_ms),
        'near_miss_total': near_miss_total,
        'repeated_same_wrong_total': repeated_same_wrong_total,
        'correction_latency_mean_ms': (
            statistics.mean(correction_latency_list_ms) if correction_latency_list_ms else 0.0
        ),
    }


# ---------------------------------------------------------------------------
# Main experiment function
# ---------------------------------------------------------------------------

def run_tmt(config: dict, writer: IncrementalExcelWriter):
    writer.log_session_event('TMT task started')
    pid       = config.get('participant_id', 'unknown')
    treatment = config.get('treatment', '')
    screen_w  = config.get('screen_width', 1920)
    screen_h  = config.get('screen_height', 1080)
    fullscr   = config.get('fullscreen', True)
    abort_flag_path = config.get('abort_flag_path')

    n_elem         = int(config.get('tmt_elements_per_category', 6))
    use_numbers    = config.get('tmt_use_numbers', True)
    use_letters    = config.get('tmt_use_letters', True)
    use_shapes     = config.get('tmt_use_shapes', True)
    run_fam        = config.get('tmt_run_familiarization', True)
    use_legacy_mixed_order = config.get('tmt_use_legacy_mixed_order', False)
    practice_max_errors = int(config.get('tmt_practice_max_errors', 1))
    master_seed    = int(config.get('master_seed', random.SystemRandom().randint(1, 2**31 - 2)))
    replay_exact   = bool(config.get('replay_exact_sequence', False))
    task_seed      = derive_seed(master_seed, 'TMT')
    plan_seed      = derive_seed(task_seed, 'TRIAL_PLAN')
    plan_rng       = random.Random(plan_seed)

    categories = []
    if use_numbers: categories.append('numbers')
    if use_letters: categories.append('letters')
    if use_shapes:  categories.append('shapes')

    if not categories:
        categories = ['numbers', 'letters', 'shapes']

    win = visual.Window(size=[screen_w, screen_h], fullscr=fullscr,
                        monitor='testMonitor', color='black',
                        units='pix', allowGUI=False)
    win.mouseVisible = True
    sf  = _scale(win.size)
    ww  = int(800 * sf)
    th  = int(50 * sf)
    timing = FrameTimingMonitor(win)

    try:
        writer.log_session_event(
            f"SEED task=TMT replay={replay_exact} master={master_seed} task={task_seed}"
        )
        writer.log_session_event(f"SEED task=TMT block=TRIAL_PLAN seed={plan_seed}")
        # Welcome
        visual.TextStim(win,
            text='Trail Making Test\n\nClick each item in the correct sequence.\n\nPress any key to begin.',
            height=th, wrapWidth=ww).draw()
        win.flip()
        while True:
            keys = event.waitKeys()
            if 'escape' not in keys:
                break
            action = show_pause_menu(win, title='Trail Making Test', scale_factor=sf)
            if action == 'resume':
                visual.TextStim(win,
                    text='Trail Making Test\n\nClick each item in the correct sequence.\n\nPress any key to begin.',
                    height=th, wrapWidth=ww).draw()
                win.flip()
                continue
            if action == 'quit_battery':
                request_suite_abort(abort_flag_path)
            return

        # Mandatory short competency practice (kept separate from optional familiarization)
        while True:
            practice_seq = [1, 2, 3, 4]
            practice_instruction = (
                "Mandatory TMT Practice\n\n"
                "Connect 1 -> 2 -> 3 -> 4.\n"
                "Take as much time as you need on this practice part.\n\n"
                f"Pass criteria: errors <= {practice_max_errors}\n\n"
                "Press any key to start."
            )
            p = run_trial(
                win,
                trial_name='PracticeGate_TMT',
                sequence=practice_seq,
                instructions_text=practice_instruction,
                pid=pid,
                treatment=treatment,
                writer=writer,
                timing_monitor=timing,
                abort_flag_path=abort_flag_path,
                seq_type=None,
                cat_order=None,
            )
            if p['status'] == 'quit_battery':
                return
            if p['status'] == 'quit_task':
                return
            if p.get('total_errors', 9999) <= practice_max_errors:
                visual.TextStim(
                    win,
                    text='Practice passed.\n\nYou are ready to begin the task.\n\nPress any key.',
                    height=th,
                    wrapWidth=ww,
                ).draw()
                win.flip()
                event.waitKeys()
                break

            visual.TextStim(
                win,
                text=(
                    "Practice not passed yet.\n\n"
                    "Please try again.\n"
                    "Take as much time as you need on this practice part.\n\n"
                    "Press any key to retry."
                ),
                height=th,
                wrapWidth=ww,
            ).draw()
            win.flip()
            event.waitKeys()

        # ── Build trial list ────────────────────────────────────────────────
        trials = []
        exp_trial_count = 0
        exp_completion_s = 0.0
        exp_total_errors = 0
        exp_corrected_error_burden = 0
        exp_click_rts = []
        exp_near_miss_total = 0
        exp_repeated_same_wrong_total = 0
        exp_correction_latency_means = []

        if run_fam:
            for cat in [c for c in ['numbers','letters','shapes'] if c in categories]:
                label = cat.capitalize()
                trials.append((
                    f'Familiarization_{label}_Asc', [cat], 'ascending',
                    f'Familiarization: {label} Ascending\n\nPress any key to start.'
                ))
                trials.append((
                    f'Familiarization_{label}_Desc', [cat], 'descending',
                    f'Familiarization: {label} Descending\n\nPress any key to start.'
                ))

            if len(categories) > 1:
                cat_str_asc  = ' → '.join(categories)
                cat_str_desc = ' → '.join(categories[::-1])
                trials.append((
                    'Familiarization_Mixed_Asc', categories, 'ascending',
                    f'Familiarization: Mixed Ascending\nOrder: {cat_str_asc}\n\nPress any key to start.'
                ))
                trials.append((
                    'Familiarization_Mixed_Desc', categories, 'descending',
                    f'Familiarization: Mixed Descending\nOrder: {cat_str_desc}\n\nPress any key to start.'
                ))

        # Experimental mixed trials
        if len(categories) > 1:
            if use_legacy_mixed_order and len(categories) == 3:
                # Legacy mode: match old script's fixed 3-order set.
                legacy_orders = [
                    [categories[0], categories[2], categories[1]],  # numbers->shapes->letters in default order
                    [categories[2], categories[1], categories[0]],  # shapes->letters->numbers
                    [categories[1], categories[0], categories[2]],  # letters->numbers->shapes
                ]
                start_asc = plan_rng.choice([True, False])
                trial_idx = 1
                for order in legacy_orders:
                    direction_pair = ('ascending', 'descending') if start_asc else ('descending', 'ascending')
                    for direction in direction_pair:
                        label = direction.capitalize()
                        trials.append((
                            f'Experimental_{label}_{trial_idx:02d}', order[:], direction,
                            f'Experimental Trial — {label} {trial_idx:02d}\nCategory order: {" → ".join(order)}\n\nPress any key to start.'
                        ))
                        trial_idx += 1
            else:
                # Default/new mode: all unique category permutations,
                # each run once ascending and once descending.
                all_orders = [list(order) for order in permutations(categories)]
                plan_rng.shuffle(all_orders)
                trial_idx = 1
                for order in all_orders:
                    for direction in ('ascending', 'descending'):
                        label = direction.capitalize()
                        trials.append((
                            f'Experimental_{label}_{trial_idx:02d}', order, direction,
                            f'Experimental Trial — {label} {trial_idx:02d}\nCategory order: {" → ".join(order)}\n\nPress any key to start.'
                        ))
                        trial_idx += 1
        else:
            # Single category — just asc/desc
            for i, direction in enumerate(['ascending','descending','ascending']):
                trials.append((
                    f'Experimental_{direction.capitalize()}_{i+1}', categories, direction,
                    f'Experimental Trial {i+1} — {direction.capitalize()}\n\nPress any key to start.'
                ))

        # ── Run trials ──────────────────────────────────────────────────────
        task_quit_early = False
        for trial_idx, (trial_name, cats, seq_type, instructions) in enumerate(trials, start=1):
            block_seed = derive_seed(task_seed, 'TRIAL', trial_name, str(trial_idx))
            writer.log_session_event(f"SEED task=TMT block={trial_name} seed={block_seed}")
            random.seed(block_seed)
            np.random.seed(block_seed % (2**32 - 1))
            cat_order = cats if len(cats) > 1 else None
            sequence  = create_sequence(cats, seq_type, n=n_elem)
            is_mixed  = cat_order and ('Experimental' in trial_name or 'Mixed' in trial_name)
            trial_result = run_trial(win, trial_name, sequence, instructions,
                           pid, treatment, writer,
                           timing_monitor=timing,
                           abort_flag_path=abort_flag_path,
                           seq_type=seq_type if is_mixed else None,
                           cat_order=cat_order if is_mixed else None)
            if trial_result['status'] == 'completed':
                if trial_name.startswith('Experimental_'):
                    exp_trial_count += 1
                    exp_completion_s += float(trial_result.get('completion_time_s', 0.0))
                    exp_total_errors += int(trial_result.get('total_errors', 0))
                    exp_corrected_error_burden += int(trial_result.get('corrected_error_burden', 0))
                    exp_click_rts.extend(trial_result.get('click_rts_ms', []))
                    exp_near_miss_total += int(trial_result.get('near_miss_total', 0))
                    exp_repeated_same_wrong_total += int(trial_result.get('repeated_same_wrong_total', 0))
                    exp_correction_latency_means.append(float(trial_result.get('correction_latency_mean_ms', 0.0)))
                continue
            if trial_result['status'] == 'quit_battery':
                return
            if trial_result['status'] == 'quit_task':
                task_quit_early = True
                break

        # Final message
        end_text = (
            'Trail Making Test Ended Early.\n\nData has been saved.\n\nPress any key to exit.'
            if task_quit_early
            else 'Trail Making Test Complete!\n\nThank you.\n\nPress any key to exit.'
        )
        run_summary = timing.run_summary()
        completion_status = 'ABORTED' if task_quit_early else 'COMPLETED'
        interclick_var = statistics.pstdev(exp_click_rts) if len(exp_click_rts) > 1 else 0.0
        correction_latency_mean = (
            statistics.mean(exp_correction_latency_means) if exp_correction_latency_means else 0.0
        )
        writer.write_row({
            'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ID': pid,
            'Treatment': treatment,
            'Trial_Name': '__RUN_SUMMARY__',
            'Connection': '',
            'Reaction_Time_ms': '',
            'Total_Time_ms': '',
            'Wrong_Guesses_Before_Correct': '',
            **timing_row_fields({
                'dropped_frames': '',
                'max_interval_ms': '',
                'exceeded_threshold': '',
                'threshold_ms': '',
                'expected_frame_ms': '',
            }, run_fields_blank=False),
            **timing_run_fields(run_summary),
        })
        write_derived_metrics(
            excel_path=config['excel_path'],
            task='TMT',
            participant_id=pid,
            treatment=treatment,
            metrics={
                'Completion_Status': completion_status,
                'TMT_Experimental_Trials_Completed': exp_trial_count,
                'TMT_Completion_Time_s': round(exp_completion_s, 3),
                'TMT_Total_Errors': exp_total_errors,
                'TMT_Corrected_Error_Burden': exp_corrected_error_burden,
                'TMT_InterClick_RT_Variability_ms': round(interclick_var, 3),
                'TMT_Click_Count': len(exp_click_rts),
                'TMT_Near_Miss_Total': exp_near_miss_total,
                'TMT_Repeated_Same_Wrong_Target_Total': exp_repeated_same_wrong_total,
                'TMT_Correction_Latency_Mean_ms': round(correction_latency_mean, 3),
            },
        )
        visual.TextStim(win,
            text=f"{end_text}\n\nTiming Quality Score: {run_summary['run_quality_score']:.2f}",
            height=th, wrapWidth=ww).draw()
        win.flip(); event.waitKeys()

    finally:
        try:
            writer.log_session_event('TMT ended (session closed)')
        except Exception:
            pass
        win.close()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _standalone_config():
    info = {'Participant ID': '', 'Treatment': ''}
    dlg = gui.DlgFromDict(info, title='TMT — Standalone')
    if not dlg.OK:
        core.quit()
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data')
    return {
        'participant_id': info['Participant ID'],
        'treatment': info['Treatment'],
        'screen_width': 1920, 'screen_height': 1080, 'fullscreen': True,
        'tmt_elements_per_category': 6,
        'tmt_use_numbers': True, 'tmt_use_letters': True, 'tmt_use_shapes': True,
        'tmt_run_familiarization': True,
        'tmt_use_legacy_mixed_order': False,
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
        run_tmt(config, writer)
    finally:
        writer.close()
