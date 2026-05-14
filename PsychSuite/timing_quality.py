"""
Frame timing quality helpers for PsychSuite tasks.
"""
from __future__ import annotations


class FrameTimingMonitor:
    def __init__(self, win, threshold_factor: float = 1.5, fallback_hz: float = 60.0):
        self.win = win
        hz = win.getActualFrameRate() or fallback_hz
        self.expected_interval_s = 1.0 / float(hz)
        self.threshold_s = self.expected_interval_s * float(threshold_factor)

        self.win.recordFrameIntervals = True
        self.win.refreshThreshold = self.threshold_s

        self.run_total_frames = 0
        self.run_dropped_frames = 0
        self.run_max_interval_s = 0.0

    def start_segment(self):
        self.win.frameIntervals = []

    def end_segment(self):
        intervals = list(self.win.frameIntervals)
        self.win.frameIntervals = []

        frame_count = len(intervals)
        dropped = sum(1 for dt in intervals if dt > self.threshold_s)
        max_interval_s = max(intervals) if intervals else 0.0
        exceeded = dropped > 0

        self.run_total_frames += frame_count
        self.run_dropped_frames += dropped
        if max_interval_s > self.run_max_interval_s:
            self.run_max_interval_s = max_interval_s

        return {
            "frame_count": frame_count,
            "dropped_frames": dropped,
            "max_interval_ms": round(max_interval_s * 1000.0, 3),
            "threshold_ms": round(self.threshold_s * 1000.0, 3),
            "expected_frame_ms": round(self.expected_interval_s * 1000.0, 3),
            "exceeded_threshold": bool(exceeded),
        }

    def run_summary(self):
        total = self.run_total_frames
        dropped = self.run_dropped_frames
        quality_score = 100.0 if total <= 0 else max(0.0, 100.0 * (1.0 - (dropped / total)))
        return {
            "run_total_frames": total,
            "run_dropped_frames": dropped,
            "run_max_interval_ms": round(self.run_max_interval_s * 1000.0, 3),
            "run_quality_score": round(quality_score, 2),
            "run_exceeded_threshold": bool(dropped > 0),
        }


def timing_row_fields(segment_metrics: dict, run_fields_blank: bool = True):
    data = {
        "Timing_Dropped_Frames": segment_metrics.get("dropped_frames", 0),
        "Timing_Max_Frame_Interval_ms": segment_metrics.get("max_interval_ms", 0.0),
        "Timing_Exceeded_Threshold": segment_metrics.get("exceeded_threshold", False),
        "Timing_Frame_Threshold_ms": segment_metrics.get("threshold_ms", 0.0),
        "Timing_Expected_Frame_ms": segment_metrics.get("expected_frame_ms", 0.0),
    }
    if run_fields_blank:
        data.update(
            {
                "Timing_Run_Quality_Score": "",
                "Timing_Run_Dropped_Frames": "",
                "Timing_Run_Total_Frames": "",
                "Timing_Run_Max_Frame_Interval_ms": "",
                "Timing_Run_Exceeded_Threshold": "",
            }
        )
    return data


def timing_run_fields(run_summary: dict):
    return {
        "Timing_Run_Quality_Score": run_summary.get("run_quality_score", 0.0),
        "Timing_Run_Dropped_Frames": run_summary.get("run_dropped_frames", 0),
        "Timing_Run_Total_Frames": run_summary.get("run_total_frames", 0),
        "Timing_Run_Max_Frame_Interval_ms": run_summary.get("run_max_interval_ms", 0.0),
        "Timing_Run_Exceeded_Threshold": run_summary.get("run_exceeded_threshold", False),
    }
