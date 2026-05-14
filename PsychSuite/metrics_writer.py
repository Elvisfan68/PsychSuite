"""
Write standardized per-task summaries into a shared Derived_Metrics sheet.
"""
from datetime import datetime

from data_writer import IncrementalExcelWriter


def write_derived_metrics(excel_path: str, task: str, participant_id: str, treatment: str, metrics: dict):
    row = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Task": task,
        "Participant_ID": participant_id,
        "Treatment": treatment,
        "Completion_Status": "",

        # PVT
        "PVT_Median_RT_ms": "",
        "PVT_Lapses": "",
        "PVT_False_Starts": "",
        "PVT_Fastest10_Mean_RT_ms": "",
        "PVT_Slowest10_Mean_RT_ms": "",
        "PVT_Valid_Response_Count": "",

        # TMT
        "TMT_Experimental_Trials_Completed": "",
        "TMT_Completion_Time_s": "",
        "TMT_Total_Errors": "",
        "TMT_Corrected_Error_Burden": "",
        "TMT_InterClick_RT_Variability_ms": "",
        "TMT_Click_Count": "",
        "TMT_Near_Miss_Total": "",
        "TMT_Repeated_Same_Wrong_Target_Total": "",
        "TMT_Correction_Latency_Mean_ms": "",

        # BART
        "BART_Trials_Completed": "",
        "BART_Adjusted_Pumps_Mean": "",
        "BART_Explosion_Rate": "",
        "BART_Topoff_Offered_Count": "",
        "BART_Topoff_Used_Count": "",
        "BART_Topoff_Usage_Rate_When_Offered": "",
        "BART_Hesitation_Before_Pump_Mean_ms": "",
        "BART_Hesitation_Before_Collect_Mean_ms": "",
        "BART_Topoff_Decision_Latency_Mean_ms": "",
    }
    row.update(metrics or {})
    w = IncrementalExcelWriter(excel_path, "Derived_Metrics")
    try:
        w.write_row(row)
    finally:
        w.close()
