"""
FastAPI web UI for the SmartLife/Tuya light switch controller.

Run with:
  uvicorn server:app --host 0.0.0.0 --port 8000
or:
  python3 server.py
"""

import asyncio
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import lights

BLUESOUND_URL = "http://192.168.10.130:11000"
HDMI_PLAY_URL = "Capture:hw:imxspdif,0/1/25/2?id=input2"

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


# ---------------------------------------------------------------------------
# Bluesound API
# ---------------------------------------------------------------------------

def _bs_text(root, tag):
    el = root.find(tag)
    return el.text if el is not None else None


@app.get("/api/bluesound/status")
async def bluesound_status():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Status", timeout=5)
        r.raise_for_status()
    root = ET.fromstring(r.text)
    service = _bs_text(root, "service") or ""
    input_id = _bs_text(root, "inputId") or ""
    if service == "Capture" and input_id == "input2":
        active_input = "hdmi"
    elif service == "Tidal":
        active_input = "tidal"
    else:
        active_input = "other"
    return {
        "input": active_input,
        "title": _bs_text(root, "title1"),
        "artist": _bs_text(root, "title2"),
        "state": _bs_text(root, "state"),
        "volume": _bs_text(root, "volume"),
    }


@app.post("/api/bluesound/volume/{level}")
async def bluesound_volume(level: int):
    if not 0 <= level <= 100:
        raise HTTPException(400, "level must be 0–100")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Volume", params={"level": level}, timeout=5)
        r.raise_for_status()
    return {"ok": True, "volume": level}


@app.post("/api/bluesound/play")
async def bluesound_play():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Play", timeout=5)
        r.raise_for_status()
    return {"ok": True}


@app.post("/api/bluesound/pause")
async def bluesound_pause():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Pause", timeout=5)
        r.raise_for_status()
    return {"ok": True}


@app.post("/api/bluesound/stop")
async def bluesound_stop():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Stop", timeout=5)
        r.raise_for_status()
    return {"ok": True}


@app.post("/api/bluesound/skip")
async def bluesound_skip():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Skip", timeout=5)
        r.raise_for_status()
    return {"ok": True}


@app.post("/api/bluesound/back")
async def bluesound_back():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Back", timeout=5)
        r.raise_for_status()
    return {"ok": True}


@app.post("/api/bluesound/input/hdmi")
async def bluesound_hdmi():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BLUESOUND_URL}/Play", params={"url": HDMI_PLAY_URL}, timeout=5)
        r.raise_for_status()
    return {"ok": True, "input": "hdmi"}


@app.post("/api/bluesound/input/tidal")
async def bluesound_tidal():
    async with httpx.AsyncClient() as client:
        # Browse My Mix playlists and play the first one
        r = await client.get(f"{BLUESOUND_URL}/Browse", params={
            "service": "Tidal",
            "key": "Tidal:Playlist/%2FPlaylists%3Fcategory=mymix%26service=Tidal",
        }, timeout=5)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        item = next((i for i in root.findall("item") if i.get("playURL")), None)
        if item is None:
            raise HTTPException(503, "No Tidal My Mix playlists found")
        play_url = item.get("playURL")
        await client.get(f"{BLUESOUND_URL}{play_url}", timeout=5)
    return {"ok": True, "input": "tidal"}


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
