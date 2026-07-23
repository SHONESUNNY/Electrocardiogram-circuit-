"""
Two-tier ECG processing:

1. HR tier — fast, ~8s window, updates frequently.
   get_display_chunk()  → cleanly filtered samples for live plotting
   get_hr()              → instantaneous heart rate (bpm)

2. HRV tier — 5-minute window, updates infrequently.
   compute_hrv()          → SDNN, RMSSD, Baevsky Stress Index only.
"""

import numpy as np
import neurokit2 as nk
from collections import deque

# ─── Constants ────────────────────────────────────────────────────────────────
HR_WINDOW_SEC   = 8      # fast tier — instantaneous HR
HRV_WINDOW_SEC  = 300    # slow tier — proper SDNN/RMSSD window (5 min)
HRV_MIN_RR_COUNT = 4     # minimum R-R intervals to attempt HR


class ECGProcessor:
    def __init__(self, fs: int = 250):
        self.fs = fs

        self.hr_window_samples  = int(HR_WINDOW_SEC * fs)
        self.hrv_window_samples = int(HRV_WINDOW_SEC * fs)
        self._hr_buffer = deque(maxlen=self.hr_window_samples)
        self._hrv_buffer = deque(maxlen=self.hrv_window_samples)

    # ─── Ingest & Clean ─────────────────────────────────────────────────────

    def add_samples(self, samples: list) -> None:
        """Push raw ECG samples. Feeds both buffers."""
        for s in samples:
            self._hr_buffer.append(s)
            self._hrv_buffer.append(s)

    def _clean_signal(self, raw_signal: np.ndarray) -> np.ndarray:
        # UPDATED: Explicitly use Pan-Tompkins 1985 bandpass filter
        return nk.ecg_clean(raw_signal, sampling_rate=self.fs, method="pantompkins1985")

    def get_display_chunk(self, n: int = 128) -> list:
        """Last n CLEANED samples for live plotting."""
        process_window = min(len(self._hr_buffer), self.fs * 2)
        if process_window < self.fs:
            return list(self._hr_buffer)[-n:]
            
        raw_chunk = np.array(list(self._hr_buffer)[-process_window:], dtype=np.float64)
        clean_chunk = self._clean_signal(raw_chunk)
        
        return clean_chunk[-n:].tolist()

    def get_hr(self) -> dict | None:
        if len(self._hr_buffer) < self.hr_window_samples:return None

        ecg = np.array(self._hr_buffer, dtype=np.float64)

        if np.ptp(ecg) == 0: 
             print("[ECG] Sensor flatline detected.")
             return None

        cleaned_ecg = self._clean_signal(ecg)

        try:


            # 1. Find peaks using Pan-Tompkins
            corrected_ecg, is_inverted = nk.ecg_invert(cleaned_ecg, sampling_rate=self.fs)
            _, info = nk.ecg_peaks(corrected_ecg, sampling_rate=self.fs, method="pantompkins1985")
            r_peaks = info["ECG_R_Peaks"]
            print(f"[ECG] R-peaks detected:" ,r_peaks)
          
            if len(r_peaks) < HRV_MIN_RR_COUNT: return None

          # 2. Fix false positives (removes impossibly close spikes)
            artifacts, r_peaks = nk.signal_fixpeaks(r_peaks, sampling_rate=self.fs, iterative=True, method="neurokit")
            quality = nk.ecg_quality(corrected_ecg,rpeaks=r_peaks,
                sampling_rate=self.fs, method="zhao2018",)
            if quality == "Unacceptable":
                 print("[ECG] Signal rejected.")
                 return None
            
            rr_ms = np.diff(r_peaks) * 1000 / self.fs
            hr = 60000 / rr_ms
            print(f"[ECG] HR series manual: {hr}")

            
            hr_series = nk.signal_rate(r_peaks, sampling_rate=self.fs, desired_length=len(cleaned_ecg))
            return {
                "HR_bpm":     int(np.median(hr_series)),
                "HR_min_bpm": round(float(np.min(hr_series)),  2),
                "HR_max_bpm": round(float(np.max(hr_series)),  2),
                "SQI":        quality
            }

        except Exception as e:
            print(f"[ECG] HR error: {e}")
            return None


    # ─── Tier 2: HRV (slow, 5-min window) ──────────────────────────────────

    def compute_hrv(self) -> dict | None:
        if len(self._hrv_buffer) < self.hrv_window_samples:
            filled_sec = len(self._hrv_buffer) / self.fs
            print(f"[ECG] HRV buffering... {filled_sec:.0f}s / {HRV_WINDOW_SEC}s")
            return None

        ecg = np.array(self._hrv_buffer, dtype=np.float64)
        
        # 1. Clean the signal
        cleaned_ecg = self._clean_signal(ecg)

        try:
            
            _, info = nk.ecg_peaks(cleaned_ecg, sampling_rate=self.fs, method="pantompkins1985")
            r_peaks = info["ECG_R_Peaks"]
            if len(r_peaks) < HRV_MIN_RR_COUNT + 1:return None


            # 3. Calculate HRV
            hrv_time = nk.hrv_time(r_peaks, sampling_rate=self.fs, show=False)
            sdnn  = float(hrv_time["HRV_SDNN"].values[0])
            rmssd = float(hrv_time["HRV_RMSSD"].values[0])
            return {
                "SDNN_ms":      round(sdnn,  2),
                "RMSSD_ms":     round(rmssd, 2),
                "r_peak_count": len(r_peaks),
            }

        except Exception as e:
            print(f"[ECG] HRV error: {e}")
            return None