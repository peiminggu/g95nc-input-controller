# Step 3 — Run the key controller automatically on the Pi

This controller uses the four physical GPIO keys from [Step 2](setup-keys.md) to send the input-source commands tested in [Step 1](setup-guide.md). Run every command below **on the Pi**, locally or over SSH. Keep the Pi's HDMI cable connected to the monitor even when another computer's input is selected.

## 1. Install the controller and dependencies

Finish the Step 1 switching tests and Step 2 wiring tests first. Stop `test_keys.py` before starting this controller; only one program should use these GPIO pins.

```bash
sudo apt update
sudo apt install -y git python3 python3-gpiozero ddcutil
```

If you have not downloaded the repository:

```bash
git clone https://github.com/peiminggu/g95nc-input-controller.git
```

Enter your existing or newly downloaded checkout:

```bash
cd ~/g95nc-input-controller
cp -n config.example.json config.json
nano config.json
```

No pip installation or virtual environment is needed; use Raspberry Pi OS's packaged GPIO Zero library and system Python.

## 2. Assign each key to a verified input

Set `display` to the G95NC display number from `sudo ddcutil detect`. Replace each `null` with the input value you physically verified in Step 1, enclosed in quotes, for example `"0x11"`. That value is an example, **not a confirmed G95NC port mapping**. Leave unused keys as `null`; at least one key must have an input assigned. The supplied example deliberately has no input codes assigned.

| Key | BCM GPIO | Physical pin | Configuration entry |
| --- | --- | --- | --- |
| Key 1 | 17 | 11 | First key's `input` |
| Key 2 | 27 | 13 | Second key's `input` |
| Key 3 | 22 | 15 | Third key's `input` |
| Key 4 | 23 | 16 | Fourth key's `input` |

All keys connect their other contact to the shared ground on physical pin 14. The script enables internal pull-ups and 50 ms debounce. GPIO values are BCM numbers. You can rename keys to the connected computers without changing the wiring.

The remaining settings are `bounce_time` (seconds of software debounce) and `command_timeout` (maximum seconds for each ddcutil invocation). Start with the defaults. JSON requires double quotes and no trailing commas or comments.

Validate your configuration without accessing GPIO or the monitor:

```bash
python3 controller.py --config config.json --check-config
```

## 3. Test key monitoring and source switching

First log commands without changing the monitor:

```bash
python3 controller.py --config config.json --dry-run
```

Press each enabled key and confirm its name and intended input code appear. Hold a key: it should cause one event, with another event after release and a new press. Stop with Ctrl+C. If GPIO access is denied, follow Step 2's GPIO permissions check before proceeding.

Now perform the real switching test:

```bash
sudo python3 controller.py --config config.json
```

Press each key and visually confirm the intended source. Test from an input other than the Pi's as well. Continue over SSH when the Pi's picture disappears. Stop with Ctrl+C before installing the service.

The script sends `ddcutil --display NUMBER setvcp 60 VALUE` for each press. It processes commands one at a time, queues up to 16 waiting presses, and logs failures or timeouts while remaining ready for later presses. Holding a key does not repeatedly switch inputs. Starting the script does not select a default input. A successful command exit is not proof of the visible source; confirm it on the monitor. If the monitor refuses DDC on its inactive HDMI input, the script cannot overcome that limitation.

## 4. Install a boot service

The service runs under a dedicated account, with GPIO and I2C device access. It needs neither an interactive login nor a network connection to monitor the keys.

Check the device permissions first:

```bash
getent group gpio
getent group i2c
ls -l /dev/gpiomem /dev/i2c-*
```

On the expected Raspberry Pi OS setup, `/dev/gpiomem` allows the `gpio` group access and the monitor's I2C adapter allows the `i2c` group read/write access. If those groups or permissions differ, resolve the permissions using Steps 1 and 2 before installing this service; do not make devices world-writable.

Create the account once (if it already exists, skip the `useradd` command):

```bash
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin g95nc-controller
sudo usermod -aG gpio,i2c g95nc-controller
```

From the repository folder, copy the application, your tested configuration, and the service definition into their installed locations:

