# Electronics

All the electronics for the smart desk.

## Folders

- `schematics/` — circuit diagrams (PDF + KiCad source)
- `pcb/` — PCB design files and Gerber zips for fab
- `bom/` — parts list (CSV)
- `wiring/` — wiring diagrams, pinouts, connector maps

## Main Parts (typical)

- Microcontroller (ESP32 / Raspberry Pi)
- Motor driver (for height adjust)
- Sensors (presence, light, posture)
- Power supply (24V or 12V)
- Touch panel / display

See `bom/parts.csv` for the full list.

## Safety

- Mains voltage parts are clearly marked
- Always disconnect power before wiring
- Use the fuse rating in the BOM
