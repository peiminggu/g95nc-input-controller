# g95nc-input-controller

Control Samsung G95NC input source with a Raspberry Pi.

![Front view of the G95NC input controller](doc/img/front.jpeg)

## Tested hardware

- Monitor: Samsung Odyssey Neo G9 57" (G95NC)
- Firmware: `M-C9557GGPA-1009.2`

## Setup documentation

1. [Step 1 — Set up the Pi and verify monitor control](doc/setup-guide.md)
2. [Step 2 — Setup Keys: detailed GPIO wiring and diagrams](doc/setup-keys.md)
3. [Step 3 — Install the key controller and start it automatically on the Pi](doc/setup-controller.md)
4. [Step 4 — Add an optional 128×32 OLED source display](doc/setup-oled.md)
5. [Step 5 — Print and assemble the enclosure: separate or integrated Pi Zero](doc/setup-enclosure.md)

`controller.py` monitors the GPIO keys and switches inputs through `ddcutil`.
Copy `config.example.json` to `config.json`, assign the verified input values
from Step 1, and follow Step 3 for testing and boot service installation.

## Usage precautions

Verify the GPIO pin assignments, voltage levels, and wiring before use, and
disconnect power before connecting or changing hardware. Monitor input source
values may vary by model or firmware version; follow Step 1 to verify them before
enabling automatic control.

## License

This project is licensed under the [MIT License](https://opensource.org/license/mit).
