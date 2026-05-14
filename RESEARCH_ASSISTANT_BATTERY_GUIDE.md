# PsychTest Battery Manual (Research Assistant Guide)

This guide explains the full battery workflow for:
- BART
- PVT
- Trail Making Test (TMT)

It is written for day-to-day data collection staff.

---

## 1) What This Battery Does

The battery runs three tasks from one master launcher:
- `BART` (risk taking / balloon pumping decisions)
- `PVT` (psychomotor vigilance / reaction-time task)
- `TMT` (visual search + sequencing task)

Key system behavior:
- One participant run creates one Excel workbook.
- Data is written incrementally during tasks (crash-safe style).
- You can pause tasks with `ESC` (pause menu).
- Optional self-report can be collected at beginning/end.
- Deterministic replay mode is available using a seed.
- On macOS, `master.py` attempts to set display mode to `3840x2160` before launcher start.

---

## 2) One-Time Computer Setup

Recommended Python:
- Python `3.11` (64-bit)

Setup steps (Windows terminal in project folder):

```bat
cd C:\Users\colon\Desktop\Psych
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

For macOS stations (one-time):
- Install `displayplacer` so startup display mode automation can run:
  - `brew install displayplacer`

Run launcher:

```bat
python master.py
```

---

## 3) Master Launcher Overview

The launcher controls:
- participant identifiers
- screen size / fullscreen behavior
- task order
- task parameters
- deterministic replay seed settings
- optional self-report settings

### Participant section
- **Participant ID** (required)
- **Treatment / Condition**
- **Replay exact random sequence (deterministic)** (optional)
- **Replay seed** (integer, used when replay is enabled)
- **Self-report at beginning** (optional)
- **Self-report at end** (optional)

### Screen section
- Preset resolution or custom width/height
- Fullscreen toggle

### Order section
- Reorder tasks with up/down buttons

### Parameters tabs
- BART, PVT, TMT parameters are editable before run
- TMT includes `Use legacy mixed order set`
- `Run familiarization trials` is **OFF by default** for TMT

### Run controls
- Run all in configured order
- Run individual task buttons

---

## 4) Standard RA Workflow (Per Participant)

1. Open launcher (`python master.py`).
2. Enter Participant ID and Treatment.
3. Confirm screen settings for this station.
4. Confirm task order and parameter values.
5. Decide whether deterministic replay is needed:
   - Usually OFF for normal data collection.
   - ON only for troubleshooting/reproducibility.
6. If enabled, complete beginning self-report.
7. Start run (all tasks or selected task).
8. Monitor participant and intervene only when needed.
9. If enabled, complete end self-report.
10. Confirm output path and file present in `PsychSuite\Data`.

---

## 5) Pause / Emergency Behavior

In-task `ESC` opens pause menu (timing is frozen while paused).

Pause menu options:
- `Resume (R)`
- `Quit Test (Q)` -> ends current task only
- `Quit Battery (X)` -> stops remaining tasks

Mouse buttons are clickable; keyboard shortcuts also work.

Important:
- Pause time is excluded from timed metrics in PVT/TMT.
- BART pump timing is adjusted on resume to avoid jump artifacts.

---

## 6) Task-by-Task Process

## 6.1 PVT Process

Flow:
1. Instructions
2. **Mandatory competency practice gate**
3. Main timed PVT
4. Completion summary + derived metrics

Practice gate (mandatory):
- Must obtain at least minimum valid responses (default `3`)
- Must avoid repeated false starts (no 2 consecutive false starts)
- Unlimited retries
- Message explicitly states participant can take as much time as needed

Main PVT captures:
- ISI per trial
- RT or no-response/false-start markers
- lapse flag
- timing quality flags

Derived metrics written at end:
- median RT
- lapses
- false starts
- fastest 10% mean RT
- slowest 10% mean RT
- valid response count

---

## 6.2 TMT Process

Flow:
1. Instructions
2. **Mandatory competency practice gate**
3. Optional familiarization block (if enabled)
4. Experimental trials
5. Completion summary + derived metrics

Practice gate (mandatory):
- Mixed-category sequence (`1 -> triangle -> A -> 2 -> square -> B -> 3 -> pentagon -> C`)
- Pass criterion: errors <= configured threshold (default `1`)
- Unlimited retries
- Reminder that participant can take as much time as needed

Familiarization:
- Controlled by `Run familiarization trials` checkbox
- Still optional and preserved
- Runs after competency gate, before experimental trials
- Default is OFF unless the RA enables it

Mixed-order mode:
- Default/new mode: all unique category permutations x ascending/descending
- Legacy mode: old 3-order template set x ascending/descending

Enhanced TMT error modeling:
- near-miss count
- repeated same wrong target
- correction latency
- On macOS, TMT visual targets are intentionally rendered larger for readability

Derived metrics written at end:
- experimental trials completed
- completion time
- total errors
- corrected-error burden
- inter-click RT variability
- near-miss total
- repeated-same-wrong-target total
- correction latency mean

---

## 6.3 BART Process

Flow:
1. Instructions
2. **Mandatory competency practice gate**
3. Main BART balloons
4. Completion summary + derived metrics

Practice gate (mandatory):
- Participant must pump at least once and collect successfully
- Unlimited retries
- Reminder that participant can take as much time as needed

Main BART captures:
- explosion point
- initial pump selection
- top-off behavior
- earned values
- timing quality flags

Decision-process enrichment fields:
- selected pumps (initial/top-off)
- hesitation before pump
- hesitation before collect
- top-off decision latency

Derived metrics written at end:
- trials completed
- adjusted pumps mean
- explosion rate
- top-off offered/used counts
- top-off usage rate when offered
- mean hesitation before pump
- mean hesitation before collect
- mean top-off decision latency

---

## 7) Randomization and Replay Mode

The battery supports deterministic randomization.

Concept:
- Each run has a **master seed**.
- Each task derives a **task seed**.
- Task internals derive **block seeds** (e.g., trial planning blocks).

If replay mode is ON with same seed:
- randomization should reproduce the same sequence logic.

Seeds are logged in `_SessionLog` as `SEED ...` entries.

Use cases:
- debugging odd runs
- audit/reproducibility
- cross-machine verification

---

## 8) Output Files and Sheets

Workbook path:
- `PsychSuite\Data\<Participant>_<Treatment>_<timestamp>.xlsx`

Common sheets:
- `BART`
- `PVT`
- `TMT`
- `Derived_Metrics`
- `_SessionLog`

Optional sheet:
- `Self_Report` (only if enabled in launcher)

Data safety:
- rows are saved incrementally during testing
- crash should preserve data up to last written row

---

## 9) Timing Integrity Checks (Why They Matter)

Each task logs frame-timing quality:
- dropped frames
- max frame interval
- threshold exceeded flag

Run-level quality summary is written as a `__RUN_SUMMARY__` row plus run fields:
- total frames
- dropped frames
- max interval
- quality score

Why:
- helps distinguish participant performance from machine lag artifacts

---

## 10) Self-Report Module (Optional)

Can be enabled at:
- beginning of battery
- end of battery

Questions (1-9 scale):
- sleepiness
- effort
- distraction
- optional notes

Stored in `Self_Report` sheet with phase label (`Beginning` / `End`).

---

## 11) RA Quality Control Checklist

Before run:
- confirm Participant ID and treatment
- verify screen mode/resolution
- verify intended task order
- verify replay mode is OFF unless intentionally reproducing

During run:
- watch for participant misunderstanding
- use pause menu when needed (ESC)
- document unusual interruptions

After run:
- verify workbook exists
- verify expected sheets exist
- verify completion status in Derived_Metrics
- verify no obvious aborted run unless intentional

---

## 12) Troubleshooting

If participant gets stuck:
- Press `ESC` -> use pause menu

If battery should stop:
- pause menu -> `Quit Battery (X)`

If run behavior is unusual and needs reproduction:
- rerun with deterministic replay + same seed

If mouse appears missing:
- open pause menu (it forces cursor visible)

If task ended early unexpectedly:
- check `_SessionLog` and `Completion_Status` in `Derived_Metrics`

If macOS startup prints display-mode warning:
- Battery can still run; this means requested display mode was not applied
- Verify `displayplacer` installation and test modes with `displayplacer list`

---

## 13) Notes for Study Documentation

For Methods/Protocol writeups, include:
- task order policy
- whether replay mode used (normally no)
- whether self-report enabled
- TMT mode (legacy vs all permutations)
- familiarization setting
- any non-default parameter changes

---

## 14) Quick RA Script (Short Form)

1. Launch battery.
2. Enter ID/treatment.
3. Confirm settings.
4. Run all tasks.
5. Use ESC pause menu if needed.
6. Finish end self-report if enabled.
7. Confirm workbook saved and complete.

---

If protocol changes are made later, update this guide version and date.
