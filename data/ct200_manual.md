# CardioTrack CT-200 Home Blood Pressure Monitor — Technical & User Manual

<!-- TODO: confirm with regulatory -->

## 1. Device Overview

The CardioTrack CT-200 is an oscillometric, upper-arm blood pressure monitor intended for home use by adult users. It measures systolic pressure, diastolic pressure, and pulse rate, and stores up to 200 readings across two user profiles.

### 1.1 Intended Use

The CT-200 is intended to non-invasively measure blood pressure and pulse rate in adults with an arm circumference of 22–42 cm. It is not intended for use on neonates, infants, or pregnant users, and is not a diagnostic device — readings should be interpreted by a qualified clinician.

### 1.2 Indications and Contraindications

The device should not be used on the arm ipsilateral to a mastectomy, on limbs with an active intravenous line, or on users with severe arrhythmia without clinician guidance, since oscillometric measurement can be unreliable in these cases.

## 2. Physical and Electrical Specifications

### 2.1 General Specifications

| Parameter | Value |
|---|---|
| Measurement method | Oscillometric |
| Pressure range | 0–299 mmHg |
| Pulse range | 40–199 bpm |
| Accuracy (pressure) | ±3 mmHg |
| Accuracy (pulse) | ±5% |
| Power source | 4x AA batteries or 6V DC adapter |
| Display | Backlit LCD |

#### 2.1.1.1 Battery Life Under Typical Use

Under typical use (three measurements per day), four AA alkaline batteries provide approximately 300 measurement cycles before requiring replacement. The device displays a low‑battery icon once remaining capacity falls below 15%.

### 2.2 Cuff Specifications

The standard cuff supplied with the CT‑200 fits arm circumferences of 22–32 cm. A separate large cuff (part number CT200‑LC) is available for 32–42 cm and must be ordered separately; using the standard cuff outside its rated range will produce inaccurate readings.

## 3. Device Operation

### 3.1 Powering On and Profile Selection

Press and hold the power button for one second to power on the device. Use the profile button to select User 1 or User 2 before beginning a measurement; readings are stored against whichever profile is active at the time of measurement.

#### 3.2 Cuff Inflation Sequence

On starting a measurement, the device inflates the cuff to an initial target of 180 mmHg. If the user's pulse is not detected by 180 mmHg, the device inflates in 40 mmHg increments up to a maximum of 299 mmHg before aborting with an error. Deflation occurs in controlled steps of approximately 3 mmHg to capture oscillometric pulse data.

### 3.4 Auto Shutoff

To conserve battery, the CT‑200 automatically powers off after 60 seconds of inactivity on the home screen, and after 3 minutes of inactivity if a measurement screen is left open without starting a reading.

### 3.3 Result Display and Classification

After a completed measurement, the device displays systolic pressure, diastolic pressure, and pulse rate simultaneously, along with a classification indicator (see 2.1, 4.3 for related specifications and alarm thresholds) based on the most recent joint clinical guidance available at time of manufacture.

1. Normal: systolic < 120 and diastolic < 80
2. Elevated: systolic 120–129 and diastolic < 80
3. Hypertension Stage 1: systolic 130–139 or diastolic 80–89
4. Hypertension Stage 2: systolic ≥ 140 or diastolic ≥ 90
5. Hypertensive Crisis: systolic > 180 or diastolic > 120 — device recommends seeking immediate medical attention

## 4. Alarms and Safety Behavior

### 4.1 Overpressure Protection

If cuff pressure exceeds 299 mmHg at any point, or exceeds 300 mmHg for longer than 3 seconds due to sensor fault, the device immediately triggers an emergency deflation valve, halting inflation and venting the cuff within 2 seconds, independent of the main firmware control loop.

### 4.2 Error Codes

| Code | Meaning | Device Behavior |
|---|---|---|
| E1 | Cuff not connected or leak detected | Aborts measurement, displays E1 |
| E2 | Motion artifact detected during measurement | Aborts measurement, displays E2, prompts retry |
| E3 | Overpressure condition | Auto-deflates within 2 seconds, displays E3 |
| E4 | Low battery during measurement | Aborts measurement, displays E4 |
| E5 | Internal sensor fault | Device disables measurement function, displays E5 until serviced |

### 4.3 Alarm Thresholds

The device does not sound an audible alarm for elevated readings by default; audible alarms are limited to the E1–E5 error conditions above and are user‑configurable in the settings menu, except for E3 (overpressure), which cannot be silenced for safety reasons.

## 5. Data Management

### 5.1 Local Storage

The CT‑200 stores up to 100 readings per user profile in non‑volatile memory. When storage is full, the oldest reading for that profile is overwritten automatically; there is no user‑facing warning before this occurs.

### 5.2 Bluetooth Sync

The device can pair with the CardioTrack companion app via Bluetooth Low Energy. Readings sync automatically when the app is open and the device is within range; there is no manual "sync now" trigger in firmware version 1.x.

## 6. Maintenance and Cleaning

### 6.1 Cleaning Instructions

Wipe the device body and cuff exterior with a soft, dry cloth or one lightly dampened with water. Do not submerge the device or cuff, and do not use alcohol, solvents, or abrasive cleaners on the display.

### 6.2 Calibration

Anthropic recommends professional recalibration every 2 years or after any drop or significant impact. The device does not perform self‑calibration; there is no field calibration procedure available to end users.

## 7. Troubleshooting

### 7.1 Error Codes

If a code from Section 4.2 appears and persists after following the on‑screen retry prompt twice, users should discontinue use and contact CardioTrack support rather than attempting further self‑diagnosis, particularly for E5, which indicates an internal sensor fault.

### 7.2 Inconsistent Readings

Inconsistent readings between measurements are most commonly caused by cuff mispositioning, talking or moving during measurement, or measuring within 30 minutes of exercise, caffeine, or smoking; the manual recommends resting quietly for 5 minutes before remeasuring.

## 8. Regulatory Information

### 8.1 Classification

The CT‑200 is classified as a Class II medical device under applicable regulations for non‑invasive blood pressure monitors and has been validated against relevant clinical accuracy standards for oscillometric devices.