```bash
sudo install -d -m 755 /opt/g95nc-input-controller /etc/g95nc-controller
sudo install -m 644 controller.py /opt/g95nc-input-controller/controller.py
sudo install -m 644 config.json /etc/g95nc-controller/config.json
sudo install -m 644 deploy/g95nc-controller.service /etc/systemd/system/g95nc-controller.service
sudo modprobe i2c-dev
echo i2c-dev | sudo tee /etc/modules-load.d/g95nc-i2c.conf
```

Before enabling autostart, test device access using the actual service account:

```bash
sudo -u g95nc-controller ddcutil detect
sudo -u g95nc-controller /usr/bin/python3 /opt/g95nc-input-controller/controller.py --config /etc/g95nc-controller/config.json
```

Press the keys to verify switching, then stop with Ctrl+C. If this fails while the earlier root test worked, fix device/group permissions first. The service does not use sudo or need a password.

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now g95nc-controller.service
systemctl status g95nc-controller.service --no-pager
```

An active service with a `Ready` log means it has opened the enabled keys. View live logs in another SSH session:

```bash
journalctl -u g95nc-controller.service -f
```

Ctrl+C stops the log viewer; the service keeps running. Reboot and verify that the keys work without manually starting the script:

```bash
sudo reboot
```

After reconnecting:

```bash
systemctl is-enabled g95nc-controller.service
systemctl is-active g95nc-controller.service
journalctl -u g95nc-controller.service -b --no-pager
```

The service restarts after a controller crash with a five-second delay. A monitor command failure is logged without restarting the controller. If a display is not ready just after boot, wait until it is ready and press the key again.

## 5. Change mappings, update, or stop

Edit the **installed** configuration and restart to apply changes:

```bash
sudo nano /etc/g95nc-controller/config.json
python3 /opt/g95nc-input-controller/controller.py --config /etc/g95nc-controller/config.json --check-config
sudo systemctl restart g95nc-controller.service
```

Editing `~/g95nc-input-controller/config.json` alone does not change the installed service configuration. Detect the monitor again if hardware changes; display numbering can change.

To update the script from a newer checkout, preserve your installed mappings:

```bash
cd ~/g95nc-input-controller
git pull --ff-only
sudo systemctl stop g95nc-controller.service
sudo install -m 644 controller.py /opt/g95nc-input-controller/controller.py
sudo install -m 644 deploy/g95nc-controller.service /etc/systemd/system/g95nc-controller.service
sudo systemctl daemon-reload
sudo systemctl start g95nc-controller.service
```

Stop temporarily with `sudo systemctl stop g95nc-controller.service`. Disable autostart and stop with `sudo systemctl disable --now g95nc-controller.service`. Stop the service before any foreground GPIO tests; start it again afterward.

## 6. Troubleshooting and completion

| Symptom | Check |
| --- | --- |
| Configuration invalid / service keeps restarting | Read the journal; validate the installed JSON. Assign at least one verified input code. |
| GPIO access denied | Check the `gpio` group and device permissions; verify Step 2 key detection. |
| I2C access denied | Check the detected HDMI adapter's `i2c` group permissions and service account membership. |
| Key appears but switching fails | Repeat the Step 1 command manually; check display number, input value, HDMI/DDC availability, and journal error. |
| Wrong source appears | Correct the verified input mapping; check whether the key signal wires are swapped. |
| Switching times out | Check monitor power and inactive-input DDC support. Increase `command_timeout` only if manual commands actually need longer; keep service `TimeoutStopSec` greater than that value. |
| Extra or missed presses | Recheck wiring and adjust `bounce_time`; very fast taps within the debounce window can be missed. |
| Worked before install but service fails | Run the service-account test above, inspect logs, and confirm installed paths and permissions. |

- [ ] Each enabled key selects its intended input, including from another active source.
- [ ] Holding a key produces one switching event.
- [ ] The service account can access GPIO and the monitor's HDMI DDC adapter.
- [ ] After reboot, the controller starts automatically and the keys work.
- [ ] Logs show no persistent startup or switching errors.

The software can be checked with simulated inputs, but actual GPIO, DDC behavior, and boot service operation must be verified on your Pi and monitor.

## References

- [GPIO Zero Button API](https://gpiozero.readthedocs.io/en/stable/api_input.html#button)
- [ddcutil setvcp syntax](https://www.ddcutil.com/command_setvcp/)
- [ddcutil device permissions](https://www.ddcutil.com/i2c_permissions/)
