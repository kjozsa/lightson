"""
FastAPI web UI for the SmartLife/Tuya light switch controller.

Run with:
  uvicorn server:app --host 0.0.0.0 --port 8000
or:
  python3 server.py
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import lights

app = FastAPI(title="LightsOn")
_pool = ThreadPoolExecutor(max_workers=8)


def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_pool, fn, *args)


def _load_devices_safe() -> dict:
    """Like lights.load_devices() but returns {} instead of sys.exit() when cache is missing."""
    if not lights.CACHE_FILE.exists():
        return {}
    return lights.load_devices()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/devices")
async def list_devices():
    """Return device list with current on/off state for each."""
    devs = await _run(_load_devices_safe)

    async def _status_entry(num, dev):
        state = await _run(lights.get_status, dev)
        return {
            "id": num,
            "name": dev["name"],
            "state": state,
            "method": "local" if dev.get("ip") else "cloud",
            "online": dev.get("online", False),
        }

    entries = await asyncio.gather(*[_status_entry(n, d) for n, d in sorted(devs.items())])
    return list(entries)


@app.post("/api/device/{device_id}/on")
async def turn_on(device_id: int):
    devs = await _run(_load_devices_safe)
    if device_id not in devs:
        raise HTTPException(404, "Device not found")
    ok = await _run(lights.set_switch, devs[device_id], True)
    return {"ok": bool(ok)}


@app.post("/api/device/{device_id}/off")
async def turn_off(device_id: int):
    devs = await _run(_load_devices_safe)
    if device_id not in devs:
        raise HTTPException(404, "Device not found")
    ok = await _run(lights.set_switch, devs[device_id], False)
    return {"ok": bool(ok)}


@app.post("/api/device/{device_id}/toggle")
async def toggle(device_id: int):
    devs = await _run(_load_devices_safe)
    if device_id not in devs:
        raise HTTPException(404, "Device not found")
    dev = devs[device_id]
    state = await _run(lights.get_status, dev)
    if state is None:
        raise HTTPException(503, "Could not read device status")
    new_state = not state
    ok = await _run(lights.set_switch, dev, new_state)
    return {"ok": bool(ok), "state": new_state}


@app.post("/api/all/{action}")
async def all_action(action: str):
    if action not in ("on", "off"):
        raise HTTPException(400, "action must be 'on' or 'off'")
    devs = await _run(_load_devices_safe)
    target = action == "on"
    results = await asyncio.gather(
        *[_run(lights.set_switch, dev, target) for dev in devs.values()],
        return_exceptions=True,
    )
    failed = sum(1 for r in results if isinstance(r, Exception) or not r)
    return {"ok": failed == 0, "failed": failed, "total": len(results)}


@app.post("/api/refresh")
async def refresh():
    """Re-scan cloud + local network and rebuild devices.json."""
    await _run(lights.cmd_refresh)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Serve UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
