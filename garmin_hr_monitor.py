#!/usr/bin/env python3
"""
garmin_hr_monitor.py
--------------------
Listens for a Garmin Fenix (or any BLE HR broadcast) and prints:
  • Heart-rate (bpm)
  • RR-intervals (ms) – beat-to-beat timing, if broadcast
  • Sensor contact status
  • Battery level (if the device exposes it)
  • Any unknown characteristic values (hex dump)

Uses Bleak for cross-platform BLE on Linux/macOS/Windows.
On Linux the BlueZ stack talks directly to the dongle; no pairing needed
as long as the watch is in "HR Broadcast" mode.

Usage:
  python garmin_hr_monitor.py               # auto-scan and connect to first HR device
  python garmin_hr_monitor.py --scan        # list nearby BLE devices and exit
  python garmin_hr_monitor.py --addr <MAC>  # connect to a specific device
  python garmin_hr_monitor.py --timeout 60  # stop after N seconds (0 = run forever)
"""

import asyncio
import argparse
import struct
import sys
from datetime import datetime
from typing import List, Optional, Tuple

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# ── Standard BLE UUIDs ────────────────────────────────────────────────────────
HR_SERVICE_UUID            = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_CHAR_UUID   = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_SENSOR_LOC_CHAR_UUID  = "00002a38-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE_UUID       = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID    = "00002a19-0000-1000-8000-00805f9b34fb"
DEVICE_INFO_SERVICE_UUID   = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_CHAR_UUID     = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_CHAR_UUID            = "00002a24-0000-1000-8000-00805f9b34fb"

BODY_SENSOR_LOCATIONS = {
    0: "Other", 1: "Chest", 2: "Wrist", 3: "Finger",
    4: "Hand",  5: "Ear Lobe", 6: "Foot",
}

# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_hr_measurement(data: bytearray) -> dict:
    """
    Decode the Heart Rate Measurement characteristic (0x2A37).

    Flags byte (bit layout):
      bit 0 : HR value format  0=UINT8  1=UINT16
      bit 1 : Sensor Contact Detected
      bit 2 : Sensor Contact Feature Supported
      bit 3 : Energy Expended present
      bit 4 : RR-Interval(s) present
    """
    flags = data[0]
    offset = 1
    result = {}

    # Heart rate
    hr_16bit = bool(flags & 0x01)
    if hr_16bit:
        result["hr_bpm"] = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    else:
        result["hr_bpm"] = data[offset]
        offset += 1

    # Sensor contact
    contact_supported = bool(flags & 0x04)
    contact_detected  = bool(flags & 0x02)
    if contact_supported:
        result["sensor_contact"] = "detected" if contact_detected else "not detected"

    # Energy expended (kJ)
    if flags & 0x08:
        result["energy_expended_kj"] = struct.unpack_from("<H", data, offset)[0]
        offset += 2

    # RR intervals (1/1024 s units → convert to ms)
    rr_intervals = []
    if flags & 0x10:
        while offset + 1 < len(data):
            raw = struct.unpack_from("<H", data, offset)[0]
            rr_intervals.append(round(raw / 1024 * 1000, 1))
            offset += 2
    if rr_intervals:
        result["rr_intervals_ms"] = rr_intervals

    return result


# ── Display ───────────────────────────────────────────────────────────────────

def print_hr(data: dict) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hr = data.get("hr_bpm", "?")
    contact = data.get("sensor_contact", "")
    rr = data.get("rr_intervals_ms", [])
    energy = data.get("energy_expended_kj")

    parts = [f"[{ts}]  HR: {hr:>3} bpm"]
    if contact:
        parts.append(f"contact={contact}")
    if rr:
        rr_str = ", ".join(f"{v}" for v in rr)
        parts.append(f"RR=[{rr_str}] ms")
    if energy is not None:
        parts.append(f"energy={energy} kJ")
    print("  ".join(parts))


# ── Scanning helpers ──────────────────────────────────────────────────────────

def has_hr_service(adv: AdvertisementData) -> bool:
    uuids = [u.lower() for u in adv.service_uuids]
    return HR_SERVICE_UUID in uuids


async def scan_devices(duration: float = 8.0) -> List[Tuple[BLEDevice, AdvertisementData]]:
    print(f"Scanning for BLE devices ({duration}s) …\n")
    found = []

    def callback(device: BLEDevice, adv: AdvertisementData):
        found.append((device, adv))

    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(duration)

    # Deduplicate by address
    seen = {}
    for dev, adv in found:
        seen[dev.address] = (dev, adv)
    return list(seen.values())


async def find_hr_device(timeout: float = 15.0) -> Optional[BLEDevice]:
    """Return the first device advertising the HR service."""
    print(f"Scanning for Heart Rate device (up to {timeout}s) …")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: has_hr_service(adv),
        timeout=timeout,
    )
    return device


# ── Device info ───────────────────────────────────────────────────────────────

