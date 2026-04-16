# lightson

Local control for SmartLife/Tuya smart switches via the Tuya local protocol.

## Tuya IoT Platform registration

To get API credentials you need a free developer account:

1. Go to [iot.tuya.com](https://iot.tuya.com) and register
2. Create a new **Cloud Project** — choose "Smart Home" as the industry and "Smart Home" as the development method
3. On the project's **Overview** tab, copy the **Access ID** and **Access Secret**
4. Go to the **Devices** tab → **Link Tuya App Account** → scan the QR code with the SmartLife app
   (Profile tab → QR scanner icon in the top right corner)

Your devices will now appear in the project and their local keys become accessible via the API.

## Setup

1. Copy `.env.example` to `.env` and fill in your Tuya IoT Platform credentials:
   ```
   TUYA_REGION=eu
   TUYA_KEY=your_access_id
   TUYA_SECRET=your_access_secret
   ```
   Credentials are found at [iot.tuya.com](https://iot.tuya.com) → your project → Overview tab.

2. Install dependencies:
   ```
   uv pip install tinytuya requests
   ```

3. Fetch devices:
   ```
   python3 lights.py refresh
   ```

## Usage

```
python3 lights.py status          # show all devices and their current state
python3 lights.py all on          # turn everything on
python3 lights.py all off         # turn everything off
python3 lights.py <id> on|off|toggle|status
```

`<id>` can be a number (from `status`) or a partial device name:
```
python3 lights.py 1 on
python3 lights.py kinti off
python3 lights.py kanape toggle
```

## Updating devices

Re-run `refresh` whenever you add, remove, or re-pair a device:
```
python3 lights.py refresh
```

Device info (IDs, local keys, IPs) is cached in `devices.json`. Commands use direct
local network control — no cloud round-trip required.
