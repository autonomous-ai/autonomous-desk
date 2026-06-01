# SD5 Keypad PCB

Keypad PCB for the Smart Desk 5. ESP32-S3 based with capacitive touch, RGB LEDs, and a small IPS display.

## Layout

```
source/          Altium Designer project files
fabrication/
  gerber/        Gerber files for PCB fabrication
  drill/         Drill files
  drc/           Design rule check report
bom/             Bill of materials + pick-and-place CSV
3d/              STEP model of assembled PCB
docs/            Schematic PDF
```

## Key Components

| Ref | Part | Description |
|-----|------|-------------|
| IC1 | ESP32-S3-WROOM-1 | Main MCU — Wi-Fi + BT |
| U2 | MPR121QR2 | 12-ch capacitive touch controller |
| U1 | LM1117-3.3V | 3.3V LDO regulator, 800mA |
| LCD1 | LCD-N114-8P | 1.14" IPS display, 8-pin FFC |
| LED1–6 | SK6812MINI-EA | Addressable RGB LEDs |
| D1, D2 | 1N5819 | Schottky diodes |
| T1 | SMBJ5.0A | TVS diode (input protection) |
| Q1, Q2 | S8050 | NPN transistors |
| Q5 | 2SA1015 | PNP transistor |

Full BOM with LCSC part numbers: [`bom/BOM_SD5_Keypad.csv`](bom/BOM_SD5_Keypad.csv)

## Touch Pads

6 capacitive pads on the bottom layer driven by MPR121: **UP, DN, 1, 2, 3, M**

## Fabrication

Send the contents of `fabrication/gerber/` and `fabrication/drill/` to your PCB fab (JLCPCB, PCBWay, etc.). Use `bom/Pick_Place_PCB_SD5_Keypad_v1.csv` for SMT assembly.
