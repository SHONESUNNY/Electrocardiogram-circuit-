import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import os
from collections import deque
import numpy as np         # NEW IMPORT
import neurokit2 as nk     # NEW IMPORT

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_FILENAME = os.path.join(SCRIPT_DIR, "sensor_data_log.csv")
SAMPLE_RATE   = 250
DISPLAY_SECS  = 10
SCROLL_SPEED  = 250

SMOOTH        = False
SMOOTH_WINDOW = 4
AUTO_SCALE    = True
AUTO_PADDING  = 0.1   

WINDOW_SAMPLES = SAMPLE_RATE * DISPLAY_SECS
voltage_buf    = deque(maxlen=WINDOW_SAMPLES)
raw_voltage_buf   = deque(maxlen=WINDOW_SAMPLES)
time_buf       = deque(maxlen=WINDOW_SAMPLES)
last_row_count = 0
total_samples  = 0

def read_new_samples():
    global last_row_count
    new_samples = []
    if not os.path.exists(CSV_FILENAME):
        return new_samples
    try:
        with open(CSV_FILENAME, mode='r', errors='ignore') as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
            for row in all_rows[last_row_count:]:
              try:
                ts  = row["Timestamp"]
                ecg_processed = float(row["ecg_processed_V"])
                ecg_raw = float(row["ecg_raw_V"])
                new_samples.append((ecg_processed , ecg_raw))
              except (KeyError, ValueError):continue    
        last_row_count = len(all_rows)
    except Exception as e:
        print(f"[ERROR] {e}")
    return new_samples


def animate(i):
    global total_samples
    try:
        new = read_new_samples()
        if new:
            for ecg_processed , ecg_raw in new:
                total_samples += 1
                time_buf.append(total_samples / SAMPLE_RATE)
                voltage_buf.append(ecg_processed)
                raw_voltage_buf.append(ecg_raw)

        ax.clear()
        ax.set_facecolor('#1e1e2e')
        ax.tick_params(colors='white', labelsize=9)
        ax.grid(True, linestyle='--', alpha=0.3, color='gray')
        for spine in ax.spines.values():
            spine.set_edgecolor('#444466')

        if voltage_buf:
            t_data = list(time_buf)
            v_data   = list(voltage_buf)      # processed
            raw_data = list(raw_voltage_buf)  # raw
            # Auto scale: fit y-axis tightly around the actual signal
            if raw_data:
                raw_baseline = sum(raw_data) / len(raw_data)
                raw_data = [r - raw_baseline for r in raw_data]
            if AUTO_SCALE:
                v_min = min(v_data + raw_data)
                v_max = max(v_data + raw_data)
                amplitude = v_max - v_min
                y_min = v_min - AUTO_PADDING
                y_max = v_max + AUTO_PADDING
                scale_note = f"amp={amplitude:.3f}V"
            else:
                y_min, y_max = 0,3.3
                scale_note = "fixed scale"

            label = f"Voltage  |  {total_samples} samples  |  {scale_note}"
            ax.plot(t_data, raw_data, color='#00d4ff', linewidth=0.9, label="Raw ECG")
            ax.plot(t_data, v_data, color='#888899', linewidth=0.6, alpha=0.6, label=label)
            # ─── NEW: LIVE PEAK DETECTION & PLOTTING ────────────────────────
            # We need at least 2 seconds of data to accurately find peaks
            if len(v_data) > SAMPLE_RATE * 2:
                v_array = np.array(v_data, dtype=np.float64)
                
                try:
                    # 1. Find R-Peaks
                    _, r_info = nk.ecg_peaks(v_array, sampling_rate=SAMPLE_RATE, method="pantompkins1985")
                    r_peaks_arr = r_info["ECG_R_Peaks"]
                    r_peaks = [int(p) for p in np.ravel(r_peaks_arr) if not np.isnan(p)]
                    if len(r_peaks) > 0:
                        # Map indices back to our time and voltage arrays
                        artifacts, r_peaks_fixed = nk.signal_fixpeaks( np.array(r_peaks, dtype=int) ,SAMPLE_RATE, iterative=True, method="neurokit")
                        r_peaks = [int(p) for p in np.ravel(r_peaks_fixed)if not np.isnan(p) and 0 <= int(p) < len(v_data)]
                        r_times = [t_data[p] for p in r_peaks]
                        r_volts = [v_data[p] for p in r_peaks]
                        
                        # Draw Red Dots on the R-Peaks
                        ax.scatter(r_times, r_volts, color='red', s=30, zorder=4, label="R-Peak")
                        
                        # 2. Find T-Waves using the DWT method (fast and accurate)
                        _, waves = nk.ecg_delineate(v_array, r_peaks, sampling_rate=SAMPLE_RATE, method="dwt")
                        t_peaks_raw = waves["ECG_T_Peaks"]
                        
                        # Filter out NaNs (which happen if a T-wave is obscured by noise)
                        t_peaks = [int(p) for p in t_peaks_raw if not np.isnan(p)]
                        
                        if len(t_peaks) > 0:
                            t_times = [t_data[p] for p in t_peaks]
                            t_volts = [v_data[p] for p in t_peaks]
                            
                            # Draw Orange Dots on the T-Waves
                            ax.scatter(t_times, t_volts, color='orange', s=25, zorder=4, label="T-Wave")
                            
                except Exception as detect_err:
                    print(f"[DEBUG] Peak detection error: {detect_err}")
            # ────────────────────────────────────────────────────────────────

            ax.set_xlim(t_data[-1] - DISPLAY_SECS, t_data[-1] + 0.1)
            ax.set_ylim(y_min, y_max)
            
            # Ensure legends don't duplicate if multiple scatter points exist
            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys(), loc='upper left', facecolor='#2a2a3e', labelcolor='white', fontsize=9)
            
        else:
            ax.text(0.5, 0.5, f'Waiting for data...',
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=10, color='gray')

        ax.set_title(f"Live STM32 Sensor Feed  |  {SAMPLE_RATE} Hz  |  {DISPLAY_SECS}s window",
                     color='white', fontsize=11, pad=8)
        ax.set_ylabel("Voltage (V)", color='white', labelpad=8)
        ax.set_xlabel("Elapsed Time (s)", color='white', labelpad=8)

    except Exception as e:
        print(f"[ERROR] animate: {e}")

fig, ax = plt.subplots(figsize=(13, 5))
fig.patch.set_facecolor('#1e1e2e')
ax.set_facecolor('#1e1e2e')
fig.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.13)

print(f"Starting plotter — {DISPLAY_SECS}s window at {SAMPLE_RATE} Hz")
print(f"Reading from: {CSV_FILENAME}")

ani = animation.FuncAnimation(fig, animate, interval=SCROLL_SPEED, cache_frame_data=False)
plt.show()