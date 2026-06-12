# Garmin Fenix BLE Heart Rate Monitor

Stream live heart rate data from a Garmin Fenix (or any BLE HR device) to your terminal on Ubuntu.

## Quickstart

**1. Enable HR Broadcast on the watch**

`Settings → Sensors & Accessories → Wrist Heart Rate → Broadcast Heart Rate → On`

**2. Install system dependencies**

```bash
sudo apt install bluez
sudo systemctl start bluetooth
```

**3. Clone / download, then build the venv**

```bash
make
```

**4. Verify your setup**

```bash
make check-sys
```

**5. Stream HR data**

```bash
make run
```

That's it. The script auto-discovers the nearest device advertising the Heart Rate service and starts printing.

---

## Make targets

| Target | Description |
|---|---|
| `make` / `make install` | Create `.venv` and install `bleak` |
| `make run` | Auto-discover and stream HR |
| `make scan` | List all nearby BLE devices |
| `make run-addr ADDR=<MAC>` | Connect to a specific device by MAC |
| `make dump [ADDR=<MAC>]` | Connect and dump all GATT services/values |
| `make check-sys` | Verify BlueZ, D-Bus, and HCI adapter |
| `make clean` | Remove `.venv` |

Stop streaming at any time with `Ctrl-C`.

---

## Sample output

```
── Device info ──────────────────────────────
  Manufacturer: Garmin
  Model: fenix 7
  Body sensor location: Wrist
  Battery: 72%
─────────────────────────────────────────────

Listening for HR measurements … (Ctrl-C to stop)

[14:32:01.042]  HR:  78 bpm  contact=detected  RR=[776.4, 781.2] ms
[14:32:02.057]  HR:  79 bpm  contact=detected  RR=[758.8] ms
[14:32:03.061]  HR:  77 bpm  contact=detected  RR=[789.1, 801.3] ms
```

Each line shows:
- **Timestamp** (HH:MM:SS.mmm)
- **Heart rate** in bpm
- **Sensor contact** status (detected / not detected)
- **RR intervals** in ms — beat-to-beat timing, present if the watch broadcasts them (useful for HRV)
- **Energy expended** in kJ, if available

---

## Direct script usage

```bash
# Auto-discover and stream
.venv/bin/python garmin_hr_monitor.py monitor

# Scan for nearby BLE devices
.venv/bin/python garmin_hr_monitor.py scan

# Connect to a specific MAC
.venv/bin/python garmin_hr_monitor.py monitor --addr C0:FF:EE:00:11:22

# Stop after 60 seconds
.venv/bin/python garmin_hr_monitor.py monitor --timeout 60

# Dump all GATT services (explore what else the watch exposes)
.venv/bin/python garmin_hr_monitor.py monitor --dump-services
```

---

## Requirements

- Python 3.8+
- Ubuntu (or any Linux with BlueZ 5.x)
- A Bluetooth dongle or built-in adapter (HCI device)
- [`bleak`](https://github.com/hbldh/bleak) — installed automatically by `make`

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `org.bluez.Error.NotReady` | `sudo systemctl start bluetooth && sudo hciconfig hci0 up` |
| Device not found | Confirm HR Broadcast is on; run `make scan` to check it appears |
| No RR intervals | Some Garmin models only broadcast RR in certain activity modes |
| Permission denied on `/dev/hci*` | `sudo usermod -aG bluetooth $USER` then log out and back in |
| `bleak` install fails | Ensure `python3-venv` is installed: `sudo apt install python3-venv` |
