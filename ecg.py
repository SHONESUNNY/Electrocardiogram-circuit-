import asyncio ,os 
import csv
import struct
from pathlib import Path
from datetime import datetime, timedelta
from bleak import BleakClient, BleakScanner
#from gsr_processor import GSRProcessor, GSREDAAnalyzer
from ecg_neurokit2 import ECGProcessor

# ─── Config ───────────────────────────────────────────────────────────────────
DEVICE_NAME      = "S-IOT"
NOTIFY_CHAR_UUID = "0000fe42-8e22-4541-9d4c-21edae82ed19"
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_FILENAME = SCRIPT_DIR / "sensor_data_log.csv"
RECONNECT_DELAY  = 2

MAGIC_BYTES  = struct.pack("<I", 0xDEADBEEF)
FRAME_SIZE   = 294        # 4 magic + 256 ECG + 32 GSR + 2 temp
SAMPLE_RATE  = 250

# How often to run the heavier computations (in frames, not seconds)
# 128 samples/frame @ 250Hz ≈ 0.512s/frame
HR_UPDATE_EVERY_N_FRAMES  = 5     # ~2.56s
HRV_UPDATE_EVERY_N_FRAMES = 80    # ~51s (HRV window itself is 5 min internally)

# ─── Globals ──────────────────────────────────────────────────────────────────
rx_buffer      = bytearray()
csv_file       = None
csv_writer     = None
frame_id       = 0
sample_counter = 0
START_TIME     = datetime.now()
ecg_processor  = ECGProcessor(fs=SAMPLE_RATE)

# Latest known values — held constant between updates, written every row
latest_hr            = None   # bpmMicrosoft.QuickAction.Bluetooth
latest_sdnn           = None   # ms
latest_rmssd          = None   # ms
latest_hrQuality      = None  




def process_frame(frame: bytes):
    global frame_id, sample_counter
    global latest_hr, latest_sdnn, latest_rmssd , latest_hrQuality
    try:
        raw = struct.unpack("<128h16hH", frame[4:])
    except struct.error as e:
        print(f"[ERROR] unpack: {e}") 
        return

    ecg_raw  = raw[0:128]
    ecg_v   = [(v) * 3.3 / 4095.0 for v in ecg_raw]
    ecg_processor.add_samples(ecg_v)
    processed_ecgv = ecg_processor.get_display_chunk(n=128)

    # ── Tier 1: HR — updates every few seconds ────────────────────────────────
    if frame_id % HR_UPDATE_EVERY_N_FRAMES == 0:
        hr_result = ecg_processor.get_hr()
        if hr_result is not None:
            latest_hr = hr_result["HR_bpm"]
            latest_hrQuality     = hr_result["SQI"]
    # ── Tier 2: HRV — updates every ~50s, needs 5 min of data internally ─────
    if frame_id % HRV_UPDATE_EVERY_N_FRAMES == 0:
        hrv_result = ecg_processor.compute_hrv()
        if hrv_result is not None:
            latest_sdnn         = hrv_result["SDNN_ms"]
            latest_rmssd        = hrv_result["RMSSD_ms"]
  

  
    # ── Write raw ECG/GSR samples + latest known parameters (held constant) ──
    if csv_writer is not None:

        for i in range(128):
            sample_time = START_TIME + timedelta(seconds=(sample_counter + i) / SAMPLE_RATE)
            ts_str = sample_time.strftime("%H:%M:%S.%f")[:-3]
            csv_writer.writerow([ ts_str,round(processed_ecgv[i], 5),round(ecg_v[i], 5),
                latest_hr , latest_sdnn, latest_rmssd ])
           
        csv_file.flush()         
    sample_counter += 128
    frame_id += 1
    print(f"[Frame {frame_id}] samples={sample_counter} | " f"HR={latest_hr} | SDNN={latest_sdnn} | RMSSD={latest_rmssd} ")

def notification_handler(sender: int, data: bytearray):
    global rx_buffer

    rx_buffer.extend(data)

    while True:
        start = rx_buffer.find(MAGIC_BYTES)
        if start == -1: return

        if start > 0:
            print(f"[ALIGN] Dropping {start} bytes before magic")
            del rx_buffer[:start]
        if len(rx_buffer) < FRAME_SIZE: return

        frame = bytes(rx_buffer[:FRAME_SIZE])
        del rx_buffer[:FRAME_SIZE]
        process_frame(frame)


async def connect_and_stream():
    print("Scanning...")
    devices = await BleakScanner.discover()
    target = next((d for d in devices if d.name == DEVICE_NAME), None)

    if not target:
        print(f"Could not find {DEVICE_NAME}")
        return

    print(f"Found {DEVICE_NAME} at {target.address}. Connecting...")
    async with BleakClient(target.address) as client:
        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)
        print("Connected and receiving...")
        while client.is_connected:
            await asyncio.sleep(0.2)
        print("Disconnected.")


async def main():
    global csv_file, csv_writer

    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "Timestamp", "ecg_processed_V", "ecg_raw_V",
            "HR_bpm", "SDNN_ms", "RMSSD_ms"])

        while True:
            try:
                await connect_and_stream()
                print(f"Retrying in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)
            except asyncio.CancelledError:
                break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTerminated by user.")