async def read_device_info(client: BleakClient) -> None:
    print("\n── Device info ──────────────────────────────")

    async def try_read(uuid: str, label: str) -> None:
        try:
            raw = await client.read_gatt_char(uuid)
            print(f"  {label}: {raw.decode('utf-8', errors='replace').strip()}")
        except Exception:
            pass

    await try_read(MANUFACTURER_CHAR_UUID, "Manufacturer")
    await try_read(MODEL_CHAR_UUID,        "Model")

    try:
        loc_raw = await client.read_gatt_char(BODY_SENSOR_LOC_CHAR_UUID)
        loc = BODY_SENSOR_LOCATIONS.get(loc_raw[0], f"unknown ({loc_raw[0]})")
        print(f"  Body sensor location: {loc}")
    except Exception:
        pass

    try:
        bat = await client.read_gatt_char(BATTERY_LEVEL_CHAR_UUID)
        print(f"  Battery: {bat[0]}%")
    except Exception:
        pass

    print("─────────────────────────────────────────────\n")


async def list_services(client: BleakClient) -> None:
    """Dump all services and characteristics for debugging."""
    print("\n── All GATT services / characteristics ──────")
    for svc in client.services:
        print(f"\n  Service: {svc.uuid}  ({svc.description})")
        for char in svc.characteristics:
            props = ", ".join(char.properties)
            print(f"    Char: {char.uuid}  [{props}]  ({char.description})")
            if "read" in char.properties:
                try:
                    val = await client.read_gatt_char(char.uuid)
                    # Try UTF-8 first, fall back to hex
                    try:
                        decoded = val.decode("utf-8").strip()
                        if decoded.isprintable():
                            print(f"           Value: {decoded!r}")
                        else:
                            raise ValueError
                    except (UnicodeDecodeError, ValueError):
                        print(f"           Value: {val.hex(' ')}")
                except Exception as exc:
                    print(f"           Value: <read error: {exc}>")
    print("─────────────────────────────────────────────\n")


# ── Main connection loop ──────────────────────────────────────────────────────

async def run(address: Optional[str], stop_after: float, dump_services: bool) -> None:
    if address:
        print(f"Connecting to {address} …")
        device = address          # bleak accepts a MAC string directly
    else:
        device = await find_hr_device()
        if device is None:
            print("No Heart Rate device found. Is HR Broadcast enabled on the watch?")
            sys.exit(1)
        print(f"Found: {device.name}  ({device.address})")

    async with BleakClient(device) as client:
        print(f"Connected  ✓  (MTU={client.mtu_size})\n")

        await read_device_info(client)
        if dump_services:
            await list_services(client)

        print("Listening for HR measurements … (Ctrl-C to stop)\n")

        stop_event = asyncio.Event()

        def hr_callback(sender, data: bytearray):
            try:
                parsed = parse_hr_measurement(data)
                print_hr(parsed)
            except Exception as exc:
                print(f"  [parse error] {exc}  raw={data.hex(' ')}")

        await client.start_notify(HR_MEASUREMENT_CHAR_UUID, hr_callback)

        if stop_after > 0:
            await asyncio.sleep(stop_after)
        else:
            await stop_event.wait()   # wait forever until Ctrl-C

        await client.stop_notify(HR_MEASUREMENT_CHAR_UUID)


# ── CLI ───────────────────────────────────────────────────────────────────────

async def cmd_scan(_args) -> None:
    devices = await scan_devices()
    if not devices:
        print("No devices found.")
        return
    print(f"{'ADDRESS':<20}  {'RSSI':>5}  {'NAME':<30}  HR?")
    print("-" * 70)
    for dev, adv in sorted(devices, key=lambda x: -(x[1].rssi or -999)):
        hr_flag = "✓" if has_hr_service(adv) else ""
        name = dev.name or adv.local_name or "(unknown)"
        rssi = adv.rssi if adv.rssi else "?"
        print(f"{dev.address:<20}  {str(rssi):>5}  {name:<30}  {hr_flag}")


def main():
    parser = argparse.ArgumentParser(
        description="Garmin Fenix BLE Heart Rate Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # scan subcommand
    sub.add_parser("scan", help="List nearby BLE devices and exit")

    # monitor subcommand (default)
    mon = sub.add_parser("monitor", help="Connect and stream HR data (default)")
    mon.add_argument("--addr", metavar="MAC",
                     help="Bluetooth address of the device (skip auto-scan)")
    mon.add_argument("--timeout", type=float, default=0,
                     help="Stop after N seconds (default: 0 = run forever)")
    mon.add_argument("--dump-services", action="store_true",
                     help="Dump all GATT services and read their values once")

    args = parser.parse_args()

    # Default to monitor if no subcommand given
    if args.command is None:
        args.command = "monitor"
        args.addr = None
        args.timeout = 0
        args.dump_services = False

    if args.command == "scan":
        asyncio.run(cmd_scan(args))
    else:
        try:
            asyncio.run(run(
                address=args.addr,
                stop_after=args.timeout,
                dump_services=args.dump_services,
            ))
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
