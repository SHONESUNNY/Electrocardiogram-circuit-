# Electrocardiogram-circuit-

<img width="1167" height="715" alt="image" src="https://github.com/user-attachments/assets/1776d317-c218-4b9e-b9a5-35b80b7f0d33" />
<img width="796" height="510" alt="image" src="https://github.com/user-attachments/assets/4a95ed5a-d4b4-434a-a13b-a5f666680b46" />


##  ECG Analog Front-End (AFE) Pipeline

To ensure the **STM32WB55** receives a clean, centered, and low-noise ECG signal before digital processing, the raw biopotential passes through a custom multi-stage **Analog Front-End (AFE)**.

### 1. Pre-Amplification & Common-Mode Noise Rejection
- Differential ECG signals are amplified with a gain of G = 47 using an **INA128 instrumentation amplifier**.
- A **Right Leg Drive (RLD)** circuit provides active feedback to improve **Common-Mode Rejection Ratio (CMRR)** and suppress power-line interference.

### 2. High-Pass Filtering (C = 10uF , R = 100k ohm)
- A passive **High-Pass Filter (HPF)** removes:
 -  Frequencies lower than fc = 0.15Hz
  - Electrode-skin DC offset (half-cell potential)
  - Baseline wander caused by respiration and body movement

### 3. Final Gain & Signal Centering
- A second **INA128** provides additional amplification(Gain = 11.86).
- A **1 V DC offset** is added to shift the bipolar ECG waveform into the **0–3.3 V** input range of the STM32 ADC, preventing clipping during digitization.

### 4. Anti-Aliasing Filter (C = 0.1uF , R = 43k ohm)
- An **RC Low-Pass Filter (LPF)** attenuates high-frequency components such as:
-  Frequencies higher than fc = 37Hz
  - Electromyographic (EMG) noise
  - Radio-frequency (RF) interference
- This prevents aliasing before analog-to-digital conversion.

### 5. Analog-to-Digital Conversion
- The conditioned ECG signal is sampled by the **STM32WB55 ADC**(It utilizes a 12 bit ADC ). 
- ADC sampling is hardware-triggered using **Timers** and transferred efficiently via **Circular DMA** for continuous real-time acquisition.

 ###  Completed  circuit using CNC machine 
 <img width="899" height="1599" alt="WhatsApp Image 2026-07-19 at 18 00 29" src="https://github.com/user-attachments/assets/c4c46470-7ef3-4ae8-94a3-261934ddb795" />

## Real-Time ECG Processing Pipeline

The digitized ECG data is streamed from the **STM32WB55** to a Python application over **Bluetooth Low Energy (BLE)**, where it is processed and visualized in real time.

### Key Features
- Implemented a real-time ECG processing pipeline using **Python**, **NeuroKit2**, and **NumPy** for signal conditioning, R-peak detection, and physiological parameter extraction.
- Performed Pan–Tompkins-based ECG filtering, R-peak detection, peak correction, and signal quality assessment to improve measurement reliability.
- Computed real-time **Heart Rate (HR)**, **SDNN**, and **RMSSD** using separate fast (8 s) and long-term (5 min) processing windows.
- Logged processed ECG signals and extracted parameters to CSV while simultaneously displaying a live waveform with detected **R-peaks** and **T-waves**.
- Built an asynchronous BLE data acquisition pipeline with automatic packet synchronization, frame validation, and reconnection support for continuous monitoring.
- <img width="1495" height="756" alt="image" src="https://github.com/user-attachments/assets/289fc81d-e695-424e-9248-0da2ec7a4994" />
