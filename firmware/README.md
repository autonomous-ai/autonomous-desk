# Firmware

Code that runs on the desk's microcontroller.

## Target

- ESP32-S3 (default)
- Build with PlatformIO or Arduino IDE

## Folders (add as you go)

- `src/` — main code
- `lib/` — libraries
- `include/` — headers
- `platformio.ini` — PlatformIO config

## Build

```
pio run
pio run -t upload
```

## Flash by USB

1. Plug in the desk controller via USB-C
2. `pio run -t upload`
3. Open serial monitor: `pio device monitor -b 115200`

## OTA Update

Once connected to Wi-Fi, you can update over the air. See `docs/ota.md`.
