#!/usr/bin/env python3
"""
Smart light switch controller for SmartLife/Tuya devices.

Usage:
  lights.py refresh         — fetch devices from cloud and update local cache
  lights.py status          — show status of all switches
  lights.py <id> on|off|toggle|status
  lights.py all on|off

<id> can be a number, device name, or partial name match.
Run 'refresh' first, or whenever you add/re-pair a device.
"""

import json
import os
import sys
from pathlib import Path
import tinytuya

# --- config -------------------------------------------------------------------

_base = Path(__file__).parent

_env_path = _base / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

TUYA_REGION = os.environ["TUYA_REGION"]
TUYA_KEY    = os.environ["TUYA_KEY"]
TUYA_SECRET = os.environ["TUYA_SECRET"]

CACHE_FILE  = _base / "devices.json"

# --- cloud & cache ------------------------------------------------------------

_cloud = None

def get_cloud():
    global _cloud
    if _cloud is None:
        _cloud = tinytuya.Cloud(apiRegion=TUYA_REGION, apiKey=TUYA_KEY, apiSecret=TUYA_SECRET)
    return _cloud


def cmd_refresh():
    print("Fetching devices from Tuya cloud...")
    cloud = get_cloud()

    # Pull device list + local keys
    cloud_devices = cloud.getdevices(verbose=True).get("result", [])

    # Pull local IPs via UDP broadcast
    print("Scanning local network for device IPs...")
    local_scan = tinytuya.deviceScan(verbose=False, maxretry=20, color=False)
    ip_by_id = {info["gwId"]: {"ip": ip, "version": float(info.get("version", 3.3))}
                for ip, info in local_scan.items()}

    # Only keep switch devices (category "cz") that are on this network
    import requests
    my_ip = requests.get("https://api.ipify.org").text.strip()

    switches = []
    for d in cloud_devices:
        if d.get("category") != "cz":
            continue
        if d.get("ip") and d["ip"] != my_ip:
            print(f"  skipping {d['name']!r} — on a different network ({d['ip']})")
            continue
        local = ip_by_id.get(d["id"], {})
        switches.append({
            "name":      d["name"],
            "id":        d["id"],
            "local_key": d["local_key"],
            "ip":        local.get("ip"),
            "version":   local.get("version", 3.3),
            "online":    d.get("online", False),
        })

    # Assign stable numbers sorted by name
    switches.sort(key=lambda d: d["name"].lower())
    numbered = {i + 1: s for i, s in enumerate(switches)}

    CACHE_FILE.write_text(json.dumps(numbered, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(numbered)} switch(es) to {CACHE_FILE.name}:")
    for num, dev in numbered.items():
        method = "local" if dev["ip"] else "cloud"
        print(f"  [{num}] {dev['name']:<24} ({method}, v{dev['version']})")


def load_devices() -> dict:
    if not CACHE_FILE.exists():
        print("No device cache found. Run:  lights.py refresh")
        sys.exit(1)
    raw = json.loads(CACHE_FILE.read_text())
    return {int(k): v for k, v in raw.items()}

# --- control ------------------------------------------------------------------

def get_status(dev):
    if dev["ip"]:
        d = tinytuya.OutletDevice(dev_id=dev["id"], address=dev["ip"],
                                  local_key=dev["local_key"], version=dev["version"])
        d.set_socketTimeout(5)
        result = d.status()
        if result and "dps" in result:
            return result["dps"].get("1")
    result = get_cloud().getstatus(dev["id"])
    for item in (result or {}).get("result", []):
        if item["code"] == "switch_1":
            return item["value"]
    return None


def set_switch(dev, state: bool):
    if dev["ip"]:
        d = tinytuya.OutletDevice(dev_id=dev["id"], address=dev["ip"],
                                  local_key=dev["local_key"], version=dev["version"])
        d.set_socketTimeout(5)
        result = d.set_value("1", state)
        if result and "Error" not in str(result):
            return True
    result = get_cloud().sendcommand(dev["id"], [{"code": "switch_1", "value": state}])
    return bool(result) and result.get("success", False)

# --- output -------------------------------------------------------------------

def fmt_status(state):
    if state is True:
        return "\033[32mON \033[0m"
    if state is False:
        return "\033[31mOFF\033[0m"
    return "\033[33m???\033[0m"


def cmd_status(devices, dev_ids):
    for num in dev_ids:
        dev = devices[num]
        state = get_status(dev)
        method = "local" if dev["ip"] else "cloud"
        print(f"  [{num}] {fmt_status(state)}  {dev['name']:<24} ({method})")


def cmd_set(devices, dev_ids, state: bool):
    word = "ON" if state else "OFF"
    for num in dev_ids:
        dev = devices[num]
        ok = set_switch(dev, state)
        mark = "ok" if ok else "FAILED"
        print(f"  [{num}] {word}  {dev['name']}  — {mark}")


def cmd_toggle(devices, num):
    dev = devices[num]
    current = get_status(dev)
    if current is None:
        print(f"  [{num}] Could not read status for {dev['name']}")
        return
    set_switch(dev, not current)
    word = "ON" if not current else "OFF"
    print(f"  [{num}] toggled -> {word}  {dev['name']}")


def resolve_id(devices, token):
    try:
        num = int(token)
        if num in devices:
            return num
    except ValueError:
        pass
    token_lower = token.lower()
    for num, dev in devices.items():
        if token_lower in dev["name"].lower():
            return num
    return None

# --- main ---------------------------------------------------------------------

def usage():
    print(__doc__)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        usage()

    if args[0] == "refresh":
        cmd_refresh()
        return

    devices = load_devices()

    if args[0] == "status":
        cmd_status(devices, sorted(devices.keys()))
        return

    if args[0] == "all":
        if len(args) < 2 or args[1] not in ("on", "off"):
            usage()
        cmd_set(devices, sorted(devices.keys()), args[1] == "on")
        return

    if len(args) < 2:
        usage()

    num = resolve_id(devices, args[0])
    if num is None:
        print(f"Unknown device: {args[0]}")
        print("Use a number or part of the device name.  Run 'status' to list devices.")
        sys.exit(1)

    action = args[1].lower()
    if action == "on":
        cmd_set(devices, [num], True)
    elif action == "off":
        cmd_set(devices, [num], False)
    elif action == "toggle":
        cmd_toggle(devices, num)
    elif action == "status":
        cmd_status(devices, [num])
    else:
        print(f"Unknown action: {action}  (use on/off/toggle/status)")
        sys.exit(1)


if __name__ == "__main__":
    main()
