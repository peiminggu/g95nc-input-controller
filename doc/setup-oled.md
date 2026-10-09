# Step 4 — Add a 128×32 OLED source display

This optional display works with the Pi Zero W and the buttons from [Step 2](setup-keys.md). Install the controller using [Step 3](setup-controller.md) first. Use a **128×32 SSD1306 I2C module compatible with 3.3 V power and logic**, with VCC, GND, SDA and SCL connections. SPI modules and other display controllers need different wiring and code.

## 1. Wire the OLED

Shut down with `sudo poweroff`, wait for shutdown, and disconnect power and HDMI before wiring. Identify the module's printed pin labels; their order varies between modules. Use a soldered GPIO header and insulated connections.

| OLED label | Pi physical header pin | Function |
| --- | --- | --- |
| VCC | 1 | 3.3 V |
| GND | 6 | Ground |
| SDA | 3 | GPIO2, I2C data |
| SCL | 5 | GPIO3, I2C clock |

The buttons stay on GPIO17, 27, 22 and 23. Their ground can remain on pin 14; all Pi ground pins are connected. Do not connect OLED signals to 5 V. Verify your module supports 3.3 V supply before using this wiring.

## 2. Enable GPIO I2C and install the library

Reconnect and run these commands **on the Pi**:

```bash
sudo raspi-config
```

Select **Interface Options → I2C → Enable**, then exit. Install the packaged OLED library and reboot:

```bash
sudo apt update
sudo apt install -y python3-luma.oled python3-pil i2c-tools
sudo reboot
```

No pip or virtual environment is needed. After reconnecting, stop the controller before testing:

```bash
sudo systemctl stop g95nc-controller.service
ls -l /dev/i2c-1
sudo i2cdetect -y 1
```

Scan only the GPIO bus `1` used by this OLED, not the monitor's HDMI DDC bus. The OLED normally appears at `3c`; some modules use `3d`. If absent, power off and check wiring, address selection, and module compatibility.

## 3. Enable the OLED in configuration

Update your checkout's `config.json` for a foreground test. Here is a complete example:

```json
{
  "display": 1,
  "bounce_time": 0.05,
  "command_timeout": 15,
  "oled_enabled": true,
  "oled_address": "0x3c",
  "keys": [
    {"name": "HDMI 1", "gpio": 17, "input": "0x11"},
    {"name": "HDMI 2", "gpio": 27, "input": "0x12"},
    {"name": "DisplayPort", "gpio": 22, "input": "0x0f"},
    {"name": "HDMI 3", "gpio": 23, "input": "0x32"}
  ]
}
```

Keep your verified monitor number and input codes from Step 1; these codes are examples and must match your monitor. Set `oled_address` to the address found above. `oled_enabled` defaults to `false` when absent, so existing configurations work without the OLED library. An enabled OLED reserves GPIO2 and GPIO3.

Use the exact key names `HDMI 1`, `HDMI 2`, `HDMI 3`, and `DisplayPort` to label detected sources. The older name `DP` also displays as `DisplayPort`. The controller maps the monitor's reported input value to the enabled keys' configured input codes; disabled keys, unmatched codes, or other names display `Ready`. Keep all four inputs configured to identify all four sources.

## 4. Test the display

From your updated checkout:

```bash
cd ~/g95nc-input-controller
python3 controller.py --config config.json --check-config
sudo ddcutil --display 1 --terse getvcp 60
sudo python3 controller.py --config config.json
```

Replace `1` with your configured display number in the manual query. A typical response is `VCP 60 SNC x11`, which identifies the current source code.

Once the GPIO keys are open and the controller is ready, the OLED initially shows `Ready`, then the detected source: `HDMI 1`, `HDMI 2`, `HDMI 3`, or `DisplayPort`. Starting the controller does not switch the monitor. It reads the actual source after each switching attempt and every five seconds while idle, so monitor-menu changes can also appear. A read can take up to `command_timeout` seconds and runs in the same worker as switching; a pending key waits for that read to finish.

Text is enlarged automatically and centered within a 120×24 pixel area, leaving a four-pixel margin. Longer labels such as `DisplayPort` shrink enough to remain fully visible. No extra font package or configuration change is needed.

If the monitor is off, a read fails, or the source is unknown, the OLED shows `Ready`. This means the button controller is ready, not that the source has been confirmed. A successful switching command alone does not change the displayed label; the monitor must report the source. Test querying while another input is active: inactive-input DDC support depends on the monitor.

Press each button and check the display. Stop with Ctrl+C; the OLED is cleared on exit. `--dry-run` only tests button logging and does not open the OLED or query DDC. `--check-config` validates without hardware access.

## 5. Update the installed boot service

After the foreground test, copy the updated code and tested configuration:

```bash
sudo install -m 644 controller.py /opt/g95nc-input-controller/controller.py
sudo install -m 644 config.json /etc/g95nc-controller/config.json
sudo usermod -aG gpio,i2c g95nc-controller
sudo systemctl restart g95nc-controller.service
journalctl -u g95nc-controller.service -n 30 --no-pager
```

The Step 3 service already uses system Python and the `i2c` group. Confirm `/dev/i2c-1` permits that group access. Reboot and check that the label appears without logging in:

```bash
sudo reboot
```

To disable the OLED, set `"oled_enabled": false` in `/etc/g95nc-controller/config.json` and restart the service. Editing only the checkout configuration does not affect the installed service. Stop and disconnect power before removing the OLED.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Blank OLED | Enable the flag, confirm address and SSD1306 128×32 hardware, and inspect the journal for OLED warnings. |
| Works as root but not as service | Check `/dev/i2c-1` group permissions and service membership in `i2c`. Restart after membership changes. |
| Always `Ready` | Run the manual DDC query, confirm display number, configured input codes and exact source names. Test from an inactive Pi HDMI input. |
| Wrong source label | Correct the input codes against physically verified ports; labels come from your configuration. |
| OLED fails during use | The controller logs the failure and disables OLED updates for that run. Fix the connection and restart; buttons continue working. |
| Slow button response | DDC reads and writes run sequentially. Check DDC response times and `command_timeout`. |

## References

- [Luma OLED documentation](https://luma-oled.readthedocs.io/en/latest/)
- [Packaged OLED library for Bookworm](https://packages.debian.org/bookworm/python3-luma.oled)
- [ddcutil current-value query and terse output](https://www.ddcutil.com/command_getvcp/)
- [Raspberry Pi GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
