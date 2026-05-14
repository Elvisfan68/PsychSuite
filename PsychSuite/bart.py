"""
bart.py — Modernized Balloon Analogue Risk Task (BART)
Accepts a config dict from the launcher OR runs standalone.
Writes each trial row to Excel immediately after balloon resolves (crash-safe).
"""
import sys, os, json, random
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_writer import IncrementalExcelWriter, make_excel_path
from pause_menu import show_pause_menu, request_suite_abort
from timing_quality import FrameTimingMonitor, timing_row_fields, timing_run_fields
from randomization import derive_seed
from metrics_writer import write_derived_metrics
from display_compat import macos_window_compat_kwargs

from psychopy import visual, event, core, gui

SHEET_NAME = 'BART'
SOUND_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Sound Effects')


class BART:
    def __init__(self, config: dict, writer: IncrementalExcelWriter):
        self.config  = config
        self.writer  = writer
        self.pid     = config.get('participant_id', 'unknown')
        self.tx      = config.get('treatment', '')
        self.abort_flag_path = config.get('abort_flag_path')
        self.master_seed = int(config.get('master_seed', random.SystemRandom().randint(1, 2**31 - 2)))
        self.replay_exact = bool(config.get('replay_exact_sequence', False))
        self.task_seed = derive_seed(self.master_seed, 'BART')
        self.rng = random.Random(self.task_seed)

        # Parameters from config
        self.total_trials      = int(config.get('bart_total_trials', 30))
        self.array_size        = int(config.get('bart_array_size', 128))
        self.points_per_pump   = float(config.get('bart_points_per_pump', 0.01))
        self.pump_interval     = float(config.get('bart_pump_interval', 0.1))
        self.target_avg        = int(config.get('bart_target_avg_break', 64))
        self.topoff_enabled    = bool(config.get('bart_topoff_enabled', True))
        self.num_topoff_trials = int(config.get('bart_num_topoff_trials', 15))

        screen_w = int(config.get('screen_width', 1920))
        screen_h = int(config.get('screen_height', 1080))
        fullscr  = bool(config.get('fullscreen', True))
        self.cfg_screen_w = screen_w
        self.cfg_screen_h = screen_h

        # Optional pygame sounds (pygame is not a hard dependency — see requirements.txt).
        self.pump_snd = self.pop_snd = self.collect_snd = None
        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
            self.pump_snd    = pygame.mixer.Sound(os.path.join(SOUND_DIR, 'pump.mp3'))
            self.pop_snd     = pygame.mixer.Sound(os.path.join(SOUND_DIR, 'pop.mp3'))
            self.collect_snd = pygame.mixer.Sound(os.path.join(SOUND_DIR, 'collect.mp3'))
        except ImportError:
            print(
                "pygame not installed — BART runs without sound. "
                "For sound effects use Python 3.10–3.12 and: pip install pygame"
            )
        except Exception as e:
            print(f"Sound warning: {e}")

        self.win = visual.Window(
            size=[screen_w, screen_h], fullscr=fullscr, screen=0,
            winType='pyglet', allowGUI=False, monitor='testMonitor',
            color=[-1,-1,-1], colorSpace='rgb', units='pix',
            **macos_window_compat_kwargs()
        )
        self.win.mouseVisible = True
        self._calc_scaling()
        self.timing = FrameTimingMonitor(self.win)
        self.writer.log_session_event(
            f"SEED task=BART replay={self.replay_exact} master={self.master_seed} task={self.task_seed}"
        )
        self.writer.log_session_event(
            f"DISPLAY task=BART requested={screen_w}x{screen_h} fullscr={fullscr} actual={self.win.size[0]}x{self.win.size[1]} useRetina={getattr(self.win, 'useRetina', 'na')}"
        )

        # Generate break points and top-off assignment
        self.break_points = self._gen_break_points()
        self.trial_seq    = [{'trial': i+1, 'explosion_point': self.break_points[i]}
                             for i in range(self.total_trials)]
        self._assign_topoff()

        # Runtime state
        self.current_trial       = 0
        self.total_earned        = 0.0
        self.last_balloon_earned = 0.0
        self.trial_data          = []
        self._trial_timing_acc   = None
        self.in_competency_gate  = False
        self.practice_min_pumps  = int(config.get('bart_practice_min_pumps', 1))

        self._setup_display()

    # ── Scaling ──────────────────────────────────────────────────────────────

    def _calc_scaling(self):
        # Use configured resolution for scaling to avoid macOS HiDPI fullscreen oversizing.
        sw, sh = self.cfg_screen_w, self.cfg_screen_h
        sf = min(sw / 1920.0, sh / 1080.0) * 1.5
        self.ts = {k: int(v * sf) for k, v in
                   {'large':35,'medium':28,'normal':22,'small':18,'button':24,'huge':50}.items()}
        self.sf = sf

    # ── Break-point generation ────────────────────────────────────────────────

    def _gen_break_points(self):
        n_blocks   = max(1, self.total_trials // 10)
        per_block  = self.total_trials // n_blocks
        remainder  = self.total_trials % n_blocks
        out = []
        for b in range(n_blocks):
            count = per_block + (1 if b < remainder else 0)
            block_seed = derive_seed(self.task_seed, 'BREAKPOINT_BLOCK', str(b))
            self.writer.log_session_event(f"SEED task=BART block=BREAKPOINT_BLOCK_{b+1} seed={block_seed}")
            block_rng = random.Random(block_seed)
            block_np = np.random.default_rng(block_seed)
            out.extend(self._block_seq(self.array_size, self.target_avg, count, block_rng, block_np))
        return out

    def _block_seq(self, arr, avg, n, block_rng, block_np):
        mu, sigma = avg, arr / 6
        seq = [int(round(max(1, min(arr, x)))) for x in block_np.normal(mu, sigma, n)]
        diff = int(round(avg * n - sum(seq)))
        idxs = list(range(n)); block_rng.shuffle(idxs)
        for i in idxs:
            if diff == 0: break
            if diff > 0 and seq[i] < arr:  seq[i] += 1; diff -= 1
            elif diff < 0 and seq[i] > 1:  seq[i] -= 1; diff += 1
        return [max(1, min(arr, x)) for x in seq]

    def _assign_topoff(self):
        n = self.num_topoff_trials
        topoff_seed = derive_seed(self.task_seed, 'TOPOFF_ASSIGN')
        self.writer.log_session_event(f"SEED task=BART block=TOPOFF_ASSIGN seed={topoff_seed}")
        topoff_rng = random.Random(topoff_seed)
        bps = [t['explosion_point'] for t in self.trial_seq]
        top3 = sorted(range(len(bps)), key=lambda i: bps[i], reverse=True)[:3]
        rest = [i for i in range(len(bps)) if i not in top3]
        extra = topoff_rng.sample(rest, min(n-3, len(rest)))
        topoff_set = set(top3) | set(extra)
        self.topoff_assign = [i in topoff_set for i in range(self.total_trials)]

    # ── Display setup ─────────────────────────────────────────────────────────

    def _setup_display(self):
        sw, sh = self.win.size
        sf = self.sf

        bw, bh = int(200*sf), int(70*sf)
        cw      = int(240*sf)
        btn_y   = -sh//3
        sl_y    = btn_y + int(200*sf)
        sl_w    = int(400*sf)
        sl_h    = int(20*sf)
        ball_y  = int(150*sf)

        # Balloon + preview
        self.balloon = visual.Circle(self.win, radius=50, pos=[0, ball_y],
                                     fillColor=[-1,1,-1], lineColor=[-1,.4,-1], lineWidth=2)
        self.balloon_preview = visual.Circle(self.win, radius=50, pos=[0, ball_y],
                                             fillColor=None, lineColor=[-1,1,-1], lineWidth=2, opacity=.5)

        # Slider
        self.sl_y = sl_y; self.sl_w = sl_w
        self.sl_left = -sl_w//2; self.sl_right = sl_w//2
        self.slider_track  = visual.Rect(self.win, width=sl_w, height=sl_h, pos=[0,sl_y],
                                         fillColor='lightgray', lineColor='black', lineWidth=2)
        self.slider_handle = visual.Circle(self.win, radius=int(15*sf), pos=[self.sl_left,sl_y],
                                           fillColor='red', lineColor='darkred', lineWidth=3)
        self.pump_count_txt = visual.TextStim(self.win, text='Pumps: 1',
                                              pos=[0, sl_y-int(50*sf)],
                                              color='white', height=self.ts['medium'], bold=True)

        # Buttons
        px, cx = -sw//3, sw//3
        self.pump_btn  = visual.Rect(self.win, width=bw, height=bh, pos=[px,btn_y],
                                     fillColor='red', lineColor='darkred', lineWidth=4)
        self.pump_txt  = visual.TextStim(self.win, text='PUMP', pos=[px,btn_y],
                                         color='white', height=self.ts['button'], bold=True)
        self.coll_btn  = visual.Rect(self.win, width=cw, height=bh, pos=[cx,btn_y],
                                     fillColor='green', lineColor='darkgreen', lineWidth=4)
        self.coll_txt  = visual.TextStim(self.win, text='Collect $$$', pos=[cx,btn_y],
                                         color='white', height=self.ts['button'], bold=True)
        self.pump_info  = {'x':px,'y':btn_y,'w':bw,'h':bh}
        self.coll_info  = {'x':cx,'y':btn_y,'w':cw,'h':bh}

        # Status bar
        sy = sh//3
        self.total_txt  = visual.TextStim(self.win, text='Total: $0.00',
                                          pos=[-sw//3,sy], color='white',
                                          height=self.ts['medium'], bold=True)
        self.last_txt   = visual.TextStim(self.win, text='Last: $0.00',
                                          pos=[sw//3,sy], color='white',
                                          height=self.ts['medium'], bold=True)
        self.trial_txt  = visual.TextStim(self.win, text='Balloon 1',
                                          pos=[0,sy], color='white',
                                          height=self.ts['medium'], bold=True)
        instr_y = max(btn_y - int(100*sf), -sh//2 + int(50*sf))
        self.instr_txt  = visual.TextStim(self.win, text='', pos=[0,instr_y],
                                          color='white', height=self.ts['small'],
                                          wrapWidth=sw*.8, alignText='center')

        # Per-trial state
        self.selected_pumps    = 1
        self.slider_dragging   = False
        self.is_pumping        = False
        self.in_topoff         = False
        self.has_topped_off    = False
        self.current_pumps     = 0
        self.current_bal_size  = 50
        self.temp_bank         = 0.0
        self.balloon_exploded  = False
        self.pump_sessions     = []
        self.session_number    = 0
        self.pumps_to_sim      = 0
        self.pumps_simmed      = 0
        self.pump_timer        = 0
        self.initial_sel       = 0
        self.topoff_sel        = 0
        self.intended_total    = 0
        self.is_topoff_session = False
        self.trial_ready_ts    = 0.0
        self.first_pump_click_ts = None
        self.last_pump_session_end_ts = None
        self.collect_click_ts  = None
        self.topoff_offer_ts   = None
        self.topoff_decision_ts = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _play(self, snd):
        try:
            if snd: snd.stop(); snd.play()
        except: pass

    def _balloon_color(self, pumps):
        r = min(pumps / 100, 1.0)
        if r <= .5:
            lr = r*2; return [lr*2-1, 1.0, -1.0]
        else:
            lr = (r-.5)*2; return [1.0, (1-lr)*2-1, -1.0]

    def _predicted_size(self):
        base = self.current_pumps if self.in_topoff else 0
        return 50 + (base + self.selected_pumps) * 8

    def _update_slider_pos(self):
        max_p = 9 if self.in_topoff else self.array_size
        ratio = (self.selected_pumps - 1) / (max_p - 1) if max_p > 1 else 0
        self.slider_handle.pos = [self.sl_left + ratio * self.sl_w, self.sl_y]

    def _update_displays(self):
        self.total_txt.text = f'Total Earned: ${self.total_earned:.2f}'
        if self.current_trial > 0:
            expl = getattr(self, 'last_exploded', False)
            pumps = getattr(self, 'last_pumps', 0)
            if expl:
                ep = self.trial_seq[self.current_trial-1]['explosion_point']
                self.last_txt.text = f'Last: $0.00 (POPPED)\nPumped: {pumps} | Popped at: {ep}'
            else:
                self.last_txt.text = f'Last: ${self.last_balloon_earned:.2f}\nPumped: {pumps}'
        self.trial_txt.text = f'Balloon {self.current_trial+1} of {self.total_trials}'
        self.pump_count_txt.text = f'Pumps: {self.selected_pumps}'

        if not self.is_pumping:
            ps = self._predicted_size()
            self.balloon_preview.radius = ps
            pred_p = (self.current_pumps + self.selected_pumps) if self.in_topoff else self.selected_pumps
            self.balloon_preview.lineColor = self._balloon_color(pred_p)

        if self.current_pumps > 0:
            self.balloon.fillColor = self._balloon_color(self.current_pumps)
            self.balloon.lineColor = [c*.7 for c in self._balloon_color(self.current_pumps)]

        if self.is_pumping:
            self.instr_txt.text = f'Pumping: {self.pumps_simmed}/{self.pumps_to_sim}\nTotal: {self.current_pumps}\nBank: ${self.temp_bank:.2f}'
        elif self.in_topoff:
            self.instr_txt.text = f'TOP-OFF: Add 1-9 more pumps?\nTotal: {self.current_pumps} | Bank: ${self.temp_bank:.2f}'
        elif self.current_pumps > 0:
            self.instr_txt.text = f'Total: {self.current_pumps} | Bank: ${self.temp_bank:.2f}\nCOLLECT to finish'
        else:
            self.instr_txt.text = 'Drag slider to select pumps, then PUMP'

    def _draw(self):
        if not self.balloon_exploded:
            self.balloon_preview.draw()
            self.balloon.draw()
        self.slider_track.draw(); self.slider_handle.draw(); self.pump_count_txt.draw()
        self.pump_btn.draw(); self.pump_txt.draw()
        self.coll_btn.draw(); self.coll_txt.draw()
        self.total_txt.draw(); self.last_txt.draw()
        self.trial_txt.draw(); self.instr_txt.draw()

    # ── Slider interaction ────────────────────────────────────────────────────

    def _handle_slider(self, mpos, mpressed):
        if self.is_pumping: return
        mx, my = mpos
        hh = 60
        if (self.sl_left-20 <= mx <= self.sl_right+20 and
                self.sl_y-hh//2 <= my <= self.sl_y+hh//2):
            if mpressed and not self.slider_dragging:
                self.slider_dragging = True
            if self.slider_dragging:
                rel = max(0, min(self.sl_w, mx - self.sl_left))
                ratio = rel / self.sl_w
                max_p = 9 if self.in_topoff else self.array_size
                new_p = max(1, min(max_p, int(1 + ratio*(max_p-1) + .5)))
                if new_p != self.selected_pumps:
                    self.selected_pumps = new_p
                    self._update_slider_pos()
                    self.balloon_preview.radius = self._predicted_size()
                    pred_p = (self.current_pumps + new_p) if self.in_topoff else new_p
                    self.balloon_preview.lineColor = self._balloon_color(pred_p)
                    self.pump_count_txt.text = f'Pumps: {new_p}'
        if not mpressed:
            self.slider_dragging = False

    # ── Pumping simulation ────────────────────────────────────────────────────

    def _start_pump(self):
        if self.is_pumping: return
        if self.session_number == 0:
            self.initial_sel = self.selected_pumps
            self.intended_total = self.selected_pumps
            self.is_topoff_session = False
        elif self.in_topoff:
            self.topoff_sel = self.selected_pumps
            self.intended_total = self.initial_sel + self.selected_pumps
            self.is_topoff_session = True
        self.is_pumping   = True
        self.pumps_to_sim = self.selected_pumps
        self.pumps_simmed = 0
        self.pump_timer   = core.getTime()

    def _update_pump(self):
        if not self.is_pumping: return
        if core.getTime() - self.pump_timer < self.pump_interval: return

        self.pumps_simmed   += 1
        self.current_pumps  += 1
        exp = self.trial_seq[self.current_trial]['explosion_point']

        if self.current_pumps >= exp:
            self.temp_bank       += self.points_per_pump
            self.current_bal_size += 8
            self.balloon.radius   = self.current_bal_size
            self._explode()
            return

        self._play(self.pump_snd)
        self.current_bal_size += 8
        self.balloon.radius    = self.current_bal_size
        self.temp_bank        += self.points_per_pump
        self._update_displays()
        self.pump_timer = core.getTime()

        if self.pumps_simmed >= self.pumps_to_sim:
            self.is_pumping = False
            self.last_pump_session_end_ts = core.getTime()
            self._record_session()
            if self.is_topoff_session:
                core.wait(.5); self._collect(after_topoff=True)
            elif self.session_number == 1 and not self.has_topped_off:
                if self.topoff_enabled and self.topoff_assign[self.current_trial]:
                    self._show_topoff()
                else:
                    core.wait(.5); self._collect()

    def _record_session(self, exploded_during=False):
        self.session_number += 1
        self.pump_sessions.append({
            'session': self.session_number,
            'intended': self.selected_pumps,
            'actual':   self.pumps_simmed,
            'was_topoff': self.is_topoff_session,
            'exploded': exploded_during,
        })
        if self.is_topoff_session:
            self.has_topped_off = True
            self.in_topoff = False

    def _show_topoff(self):
        self.topoff_offer_ts = core.getTime()
        self.in_topoff      = True
        self.selected_pumps = 1
        self._update_slider_pos()
        self._update_displays()

    def _timing_reset_trial_acc(self):
        self._trial_timing_acc = {
            'frame_count': 0,
            'dropped_frames': 0,
            'max_interval_ms': 0.0,
            'threshold_ms': 0.0,
            'expected_frame_ms': 0.0,
            'exceeded_threshold': False,
        }

    def _timing_merge(self, m):
        if self._trial_timing_acc is None:
            self._timing_reset_trial_acc()
        self._trial_timing_acc['frame_count'] += m['frame_count']
        self._trial_timing_acc['dropped_frames'] += m['dropped_frames']
        self._trial_timing_acc['max_interval_ms'] = max(
            self._trial_timing_acc['max_interval_ms'], m['max_interval_ms']
        )
        self._trial_timing_acc['threshold_ms'] = m['threshold_ms']
        self._trial_timing_acc['expected_frame_ms'] = m['expected_frame_ms']
        self._trial_timing_acc['exceeded_threshold'] = (
            self._trial_timing_acc['exceeded_threshold'] or m['exceeded_threshold']
        )

    def _timing_pause_segment(self):
        self._timing_merge(self.timing.end_segment())

    def _timing_resume_segment(self):
        self.timing.start_segment()

    def _timing_finalize_trial(self):
        self._timing_pause_segment()
        out = self._trial_timing_acc or {
            'dropped_frames': 0,
            'max_interval_ms': 0.0,
            'exceeded_threshold': False,
            'threshold_ms': 0.0,
            'expected_frame_ms': 0.0,
        }
        self._trial_timing_acc = None
        return out

    # ── Money collection ──────────────────────────────────────────────────────

    def _collect(self, after_topoff=False):
        if self.temp_bank <= 0 or self.is_pumping: return
        self.in_topoff = False
        self.last_pumps    = self.intended_total
        self.last_exploded = False
        self._play(self.collect_snd)
        self._animate_collect()
        self.last_balloon_earned  = self.temp_bank
        self.total_earned        += self.temp_bank
        self._record_trial(exploded=False, timing_metrics=self._timing_finalize_trial())
        self.temp_bank = 0.0
        self.current_trial += 1
        self._new_balloon()

    def _animate_collect(self):
        orig = self.total_earned
        for i in range(21):
            self.total_txt.text = f'Total Earned: ${orig + self.temp_bank*i/20:.2f}'
            self.balloon.draw(); self.balloon_preview.draw()
            self._draw(); self.win.flip(); core.wait(.05)

    def _explode(self):
        self.balloon_exploded = True
        self.is_pumping = False
        self._play(self.pop_snd)
        self._record_session(exploded_during=True)
        self.last_pumps    = self.intended_total
        self.last_exploded = True
        self.last_balloon_earned = 0.0
        # Flash effect
        exp_circle = visual.Circle(self.win, radius=self.current_bal_size*1.5,
                                   pos=self.balloon.pos, fillColor='red', lineColor='darkred')
        pop_txt    = visual.TextStim(self.win, text='POP!', pos=self.balloon.pos,
                                     color='white', height=self.ts['huge'])
        for _ in range(3):
            exp_circle.draw(); pop_txt.draw(); self._draw(); self.win.flip(); core.wait(.1)
            self._draw(); self.win.flip(); core.wait(.1)
        self._record_trial(exploded=True, timing_metrics=self._timing_finalize_trial())
        self.temp_bank = 0.0
        self.current_trial += 1
        core.wait(1.0); self._new_balloon()

    # ── Trial recording ───────────────────────────────────────────────────────

    def _record_trial(self, exploded, timing_metrics=None):
        if self.in_competency_gate:
            return
        initial_pump = 0; top_off = 0
        for s in self.pump_sessions:
            if s['was_topoff']: top_off      = s['intended']
            else:               initial_pump = s['intended']
        topoff_option = self.topoff_assign[self.current_trial] if self.current_trial < len(self.topoff_assign) else False
        hesitation_before_pump_ms = (
            (self.first_pump_click_ts - self.trial_ready_ts) * 1000.0
            if self.first_pump_click_ts is not None else ''
        )
        hesitation_before_collect_ms = (
            (self.collect_click_ts - self.last_pump_session_end_ts) * 1000.0
            if (self.collect_click_ts is not None and self.last_pump_session_end_ts is not None) else ''
        )
        topoff_decision_latency_ms = (
            (self.topoff_decision_ts - self.topoff_offer_ts) * 1000.0
            if (self.topoff_offer_ts is not None and self.topoff_decision_ts is not None) else ''
        )

        row = {
            'Timestamp':           datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ID':                  self.pid,
            'Treatment':           self.tx,
            'Trial':               self.current_trial + 1,
            'Explosion_Point':     self.trial_seq[self.current_trial]['explosion_point'],
            'Initial_Pump':        initial_pump,
            'Top_Off':             top_off,
            'Topoff_Option':       topoff_option,
            'Exploded':            exploded,
            'Earned_This_Balloon': 0.0 if exploded else self.temp_bank,
            'Total_Earned':        self.total_earned,
            'Selected_Pumps_Initial': initial_pump,
            'Selected_Pumps_Topoff': top_off,
            'Hesitation_Before_Pump_ms': round(hesitation_before_pump_ms, 2) if hesitation_before_pump_ms != '' else '',
            'Hesitation_Before_Collect_ms': round(hesitation_before_collect_ms, 2) if hesitation_before_collect_ms != '' else '',
            'Topoff_Decision_Latency_ms': round(topoff_decision_latency_ms, 2) if topoff_decision_latency_ms != '' else '',
        }
        row.update(timing_row_fields(timing_metrics or {
            'dropped_frames': 0,
            'max_interval_ms': 0.0,
            'exceeded_threshold': False,
            'threshold_ms': 0.0,
            'expected_frame_ms': 0.0,
        }))
        self.writer.write_row(row)
        total_pumps = int(initial_pump) + int(top_off)
        self.trial_data.append({
            'exploded': bool(exploded),
            'initial_pump': int(initial_pump),
            'top_off': int(top_off),
            'total_pumps': total_pumps,
            'topoff_option': bool(topoff_option),
            'used_topoff': bool(top_off > 0),
            'hesitation_before_pump_ms': float(hesitation_before_pump_ms) if hesitation_before_pump_ms != '' else None,
            'hesitation_before_collect_ms': float(hesitation_before_collect_ms) if hesitation_before_collect_ms != '' else None,
            'topoff_decision_latency_ms': float(topoff_decision_latency_ms) if topoff_decision_latency_ms != '' else None,
        })

    # ── New balloon ───────────────────────────────────────────────────────────

    def _new_balloon(self):
        if self.current_trial >= self.total_trials:
            self._end(); return
        self.current_pumps    = 0; self.current_bal_size = 50
        self.temp_bank        = 0.0; self.balloon_exploded = False
        self.is_pumping       = False; self.in_topoff = False
        self.has_topped_off   = False; self.pump_sessions = []
        self.session_number   = 0; self.initial_sel = 0
        self.topoff_sel       = 0; self.intended_total = 0
        self.is_topoff_session = False
        self.trial_ready_ts = core.getTime()
        self.first_pump_click_ts = None
        self.last_pump_session_end_ts = None
        self.collect_click_ts = None
        self.topoff_offer_ts = None
        self.topoff_decision_ts = None
        self.balloon.fillColor = [-1,1,-1]; self.balloon.lineColor = [-1,.4,-1]
        self.balloon.radius    = 50
        self.balloon_preview.lineColor = [-1,1,-1]
        self.selected_pumps   = 1; self._update_slider_pos()
        self._update_displays()
        self._timing_reset_trial_acc()
        self._timing_resume_segment()

    # ── Click handler ─────────────────────────────────────────────────────────

    def _handle_click(self, pos):
        if self.is_pumping: return
        now_ts = core.getTime()
        mx, my = pos
        p = self.pump_info
        if (p['x']-p['w']//2 < mx < p['x']+p['w']//2 and
                p['y']-p['h']//2 < my < p['y']+p['h']//2):
            if self.session_number == 0 and self.first_pump_click_ts is None:
                self.first_pump_click_ts = now_ts
            if self.in_topoff and self.topoff_decision_ts is None:
                self.topoff_decision_ts = now_ts
            self._start_pump(); return
        c = self.coll_info
        if (c['x']-c['w']//2 < mx < c['x']+c['w']//2 and
                c['y']-c['h']//2 < my < c['y']+c['h']//2):
            self.collect_click_ts = now_ts
            if self.in_topoff and self.topoff_decision_ts is None:
                self.topoff_decision_ts = now_ts
            self._collect()

    # ── Instructions ─────────────────────────────────────────────────────────

    def _show_instructions(self):
        pages = [
            "Balloon Analogue Risk Task (BART)\n\nPump up balloons to earn money.\nEach pump earns you 1 cent.\n\nPress SPACE to continue...",
            "The money goes into a temporary bank.\nCollect it any time before the balloon pops!\n\nIf the balloon pops, you lose everything for that balloon.\n\nPress SPACE to continue...",
            f"CONTROLS:\n• Drag the slider to choose how many pumps (1–{self.array_size})\n• Click PUMP to inflate\n• Click 'Collect $$$' to bank your money\n• On some balloons, you may get a TOP-OFF option (1–9 extra pumps)\n\n{self.total_trials} balloons total.\n\nPress SPACE to begin...",
        ]
        disp = visual.TextStim(self.win, text='', pos=[0,0], color='white',
                               height=self.ts['large'], wrapWidth=1400)
        for page in pages:
            disp.text = page; disp.draw(); self.win.flip()
            k = event.waitKeys(keyList=['space','escape'])
            if k and 'escape' in k:
                action, _ = self._pause_menu()
                if action == 'resume':
                    continue
                self._end_early(action)
                return False
        return True

    def _run_competency_gate(self):
        """
        Mandatory short competency gate:
        participant must demonstrate at least one pump and then collect.
        """
        while True:
            txt = visual.TextStim(
                self.win,
                text=(
                    "Mandatory BART Practice\n\n"
                    "Practice goal:\n"
                    "1) Pump at least once\n"
                    "2) Click Collect $$$ to bank money\n\n"
                    "Take as much time as you need on this practice part.\n\n"
                    "Press SPACE to begin practice."
                ),
                pos=[0, 0],
                color='white',
                height=self.ts['large'],
                wrapWidth=1400,
            )
            txt.draw(); self.win.flip()
            keys = event.waitKeys(keyList=['space', 'escape'])
            if 'escape' in keys:
                action, _ = self._pause_menu()
                if action == 'resume':
                    continue
                self._end_early(action)
                return False

            self.in_competency_gate = True
            self.topoff_enabled = False
            self.total_earned = 0.0
            self.last_balloon_earned = 0.0
            self.current_trial = 0
            self._new_balloon()

            mouse = event.Mouse(win=self.win)
            mouse_was_pressed = False
            passed = False
            failed = False

            while True:
                keys = event.getKeys(keyList=['escape'])
                if keys:
                    action, pause_s = self._pause_menu()
                    if action == 'resume':
                        if self.is_pumping:
                            self.pump_timer += pause_s
                        if self._trial_timing_acc is not None:
                            self._timing_resume_segment()
                        continue
                    self._end_early(action)
                    return False

                mpos = mouse.getPos()
                mpressed = mouse.getPressed()[0]
                self._handle_slider(mpos, mpressed)
                if mpressed and not mouse_was_pressed:
                    self._handle_click(mpos)
                mouse_was_pressed = mpressed

                self._update_pump()
                self._update_displays()
                self._draw(); self.win.flip()
                core.wait(0.01)

                # Pass: participant banked money with enough pumps.
                if self.current_trial >= 1 and not self.last_exploded and self.last_pumps >= self.practice_min_pumps:
                    passed = True
                    break
                # Fail attempt: first balloon popped.
                if self.current_trial >= 1 and self.last_exploded:
                    failed = True
                    break

            self.in_competency_gate = False
            self.topoff_enabled = bool(self.config.get('bart_topoff_enabled', True))
            self.total_earned = 0.0
            self.last_balloon_earned = 0.0
            self.current_trial = 0
            self._new_balloon()

            if passed:
                ok = visual.TextStim(
                    self.win,
                    text="Practice passed.\n\nYou are ready for the real task.\n\nPress SPACE to continue.",
                    pos=[0, 0], color='white', height=self.ts['large'], wrapWidth=1400
                )
                ok.draw(); self.win.flip()
                event.waitKeys(keyList=['space'])
                return True

            if failed:
                retry = visual.TextStim(
                    self.win,
                    text=(
                        "Practice attempt ended before collect.\n\n"
                        "Please try again.\n"
                        "Take as much time as you need on this practice part.\n\n"
                        "Press SPACE to retry."
                    ),
                    pos=[0, 0], color='white', height=self.ts['large'], wrapWidth=1400
                )
                retry.draw(); self.win.flip()
                keys = event.waitKeys(keyList=['space', 'escape'])
                if 'escape' in keys:
                    action, _ = self._pause_menu()
                    if action == 'resume':
                        continue
                    self._end_early(action)
                    return False

    def _pause_menu(self):
        if self._trial_timing_acc is not None:
            self._timing_pause_segment()
        action, pause_s = show_pause_menu(
            self.win, title='BART', scale_factor=self.sf, return_pause_seconds=True
        )
        if action == 'quit_battery':
            request_suite_abort(self.abort_flag_path)
        return action, pause_s

    def _end_early(self, action='quit_task'):
        self._write_derived_metrics(completion_status='ABORTED')
        mode = 'Battery stopped by experimenter.' if action == 'quit_battery' else 'Task ended by experimenter.'
        disp = visual.TextStim(
            self.win,
            text=(
                "BART Ended Early\n\n"
                f"{mode}\n\n"
                "Data has been saved.\n\nPress SPACE to exit."
            ),
            pos=[0, 0],
            color='white',
            height=self.ts['large'],
            wrapWidth=1400,
        )
        disp.draw()
        self.win.flip()
        event.waitKeys(keyList=['space'])
        self._quit()

    def _write_derived_metrics(self, completion_status='COMPLETED'):
        completed = len(self.trial_data)
        unexploded = [t for t in self.trial_data if not t['exploded']]
        adjusted_pumps = (
            sum(t['total_pumps'] for t in unexploded) / len(unexploded)
            if unexploded else 0.0
        )
        explosions = sum(1 for t in self.trial_data if t['exploded'])
        explosion_rate = (explosions / completed) if completed > 0 else 0.0
        topoff_offered = sum(1 for t in self.trial_data if t['topoff_option'])
        topoff_used = sum(1 for t in self.trial_data if t['used_topoff'])
        topoff_usage_rate = (topoff_used / topoff_offered) if topoff_offered > 0 else 0.0
        pump_hesitations = [t['hesitation_before_pump_ms'] for t in self.trial_data if t.get('hesitation_before_pump_ms') is not None]
        collect_hesitations = [t['hesitation_before_collect_ms'] for t in self.trial_data if t.get('hesitation_before_collect_ms') is not None]
        topoff_latencies = [t['topoff_decision_latency_ms'] for t in self.trial_data if t.get('topoff_decision_latency_ms') is not None]
        mean_pump_hesitation = (sum(pump_hesitations) / len(pump_hesitations)) if pump_hesitations else 0.0
        mean_collect_hesitation = (sum(collect_hesitations) / len(collect_hesitations)) if collect_hesitations else 0.0
        mean_topoff_latency = (sum(topoff_latencies) / len(topoff_latencies)) if topoff_latencies else 0.0

        write_derived_metrics(
            excel_path=self.config['excel_path'],
            task='BART',
            participant_id=self.pid,
            treatment=self.tx,
            metrics={
                'Completion_Status': completion_status,
                'BART_Trials_Completed': completed,
                'BART_Adjusted_Pumps_Mean': round(adjusted_pumps, 3),
                'BART_Explosion_Rate': round(explosion_rate, 6),
                'BART_Topoff_Offered_Count': topoff_offered,
                'BART_Topoff_Used_Count': topoff_used,
                'BART_Topoff_Usage_Rate_When_Offered': round(topoff_usage_rate, 6),
                'BART_Hesitation_Before_Pump_Mean_ms': round(mean_pump_hesitation, 3),
                'BART_Hesitation_Before_Collect_Mean_ms': round(mean_collect_hesitation, 3),
                'BART_Topoff_Decision_Latency_Mean_ms': round(mean_topoff_latency, 3),
            },
        )

    # ── End / quit ────────────────────────────────────────────────────────────

    def _end(self):
        run_summary = self.timing.run_summary()
        self._write_derived_metrics(completion_status='COMPLETED')
        self.writer.write_row({
            'Timestamp':           datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ID':                  self.pid,
            'Treatment':           self.tx,
            'Trial':               '__RUN_SUMMARY__',
            'Explosion_Point':     '',
            'Initial_Pump':        '',
            'Top_Off':             '',
            'Topoff_Option':       '',
            'Exploded':            '',
            'Earned_This_Balloon': '',
            'Total_Earned':        round(self.total_earned, 2),
            **timing_row_fields({
                'dropped_frames': '',
                'max_interval_ms': '',
                'exceeded_threshold': '',
                'threshold_ms': '',
                'expected_frame_ms': '',
            }, run_fields_blank=False),
            **timing_run_fields(run_summary),
        })
        results = (
            f"Experiment Complete!\n\n"
            f"Total Earned: ${self.total_earned:.2f}\n"
            f"Balloons completed: {self.current_trial}\n\n"
            f"Timing Quality Score: {run_summary['run_quality_score']:.2f}\n\n"
            f"Data saved to Excel.\n\nPress SPACE to exit."
        )
        disp = visual.TextStim(self.win, text=results, pos=[0,0], color='white',
                               height=self.ts['large'], wrapWidth=1400)
        disp.draw(); self.win.flip()
        event.waitKeys(keyList=['space'])
        self.win.close()

    def _quit(self):
        self.win.close()

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(self):
        try:
            if not self._show_instructions():
                return
            if not self._run_competency_gate():
                return
            # Reset run-level timing after practice gate so score reflects scored trials only.
            self.timing = FrameTimingMonitor(self.win)
            self._new_balloon()
            mouse_was_pressed = False
            mouse = event.Mouse(win=self.win)

            while self.current_trial < self.total_trials:
                keys = event.getKeys(keyList=['escape'])
                if keys:
                    action, pause_s = self._pause_menu()
                    if action == 'resume':
                        if self.is_pumping:
                            self.pump_timer += pause_s
                        if self._trial_timing_acc is not None:
                            self._timing_resume_segment()
                        continue
                    self._end_early(action)
                    return

                mpos     = mouse.getPos()
                mpressed = mouse.getPressed()[0]
                self._handle_slider(mpos, mpressed)
                if mpressed and not mouse_was_pressed:
                    self._handle_click(mpos)
                mouse_was_pressed = mpressed

                self._update_pump()
                self._update_displays()
                self._draw(); self.win.flip()
                core.wait(0.01)

        except Exception as e:
            print(f"BART error: {e}")
            self._quit()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_bart(config: dict, writer: IncrementalExcelWriter):
    writer.log_session_event('BART task started')
    try:
        bart = BART(config, writer)
        bart.run()
    finally:
        try:
            writer.log_session_event('BART ended (session closed)')
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

def _standalone_config():
    info = {'Participant ID': '', 'Treatment': ''}
    dlg = gui.DlgFromDict(info, title='BART — Standalone')
    if not dlg.OK: core.quit()
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data')
    return {
        'participant_id': info['Participant ID'], 'treatment': info['Treatment'],
        'screen_width': 1920, 'screen_height': 1080, 'fullscreen': True,
        'bart_total_trials': 30, 'bart_array_size': 128,
        'bart_points_per_pump': 0.01, 'bart_pump_interval': 0.1,
        'bart_target_avg_break': 64, 'bart_topoff_enabled': True,
        'bart_num_topoff_trials': 15,
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
        run_bart(config, writer)
    finally:
        writer.close()
