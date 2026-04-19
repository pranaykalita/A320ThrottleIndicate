# A32NX Throttle Overlay

A lightweight transparent HUD that shows your throttle position with detent markers in real time — built for the **FlyByWire A320neo (A32NX)** on Microsoft Flight Simulator 2020/2024.

<!-- BEGIN LATEST DOWNLOAD BUTTON -->
[![Download Addon](https://custom-icon-badges.demolab.com/badge/-Download-blue?style=for-the-badge&logo=download&logoColor=white "Download zip")](https://github.com/pranaykalita/A320ThrottleIndicate/archive/refs/heads/main.zip)
<!-- END LATEST DOWNLOAD BUTTON -->

---

## Why this exists

My throttle hardware is a **single-axis slider** — no detent notches, no haptic feedback. Every time I wanted to know if I was at CLB, FLX, or TOGA I had to look away from the PFD and check the EFB/flypad. This overlay puts that information on screen permanently, always on top, always readable at a glance.

---

## What it does

- Shows a vertical bar that fills as throttle increases
- Detent labels (TOGA / FLX / CLB / IDLE) appear at the correct positions on the bar
- Automatically switches to **Reverse Thrust** UI when reverse is engaged in-sim
- Reverse detents (REV IDLE / REV FULL) replace forward ones during reverse
- All positions are read live from **SimConnect** — no guesswork, no polling the joystick axis for thrust state
- Transparent, frameless window — drag anywhere, right-click for settings

---

![showcase1](/img/workSS%20(1).png)

![showcase2](/img/workSS%20(2).png)

![showcase3](/img/workSS%20(3).png)

![showcase4](/img/workSS%20(4).png)

![showcase5](/img/workSS%20(5).png)

![showcase6](/img/workSS%20(6).png)

## Tested with

| Item | Detail |
|------|--------|
| Aircraft | FlyByWire A320neo (A32NX dev/stable) |
| Simulator | MSFS 2020 / MSFS 2024 |
| Throttle hardware | Single-axis USB slider |
| OS | Windows 10/11 |

> This tool is coded specifically around the A32NX throttle lever SimConnect values:
> - Normal thrust: `0.0` to `+78.655`
> - Reverse thrust: `−1.0` to `−36.868`
>
> Other aircraft may use different ranges. The detent positions should be matched to your FlyByWire EFB (flypad) throttle calibration values.

---

## Setup

### Requirements

- Python 3.10+
- Microsoft Flight Simulator 2020 or 2024

### Install

```
pip install -r requirements.txt
```

Or just double-click **`run.bat`** — it checks and installs dependencies automatically.

---

## Usage

1. **Start MSFS first** and load into a flight
2. Double-click `run.bat`
3. The overlay waits up to 10 seconds for SimConnect — if not found it exits with an error
4. Once connected, the overlay window appears

### Controls

| Action | Effect |
|--------|--------|
| Drag | Move overlay anywhere on screen |
| Right-click | Open Settings |
| ✕ button | Close overlay |

---

## Settings

Right-click the overlay to open Settings.

### Axis Ranges

These should match your **FlyByWire EFB → Throttle Calibration** values — the min/max axis values for each detent. Add a small buffer (~0.02) on each side so the label triggers reliably.

Example (PC Flight Simulator hardware, from testing):

| Detent | Min | Max |
|--------|-----|-----|
| TOGA | −1.00 | −0.95 |
| FLX | −0.85 | −0.75 |
| CLB | −0.55 | −0.45 |
| IDLE | −0.05 | +0.05 |
| REV_IDLE | +0.75 | +0.85 |
| REV_FULL | −0.95 | −1.00 |

> Match these to your flypad calibration screen values, then add ±0.02 buffer on each side.

### Reverse Button Bind

Click **BIND** then press the button on your controller that is bound to **"Toggle Throttle Reverse Thrust"** in MSFS. The app uses this only for console logging — the actual reverse detection is always from SimConnect.

---

## Console output

On launch the console prints your current config:

```
=======================================================
  A32NX Throttle Overlay
=======================================================
  Controller   : PC Flight Simulator
  Axis index   : 2
  Rev button   : Button 4
  Cal file     : C:\...\throttle_range_cal.json
-------------------------------------------------------
  Detent axis ranges (joystick):
    TOGA       [-1.0, -0.95]
    FLX        [-0.85, -0.75]
    CLB        [-0.55, -0.45]
    IDLE       [-0.05, 0.05]
    REV_IDLE   [0.75, 0.85]
    REV_FULL   [-0.95, -1.0]
=======================================================
[SC] Waiting for SimConnect (timeout 10s)...
[SC] Connected to MSFS
```

Mode switches are logged when they happen:
```
[SC] Mode → REVERSE  lever=-5.231
[SC] Mode → NORMAL   lever=42.100
[BTN] Button 4 pressed — SC lever=-5.231  mode=reverse
```

---

## Files

| File | Purpose |
|------|---------|
| `Thrt_indic.py` | Main application |
| `throttle_range_cal.json` | Saved calibration (auto-created on first save) |
| `run.bat` | Launcher — checks deps, warns to start sim first |

---

## Troubleshooting

**"Could not connect to SimConnect after 10s"**
→ MSFS is not running, or you haven't loaded into a flight yet. Start the sim, load a flight, then run the overlay.

**Bar doesn't move / stuck at bottom**
→ Check axis index (`AXIS_ENG = 2` in the script). Use `simconnect_explorer.py` to verify `GENERAL_ENG_THROTTLE_LEVER_POSITION:1` is returning values.

**Detent labels wrong / not lighting up**
→ Open Settings and re-enter your flypad calibration values with a small buffer added.

**Overlay flips back to normal during reverse**
→ The dead-zone threshold is `SC_REV_THRESHOLD = -1.0` — if your reverse starts shallower, lower this value slightly in the script.

---

## License

MIT — free to use, modify, share.
