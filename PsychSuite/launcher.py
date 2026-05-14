"""
launcher.py — Master launcher for PsychSuite
Run this file to start the test suite.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import simpledialog
import json, os, sys, subprocess, tempfile, threading, queue, random
from datetime import datetime
from data_writer import IncrementalExcelWriter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'Data')

SCREEN_PRESETS = {
    '1024 × 768':  (1024, 768),
    '1280 × 800':  (1280, 800),
    '1366 × 768':  (1366, 768),
    '1440 × 900':  (1440, 900),
    '1920 × 1080': (1920, 1080),
    '2560 × 1440': (2560, 1440),
    'Custom':      None,
}

ALL_TESTS = ['BART', 'PVT', 'TMT']

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_excel_path(pid, tx):
    os.makedirs(DATA_DIR, exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    pid_ = (pid or 'unknown').replace(' ', '_')
    tx_  = (tx  or 'no_tx' ).replace(' ', '_')
    return os.path.join(DATA_DIR, f"{pid_}_{tx_}_{ts}.xlsx")


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

class PsychLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PsychTest Suite — Master Launcher')
        self.resizable(True, True)
        self.configure(bg='#1a1a2e')
        self._ui_queue = queue.Queue()
        self._run_poll_scheduled = False
        self._run_was_stopped = False
        self._current_run_context = None
        self._style()
        self._build_ui()
        self.update_idletasks()
        # Center window
        w, h = 900, 780
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f'{w}x{h}+{x}+{y}')

    # ── Styling ───────────────────────────────────────────────────────────────

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        BG, FG, ACC, ENTRY = '#1a1a2e', '#e0e0e0', '#7c3aed', '#2d2d44'
        s.configure('.',            background=BG, foreground=FG, font=('Segoe UI', 10))
        s.configure('TFrame',       background=BG)
        s.configure('TLabel',       background=BG, foreground=FG)
        s.configure('TLabelframe',  background=BG, foreground='#a78bfa', font=('Segoe UI', 10, 'bold'))
        s.configure('TLabelframe.Label', background=BG, foreground='#a78bfa')
        s.configure('TNotebook',    background='#16213e', tabmargins=[2,5,2,0])
        s.configure('TNotebook.Tab', background='#2d2d44', foreground=FG,
                    padding=[12,4], font=('Segoe UI', 10))
        s.map('TNotebook.Tab',
              background=[('selected','#7c3aed')],
              foreground=[('selected','white')])
        s.configure('TCheckbutton', background=BG, foreground=FG)
        s.configure('TCombobox',    fieldbackground='#2d2d44', foreground=FG,
                    selectbackground=ACC)
        s.configure('TEntry',       fieldbackground='#2d2d44', foreground=FG,
                    insertcolor=FG)
        s.configure('TSpinbox',     fieldbackground='#2d2d44', foreground=FG,
                    insertcolor=FG)
        s.configure('Run.TButton',  background=ACC, foreground='white',
                    font=('Segoe UI', 11, 'bold'), padding=[16,8])
        s.map('Run.TButton',
              background=[('active','#5b21b6'),('disabled','#3d3d5c')],
              foreground=[('disabled','#888')])
        s.configure('Solo.TButton', background='#0f4c75', foreground='white',
                    font=('Segoe UI', 10), padding=[10,6])
        s.map('Solo.TButton', background=[('active','#0a3050'),('disabled','#3d3d5c')])

        self.ENTRY_BG = '#2d2d44'

    # ── UI construction ───────────────────────────────────────────────────────

    def _lbl(self, parent, text, **kw):
        return ttk.Label(parent, text=text, **kw)

    def _entry(self, parent, textvariable, width=22):
        e = ttk.Entry(parent, textvariable=textvariable, width=width)
        return e

    def _spin(self, parent, var, from_, to, width=8):
        return ttk.Spinbox(parent, textvariable=var, from_=from_, to=to,
                           width=width, increment=1)

    def _check(self, parent, text, var):
        return ttk.Checkbutton(parent, text=text, variable=var)

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg='#16213e', pady=12)
        hdr.pack(fill='x')
        tk.Label(hdr, text='PsychTest Suite', font=('Segoe UI', 20, 'bold'),
                 bg='#16213e', fg='#a78bfa').pack()
        tk.Label(hdr, text='BART  ·  PVT  ·  Trail Making Test',
                 font=('Segoe UI', 11), bg='#16213e', fg='#6366f1').pack()

        # ── Main content (scrollable canvas) ────────────────────────────────
        outer = ttk.Frame(self)
        outer.pack(fill='both', expand=True, padx=16, pady=8)

        canvas = tk.Canvas(outer, bg='#1a1a2e', highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0,0), window=inner, anchor='nw')

        def on_resize(e):
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        canvas.bind('<Configure>', on_resize)

        def on_frame_resize(e):
            canvas.configure(scrollregion=canvas.bbox('all'))
        inner.bind('<Configure>', on_frame_resize)

        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), 'units'))

        self._build_session(inner)
        self._build_screen(inner)
        self._build_order(inner)
        self._build_params(inner)
        self._build_run(inner)

    # ── Section: Participant Info ─────────────────────────────────────────────

    def _build_session(self, parent):
        self.v_pid = tk.StringVar()
        self.v_tx  = tk.StringVar()
        self.v_replay_exact = tk.BooleanVar(value=False)
        self.v_replay_seed = tk.StringVar(value="12345")
        self.v_self_report_begin = tk.BooleanVar(value=False)
        self.v_self_report_end = tk.BooleanVar(value=False)

        frm = ttk.LabelFrame(parent, text=' 👤  Participant Info ', padding=10)
        frm.pack(fill='x', pady=(4,6))

        row = ttk.Frame(frm); row.pack(fill='x')
        self._lbl(row, 'Participant ID:').grid(row=0, column=0, sticky='w', padx=(0,8))
        self._entry(row, self.v_pid, 26).grid(row=0, column=1, sticky='w', padx=(0,24))
        self._lbl(row, 'Treatment / Condition:').grid(row=0, column=2, sticky='w', padx=(0,8))
        self._entry(row, self.v_tx, 20).grid(row=0, column=3, sticky='w')

        row2 = ttk.Frame(frm); row2.pack(fill='x', pady=(8, 0))
        self._check(row2, 'Replay exact random sequence (deterministic)', self.v_replay_exact)\
            .grid(row=0, column=0, sticky='w', padx=(0, 14))
        self._lbl(row2, 'Replay seed:').grid(row=0, column=1, sticky='w', padx=(0,6))
        self._entry(row2, self.v_replay_seed, 12).grid(row=0, column=2, sticky='w')

        row3 = ttk.Frame(frm); row3.pack(fill='x', pady=(8, 0))
        self._check(row3, 'Self-report at beginning', self.v_self_report_begin)\
            .grid(row=0, column=0, sticky='w', padx=(0, 20))
        self._check(row3, 'Self-report at end', self.v_self_report_end)\
            .grid(row=0, column=1, sticky='w')

    # ── Section: Screen Settings ──────────────────────────────────────────────

    def _build_screen(self, parent):
        self.v_screen   = tk.StringVar(value='1920 × 1080')
        self.v_cust_w   = tk.StringVar(value='1920')
        self.v_cust_h   = tk.StringVar(value='1080')
        self.v_fullscr  = tk.BooleanVar(value=True)

        frm = ttk.LabelFrame(parent, text=' 🖥️  Screen Settings ', padding=10)
        frm.pack(fill='x', pady=(0,6))

        row = ttk.Frame(frm); row.pack(fill='x')
        self._lbl(row, 'Resolution:').grid(row=0, column=0, sticky='w', padx=(0,8))
        cb = ttk.Combobox(row, textvariable=self.v_screen,
                          values=list(SCREEN_PRESETS.keys()), state='readonly', width=18)
        cb.grid(row=0, column=1, sticky='w', padx=(0,16))
        cb.bind('<<ComboboxSelected>>', self._on_screen_select)

        self._lbl(row, 'Custom W:').grid(row=0, column=2, sticky='w', padx=(0,4))
        self.e_cust_w = self._entry(row, self.v_cust_w, 6)
        self.e_cust_w.grid(row=0, column=3, sticky='w', padx=(0,4))
        self._lbl(row, '×').grid(row=0, column=4, padx=4)
        self._lbl(row, 'H:').grid(row=0, column=5, sticky='w', padx=(0,4))
        self.e_cust_h = self._entry(row, self.v_cust_h, 6)
        self.e_cust_h.grid(row=0, column=6, sticky='w', padx=(0,16))
        self._check(row, 'Fullscreen', self.v_fullscr).grid(row=0, column=7, sticky='w')

        self._on_screen_select()  # set initial state

    def _on_screen_select(self, *_):
        is_custom = self.v_screen.get() == 'Custom'
        state = 'normal' if is_custom else 'disabled'
        self.e_cust_w.configure(state=state)
        self.e_cust_h.configure(state=state)
        if not is_custom:
            w, h = SCREEN_PRESETS[self.v_screen.get()]
            self.v_cust_w.set(str(w)); self.v_cust_h.set(str(h))

    # ── Section: Test Order ────────────────────────────────────────────────────

    def _build_order(self, parent):
        frm = ttk.LabelFrame(parent, text=' 🔀  Test Order (drag or use arrows) ', padding=10)
        frm.pack(fill='x', pady=(0,6))

        row = ttk.Frame(frm); row.pack(fill='x')

        self.lb = tk.Listbox(row, height=3, selectmode='single',
                             bg='#2d2d44', fg='#e0e0e0', selectbackground='#7c3aed',
                             font=('Segoe UI', 11), relief='flat', bd=0,
                             activestyle='none', highlightthickness=1,
                             highlightcolor='#7c3aed', width=22)
        for t in ALL_TESTS:
            self.lb.insert('end', f'  {t}')
        self.lb.grid(row=0, column=0, rowspan=3, sticky='ns', padx=(0,10))

        btn_up   = tk.Button(row, text='▲  Move Up',   command=self._order_up,
                             bg='#2d2d44', fg='#a78bfa', relief='flat',
                             font=('Segoe UI', 10), padx=10, pady=4, cursor='hand2')
        btn_dn   = tk.Button(row, text='▼  Move Down', command=self._order_down,
                             bg='#2d2d44', fg='#a78bfa', relief='flat',
                             font=('Segoe UI', 10), padx=10, pady=4, cursor='hand2')
        btn_up.grid(row=0, column=1, sticky='w', pady=2)
        btn_dn.grid(row=1, column=1, sticky='w', pady=2)

        hint = ttk.Label(row, text='Select a test then use the arrows to reorder.',
                         font=('Segoe UI', 9), foreground='#888')
        hint.grid(row=2, column=1, sticky='w')

    def _order_up(self):
        sel = self.lb.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]; val = self.lb.get(i)
        self.lb.delete(i); self.lb.insert(i-1, val)
        self.lb.selection_set(i-1)

    def _order_down(self):
        sel = self.lb.curselection()
        if not sel or sel[0] == self.lb.size()-1: return
        i = sel[0]; val = self.lb.get(i)
        self.lb.delete(i); self.lb.insert(i+1, val)
        self.lb.selection_set(i+1)

    def _get_order(self):
        return [self.lb.get(i).strip() for i in range(self.lb.size())]

    # ── Section: Test Parameters ──────────────────────────────────────────────

    def _build_params(self, parent):
        frm = ttk.LabelFrame(parent, text=' ⚙️  Test Parameters ', padding=10)
        frm.pack(fill='x', pady=(0,6))

        nb = ttk.Notebook(frm)
        nb.pack(fill='x')

        self._build_bart_tab(nb)
        self._build_pvt_tab(nb)
        self._build_tmt_tab(nb)

    def _row(self, parent, r, label, widget_factory):
        self._lbl(parent, label).grid(row=r, column=0, sticky='w', padx=(0,10), pady=3)
        w = widget_factory()
        w.grid(row=r, column=1, sticky='w', pady=3)
        return w

    def _build_bart_tab(self, nb):
        tab = ttk.Frame(nb, padding=10); nb.add(tab, text='  BART  ')

        self.b_trials    = tk.IntVar(value=30)
        self.b_array     = tk.IntVar(value=128)
        self.b_ppp       = tk.DoubleVar(value=0.01)
        self.b_interval  = tk.DoubleVar(value=0.1)
        self.b_avg       = tk.IntVar(value=64)
        self.b_topoff    = tk.BooleanVar(value=True)
        self.b_topoff_n  = tk.IntVar(value=15)

        rows = [
            ('Total balloons (trials):',        lambda: self._spin(tab, self.b_trials,   1, 200)),
            ('Max pumps (array size):',          lambda: self._spin(tab, self.b_array,    1, 512)),
            ('$ per pump:',                      lambda: ttk.Spinbox(tab, textvariable=self.b_ppp,
                                                  from_=0.001, to=1.0, increment=0.001,
                                                  format='%.3f', width=8)),
            ('Pump animation interval (s):',     lambda: ttk.Spinbox(tab, textvariable=self.b_interval,
                                                  from_=0.01, to=1.0, increment=0.01,
                                                  format='%.2f', width=8)),
            ('Target avg break point:',          lambda: self._spin(tab, self.b_avg,      1, 512)),
            ('Enable top-off option:',           lambda: self._check(tab, '', self.b_topoff)),
            ('Number of top-off trials:',        lambda: self._spin(tab, self.b_topoff_n, 1, 200)),
        ]
        for i, (lbl, wf) in enumerate(rows):
            self._row(tab, i, lbl, wf)

    def _build_pvt_tab(self, nb):
        tab = ttk.Frame(nb, padding=10); nb.add(tab, text='  PVT  ')

        self.p_dur      = tk.DoubleVar(value=5.0)
        self.p_isi_min  = tk.DoubleVar(value=2.0)
        self.p_isi_max  = tk.DoubleVar(value=10.0)
        self.p_lapse    = tk.IntVar(value=500)
        self.p_timeout  = tk.IntVar(value=3000)

        rows = [
            ('Test duration (minutes):',    lambda: ttk.Spinbox(tab, textvariable=self.p_dur,
                                             from_=0.5, to=60.0, increment=0.5,
                                             format='%.1f', width=8)),
            ('ISI minimum (seconds):',      lambda: ttk.Spinbox(tab, textvariable=self.p_isi_min,
                                             from_=0.5, to=30.0, increment=0.5,
                                             format='%.1f', width=8)),
            ('ISI maximum (seconds):',      lambda: ttk.Spinbox(tab, textvariable=self.p_isi_max,
                                             from_=1.0, to=60.0, increment=0.5,
                                             format='%.1f', width=8)),
            ('Lapse threshold (ms):',       lambda: self._spin(tab, self.p_lapse,   100, 2000)),
            ('Timeout threshold (ms):',     lambda: self._spin(tab, self.p_timeout, 500, 10000)),
        ]
        for i, (lbl, wf) in enumerate(rows):
            self._row(tab, i, lbl, wf)

    def _build_tmt_tab(self, nb):
        tab = ttk.Frame(nb, padding=10); nb.add(tab, text='  Trail Making Test  ')

        self.t_n_elem  = tk.IntVar(value=6)
        self.t_numbers = tk.BooleanVar(value=True)
        self.t_letters = tk.BooleanVar(value=True)
        self.t_shapes  = tk.BooleanVar(value=True)
        self.t_fam     = tk.BooleanVar(value=False)
        self.t_legacy_mixed = tk.BooleanVar(value=False)

        rows = [
            ('Elements per category:',       lambda: self._spin(tab, self.t_n_elem, 3, 10)),
            ('Use numbers:',                 lambda: self._check(tab, '', self.t_numbers)),
            ('Use letters:',                 lambda: self._check(tab, '', self.t_letters)),
            ('Use shapes:',                  lambda: self._check(tab, '', self.t_shapes)),
            ('Run familiarization trials:',  lambda: self._check(tab, '', self.t_fam)),
            ('Use legacy mixed order set:',  lambda: self._check(tab, '', self.t_legacy_mixed)),
        ]
        for i, (lbl, wf) in enumerate(rows):
            self._row(tab, i, lbl, wf)

    # ── Section: Run controls ─────────────────────────────────────────────────

    def _build_run(self, parent):
        frm = ttk.LabelFrame(parent, text=' ▶  Run Tests ', padding=12)
        frm.pack(fill='x', pady=(0,8))

        self.status_var = tk.StringVar(value='Ready.')
        self.status_lbl = ttk.Label(frm, textvariable=self.status_var,
                                    font=('Segoe UI', 10, 'italic'),
                                    foreground='#a78bfa')
        self.status_lbl.pack(anchor='w', pady=(0,8))

        btn_row = ttk.Frame(frm); btn_row.pack(fill='x')

        self.btn_all  = ttk.Button(btn_row, text='▶  Run All Tests (in order)',
                                   style='Run.TButton',
                                   command=lambda: self._run_tests(self._get_order()))
        self.btn_all.grid(row=0, column=0, padx=(0,12), pady=4)

        self.btn_bart = ttk.Button(btn_row, text='Run BART',
                                   style='Solo.TButton',
                                   command=lambda: self._run_tests(['BART']))
        self.btn_pvt  = ttk.Button(btn_row, text='Run PVT',
                                   style='Solo.TButton',
                                   command=lambda: self._run_tests(['PVT']))
        self.btn_tmt  = ttk.Button(btn_row, text='Run TMT',
                                   style='Solo.TButton',
                                   command=lambda: self._run_tests(['TMT']))

        self.btn_bart.grid(row=0, column=1, padx=(0,6))
        self.btn_pvt .grid(row=0, column=2, padx=(0,6))
        self.btn_tmt .grid(row=0, column=3, padx=(0,6))

        self._all_btns = [self.btn_all, self.btn_bart, self.btn_pvt, self.btn_tmt]

        # Output path label
        self.path_var = tk.StringVar(value='Output: (will be created on run)')
        ttk.Label(frm, textvariable=self.path_var,
                  font=('Segoe UI', 9), foreground='#666').pack(anchor='w', pady=(8,0))

    # ── Config builder ────────────────────────────────────────────────────────

    def _build_config(self, excel_path: str, master_seed: int, abort_flag_path: str | None = None) -> dict:
        return {
            # Participant
            'participant_id': self.v_pid.get().strip(),
            'treatment':      self.v_tx.get().strip(),
            # Screen
            'screen_width':  int(self.v_cust_w.get()),
            'screen_height': int(self.v_cust_h.get()),
            'fullscreen':    self.v_fullscr.get(),
            # Excel
            'excel_path':    excel_path,
            'abort_flag_path': abort_flag_path,
            # Randomization
            'master_seed': master_seed,
            'replay_exact_sequence': self.v_replay_exact.get(),
            # Session
            'self_report_begin': self.v_self_report_begin.get(),
            'self_report_end': self.v_self_report_end.get(),
            # BART
            'bart_total_trials':      self.b_trials.get(),
            'bart_array_size':        self.b_array.get(),
            'bart_points_per_pump':   self.b_ppp.get(),
            'bart_pump_interval':     self.b_interval.get(),
            'bart_target_avg_break':  self.b_avg.get(),
            'bart_topoff_enabled':    self.b_topoff.get(),
            'bart_num_topoff_trials': self.b_topoff_n.get(),
            # PVT
            'pvt_duration_minutes':   self.p_dur.get(),
            'pvt_isi_min':            self.p_isi_min.get(),
            'pvt_isi_max':            self.p_isi_max.get(),
            'pvt_lapse_threshold_ms': self.p_lapse.get(),
            'pvt_timeout_ms':         self.p_timeout.get(),
            # TMT
            'tmt_elements_per_category': self.t_n_elem.get(),
            'tmt_use_numbers':           self.t_numbers.get(),
            'tmt_use_letters':           self.t_letters.get(),
            'tmt_use_shapes':            self.t_shapes.get(),
            'tmt_run_familiarization':   self.t_fam.get(),
            'tmt_use_legacy_mixed_order': self.t_legacy_mixed.get(),
        }

    def _prompt_self_report(self, phase_label: str):
        title = f"Self-Report ({phase_label})"
        intro = (
            "Optional self-report enabled for this phase.\n\n"
            "Rate each item 1-9.\n"
            "Take as much time as needed.\n\n"
            "Press Cancel at any prompt to skip."
        )
        messagebox.showinfo(title, intro)
        sleepiness = simpledialog.askinteger(
            title, "Sleepiness (1=very alert, 9=very sleepy):",
            parent=self, minvalue=1, maxvalue=9
        )
        if sleepiness is None:
            return None
        effort = simpledialog.askinteger(
            title, "Effort (1=very low, 9=very high):",
            parent=self, minvalue=1, maxvalue=9
        )
        if effort is None:
            return None
        distraction = simpledialog.askinteger(
            title, "Distraction (1=none, 9=extreme):",
            parent=self, minvalue=1, maxvalue=9
        )
        if distraction is None:
            return None
        notes = simpledialog.askstring(
            title, "Optional notes (press Cancel or leave blank for none):",
            parent=self
        )
        return {
            'Phase': phase_label,
            'Sleepiness': sleepiness,
            'Effort': effort,
            'Distraction': distraction,
            'Notes': notes or '',
        }

    def _write_self_report(self, excel_path: str, pid: str, tx: str, report: dict):
        w = IncrementalExcelWriter(excel_path, 'Self_Report')
        try:
            w.write_row({
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ID': pid,
                'Treatment': tx,
                'Phase': report.get('Phase', ''),
                'Sleepiness': report.get('Sleepiness', ''),
                'Effort': report.get('Effort', ''),
                'Distraction': report.get('Distraction', ''),
                'Notes': report.get('Notes', ''),
            })
        finally:
            w.close()

    def _validate(self) -> bool:
        if not self.v_pid.get().strip():
            messagebox.showwarning('Missing Info', 'Please enter a Participant ID.')
            return False
        if not (self.t_numbers.get() or self.t_letters.get() or self.t_shapes.get()):
            messagebox.showwarning('TMT Config', 'At least one TMT category must be enabled.')
            return False
        try:
            int(self.v_cust_w.get()); int(self.v_cust_h.get())
        except ValueError:
            messagebox.showwarning('Screen', 'Screen width/height must be integers.')
            return False
        if self.v_replay_exact.get():
            try:
                int(self.v_replay_seed.get())
            except ValueError:
                messagebox.showwarning('Replay Seed', 'Replay seed must be an integer.')
                return False
        return True

    # ── Run logic ─────────────────────────────────────────────────────────────

    TEST_SCRIPTS = {'BART': 'bart.py', 'PVT': 'pvt.py', 'TMT': 'trailmaking.py'}

    def _poll_ui_queue(self):
        """Drain UI messages from the worker thread (tkinter is not thread-safe)."""
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == 'status':
                    self.status_var.set(payload)
                elif kind == 'stopped':
                    self._run_was_stopped = True
                elif kind == 'finished':
                    self._run_poll_scheduled = False
                    self._on_all_done()
                    return
        except queue.Empty:
            pass
        if self._run_poll_scheduled:
            self.after(120, self._poll_ui_queue)

    def _run_tests(self, order: list):
        if not self._validate(): return
        for btn in self._all_btns: btn.configure(state='disabled')

        pid        = self.v_pid.get().strip()
        tx         = self.v_tx.get().strip()
        excel_path = make_excel_path(pid, tx)
        if self.v_replay_exact.get():
            master_seed = int(self.v_replay_seed.get())
        else:
            master_seed = random.SystemRandom().randint(1, 2**31 - 2)
        abort_fd, abort_flag_path = tempfile.mkstemp(
            prefix='psychsuite_abort_', suffix='.flag', dir=SCRIPT_DIR
        )
        os.close(abort_fd)
        try:
            os.unlink(abort_flag_path)
        except OSError:
            pass
        config     = self._build_config(excel_path, master_seed=master_seed, abort_flag_path=abort_flag_path)
        self._current_run_context = {
            'excel_path': excel_path,
            'pid': pid,
            'tx': tx,
            'self_report_end': self.v_self_report_end.get(),
        }

        if self.v_self_report_begin.get():
            report = self._prompt_self_report('Beginning')
            if report is not None:
                self._write_self_report(excel_path, pid, tx, report)

        replay_note = " (replay mode)" if self.v_replay_exact.get() else ""
        self.path_var.set(f'Output: {excel_path}  |  Seed: {master_seed}{replay_note}')

        order_copy = list(order)
        total = len(order_copy)
        self._run_was_stopped = False

        def worker():
            try:
                remaining = list(order_copy)
                idx = 0
                while remaining:
                    if os.path.exists(abort_flag_path):
                        self._ui_queue.put(('status', 'Battery stopped by experimenter.'))
                        self._ui_queue.put(('stopped', None))
                        break
                    name = remaining.pop(0)
                    idx += 1
                    self._ui_queue.put(('status', f'Running {name}... ({idx}/{total})'))
                    script = self.TEST_SCRIPTS.get(name)
                    if not script:
                        continue

                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                                    delete=False, dir=SCRIPT_DIR) as f:
                        json.dump(config, f)
                        cfg_path = f.name
                    try:
                        proc = subprocess.run(
                            [sys.executable,
                             os.path.join(SCRIPT_DIR, script),
                             cfg_path],
                            cwd=SCRIPT_DIR,
                        )
                        if proc.returncode != 0:
                            self._ui_queue.put(('status', f'{name} exited with code {proc.returncode}.'))
                        if os.path.exists(abort_flag_path):
                            self._ui_queue.put(('status', 'Battery stopped by experimenter.'))
                            self._ui_queue.put(('stopped', None))
                            break
                    finally:
                        try:
                            os.unlink(cfg_path)
                        except OSError:
                            pass
            finally:
                try:
                    if os.path.exists(abort_flag_path):
                        os.unlink(abort_flag_path)
                except OSError:
                    pass
                self._ui_queue.put(('finished', None))

        self._run_poll_scheduled = True
        self.after(50, self._poll_ui_queue)
        threading.Thread(target=worker, daemon=True).start()

    def _on_all_done(self):
        for btn in self._all_btns: btn.configure(state='normal')
        ctx = self._current_run_context
        if ctx and ctx.get('self_report_end'):
            report = self._prompt_self_report('End')
            if report is not None:
                self._write_self_report(ctx['excel_path'], ctx['pid'], ctx['tx'], report)
        if self._run_was_stopped:
            self.status_var.set('Battery stopped by experimenter. Ready for next participant.')
            messagebox.showinfo('Stopped', 'Battery stopped by experimenter.\n\nData up to stop point was saved.')
        else:
            self.status_var.set('All tests complete. Ready for next participant.')
            messagebox.showinfo('Done', 'All selected tests have finished.\n\nData saved to Excel.')
        self._current_run_context = None


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = PsychLauncher()
    app.mainloop()
