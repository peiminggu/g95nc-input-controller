# g95nc-input-controller

Control Samsung G95NC input source with a Raspberry Pi.

## Setup documentation

1. [Step 1 — Set up the Pi and verify monitor control](doc/setup-guide.md)
2. [Step 2 — Setup Keys: detailed GPIO wiring and diagrams](doc/setup-keys.md)
3. [Step 3 — Install the key controller and start it automatically on the Pi](doc/setup-controller.md)
4. [Step 4 — Add an optional 128×32 OLED source display](doc/setup-oled.md)
5. [Step 5 — Print and assemble the enclosure: separate or integrated Pi Zero](doc/setup-enclosure.md)

`controller.py` monitors the GPIO keys and switches inputs through `ddcutil`.
Copy `config.example.json` to `config.json`, assign the verified input values
from Step 1, and follow Step 3 for testing and boot service installation.

## License

This project is licensed under the [MIT License](https://opensource.org/license/mit).
