# Raspberry Pi Zero W setup guide for Samsung G95NC input control

This guide assumes the Pi already has a working network connection. It prepares a Raspberry Pi to change a Samsung G95NC monitor's input using DDC/CI commands, locally or over SSH. Wi-Fi provides remote access; the Pi also needs a direct HDMI connection to the monitor to send the display commands.

The commands below verify manual and remote monitor control. After completing this step, follow [Step 2](setup-keys.md) to wire the physical keys and [Step 3](setup-controller.md) to install the key controller and boot service.

## 1. Hardware and software

- Original Raspberry Pi Zero W (first generation, ARMv6, 512 MB RAM), a suitable micro-USB power supply, and a microSD card. This is a different board from the Zero 2 W.
- Mini-HDMI-to-HDMI cable or adapter, connected directly to a spare G95NC HDMI input. The original Zero W uses mini HDMI, not the micro HDMI connector on Pi 4/5. Connect the computers you want to switch between to the other monitor inputs.
- Existing working network connection. The Zero W has no built-in Ethernet; wired networking requires a USB adapter. A USB keyboard also requires a suitable micro-USB OTG adapter.
- Another computer for preparing the card and optionally sending SSH commands.

| Software | Install location | Purpose |
| --- | --- | --- |
| Raspberry Pi Imager | Setup computer | Write Raspberry Pi OS to the card |
| Raspberry Pi OS Lite compatible with Zero W, 32-bit | Pi | Operating system; use the ARMv6-compatible image |
| `ddcutil` | Pi | Detect the monitor and change its input |
| `i2c-tools` | Pi | Optional I2C diagnostics |
| `iw` | Pi | Check and disable Wi-Fi power saving |
| OpenSSH server (`openssh-server`) | Pi | Remote command execution |
| Avahi (`avahi-daemon`) | Pi | Resolve the Pi's `.local` hostname on compatible networks |
| Git | Pi; optional | Download this repository |
| SSH client | Remote computer | Connect to the Pi |

No Python environment, Node.js, Docker, or third-party Python packages are required for the manual SSH/DDC workflow.

## 2. Install Raspberry Pi OS

If the Pi already boots Raspberry Pi OS, skip writing the card and continue with section 3.

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on the setup computer.
2. Select **Raspberry Pi Zero W**, a compatible **32-bit Lite** OS, and the microSD card. The official downloads currently list the original Zero W under **Raspberry Pi OS (Legacy, 32-bit)**, based on Bookworm. Use Imager's compatibility filter or check the official OS compatibility list. Do not install a 64-bit image or a generic Debian ARMv7 `armhf` image on this ARMv6 board. Writing the image erases the selected card.
3. In the customisation settings, configure:
   - Hostname: `g95nc-controller`.
   - Username: `pi`, if you want to use the examples unchanged, and your own login password.
   - SSH access, using a password or your public key.
4. Write the image, insert the card into the Pi, connect HDMI and power, and boot.

The username `pi` is an example, not an assumed default account. Substitute your configured username throughout this guide. If your existing hostname is `g95mc-controller`, use that hostname instead, or change it later with `sudo raspi-config`.

For an existing installation, inspect it before deciding whether to reimage:

```bash
tr -d '\0' </proc/device-tree/model
uname -m
cat /etc/os-release
```

The original Zero W normally reports `armv6l`. A working supported 32-bit Raspberry Pi OS installation can be kept. The word `armhf` in package metadata alone does not prove incompatibility: Raspberry Pi OS's ARMv6-compatible packages differ from generic Debian ARMv7 packages.

## 3. Update and install packages

Run **on the Pi** with an internet connection:

Updates can take considerably longer on the single-core Zero W. Use the distribution's packaged ddcutil rather than compiling it from source; the SSH/manual switching workflow is lightweight and does not need a desktop.

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y ddcutil i2c-tools openssh-server avahi-daemon iw
sudo systemctl enable --now ssh
sudo systemctl enable --now avahi-daemon
sudo reboot
```

Reconnect after reboot and verify:

```bash
ddcutil --version
systemctl is-active ssh
systemctl is-active avahi-daemon
```

To download this documentation on the Pi, optionally install Git and clone the repository:

```bash
sudo apt install -y git
git clone https://github.com/peiminggu/g95nc-input-controller.git
cd g95nc-input-controller
```

Cloning downloads the files. Install the key controller separately using Step 3 after verifying monitor control and key wiring.

### Disable Wi-Fi power saving

For the Pi's remote-control connection, disable Wi-Fi power saving immediately and save the setting in the active NetworkManager profile. These commands automatically select the profile used by `wlan0`; no network name needs to be entered.

Check the current runtime setting:

```bash
iw dev wlan0 get power_save
```

Save the setting and apply it immediately:

```bash
wifi_profile_uuid="$(nmcli -g GENERAL.CON-UUID device show wlan0)"
if [ -n "$wifi_profile_uuid" ] && [ "$wifi_profile_uuid" != "--" ]; then
    sudo nmcli connection modify uuid "$wifi_profile_uuid" 802-11-wireless.powersave 2
    sudo iw dev wlan0 set power_save off
else
    echo "No active Wi-Fi profile found on wlan0. Connect Wi-Fi before running this step."
fi
```

NetworkManager value `2` disables Wi-Fi power saving. The profile setting persists across reboots; the `iw` command applies it to the current session without deliberately disconnecting SSH. It applies to this profile; repeat the step if you later use a different Wi-Fi profile.

Verify immediately, and repeat the runtime check after the next reboot:

```bash
iw dev wlan0 get power_save
nmcli -g 802-11-wireless.powersave connection show uuid "$wifi_profile_uuid"
```

Expect `Power save: off` and a profile value of `2` (possibly displayed as `2 (disable)`). The shell variable is only available in the session where it was assigned; assign it again before checking the profile in a new session. This step assumes NetworkManager manages the connected `wlan0`, as on the Pi used for this setup.

## 4. Enable the display's I2C access

Load the I2C device interface and arrange for it to load at boot:

```bash
sudo modprobe i2c-dev
echo i2c-dev | sudo tee /etc/modules-load.d/g95nc-i2c.conf
i2cdetect -l
```

`i2cdetect -l` lists adapters without probing their addresses. Do not assume a fixed HDMI bus number, or assume the GPIO I2C bus is the monitor's HDMI bus.
ffffff
Modern Raspberry Pi OS normally uses the KMS display driver. If no display-related I2C adapters appear, check the boot configuration:

```bash
grep -n 'vc4.*kms' /boot/firmware/config.txt
```

Older OS releases use `/boot/config.txt`. On the Zero W, first try the installation's existing KMS configuration and the monitor detection command below. Do not use the Pi 4/5 HDMI bus numbers as a guide for this board.

If HDMI DDC is unavailable, inspect the applicable configuration file. Back it up before editing, for example on Bookworm:

```bash
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.before-g95nc
sudo nano /boot/firmware/config.txt
```

The upstream ddcutil documentation describes `dtoverlay=vc4-kms-v3d` as one way to expose HDMI I2C on older Pi 2/3 hardware. If your Zero W is using a legacy display driver, a KMS configuration is a troubleshooting option, not a verified fix for this particular board. Avoid duplicate or conflicting KMS/FKMS overlays, reboot after changes, then repeat `i2cdetect -l` and `sudo ddcutil detect`. Restore the backup if the change causes display problems.

For older Pi hardware, upstream also documents the legacy setting `dtparam=i2c2_iknowwhatimdoing`. This enables access to an HDMI bus normally used by the GPU and can cause access conflicts. It has not been verified on your Zero W, so it is not part of the normal setup procedure. Do not add it blindly or probe the HDMI bus with address scans. If KMS does not expose working DDC, investigate the exact OS/kernel and adapter list before choosing a legacy configuration.

Enabling GPIO I2C in `raspi-config` alone does not establish that HDMI DDC is available. The monitor detection in the next section is the decisive check.

## 5. Detect the G95NC

Keep the HDMI cable between the Pi and monitor connected. Initially select the Pi's HDMI input using the monitor's on-screen menu. Enable DDC/CI in the monitor settings if an option is available.

```bash
sudo ddcutil detect
```

Record the display number for the G95NC and its I2C bus. The examples below use `--display 1`; replace `1` with the detected G95NC display number if necessary. Display numbers can change when connected hardware changes, so detect again after reconnecting displays.

```bash
sudo ddcutil --display 1 capabilities
sudo ddcutil --display 1 getvcp 60
```

Feature `60` is the hexadecimal VCP input-source feature. Check whether it is listed in capabilities and whether the current input can be read. The capabilities response can be incomplete or inaccurate, so verify switching physically as well.

## 6. Verify and record input codes

Common MCCS input values are shown below as examples. **They are not a verified G95NC port mapping.** In particular, do not assume HDMI 3 has a particular value.

| Example input | Common value |
| --- | --- |
| DisplayPort 1 | `0x0f` |
| HDMI 1 | `0x11` |
| HDMI 2 | `0x12` |

Use the monitor's capabilities and test results to determine its actual supported values. One approach is to manually select each connected input and read feature `60` over SSH from the Pi. If DDC stops responding while another input is selected, return to the Pi input with the monitor menu.

To test a value confirmed by the monitor's capabilities, for example HDMI 1:

```bash
sudo ddcutil --display 1 setvcp 60 0x11
```

The Pi's picture may disappear when switching away; continue over SSH. Confirm that the intended computer appears on the monitor. Test switching back to the Pi using its verified input value. The setup is suitable for remote switching only if the monitor continues accepting commands through the Pi's HDMI connection while another input is active.

Record your results:

| Monitor port | Connected device | Verified VCP value | Switching works from another active input? |
| --- | --- | --- | --- |
| DisplayPort | | | |
| HDMI 1 | | | |
| HDMI 2 | | | |
| HDMI 3 | | | |

Test with the monitor's intended settings, including Picture-by-Picture if you use it. Successful single-input switching does not establish support for changing Picture-by-Picture sources.

## 7. Control the monitor remotely

On a Windows computer, open PowerShell and check the SSH client:

```powershell
ssh -V
```

If unavailable, install **OpenSSH Client** through Windows Optional Features. On macOS or Linux, use the system SSH client.

Connect from the remote computer:

```bash
ssh pi@g95nc-controller.local
```

If the hostname does not resolve, use the IP shown by `hostname -I`, for example `ssh pi@192.168.1.50`. Verify the host identity on first connection before accepting its key.

Inside the SSH session, run your verified switching command:

```bash
sudo ddcutil --display 1 setvcp 60 0x11
```

Alternatively, send one command from the remote computer, allocating a terminal so `sudo` can prompt:

```bash
ssh -t pi@g95nc-controller.local 'sudo ddcutil --display 1 setvcp 60 0x11'
```

Use your actual username, hostname, display number, and verified input value. This command may ask for both the SSH login password and the Pi's `sudo` password.

### Optional: use ddcutil without sudo

First test `ddcutil detect` without `sudo`; packaged device permission rules may already allow access. If access is denied, inspect the detected adapter, replacing the example bus number `2` with its actual bus number:

```bash
ls -l /dev/i2c-2
getent group i2c
```

If the device belongs to group `i2c` and grants that group read/write access, add your login user:

```bash
sudo usermod -aG i2c "$USER"
```

Log out completely and log in again, then verify `ddcutil detect` and the switching command without `sudo`. Group membership grants access to I2C adapters, not just input switching. If the device uses different permissions, consult the ddcutil device-permissions documentation rather than making adapters world-writable.

After verifying access, a remote command can omit `sudo`:

```bash
ssh pi@g95nc-controller.local 'ddcutil --display 1 setvcp 60 0x11'
```

SSH keys can remove the login password prompt. No background controller service is required for this workflow: SSH accepts the command and ddcutil sends it to the monitor.

## 8. Troubleshooting

| Symptom | Check or next step |
| --- | --- |
| `sudo` says `Sorry, try again` | Enter the Pi account's login password. |
| SSH connection refused | Check `systemctl status ssh` on the Pi and confirm the IP address. |
| `.local` name fails | Use the Pi's IP; confirm Avahi is running and both computers can communicate on the LAN. |
| No monitor detected | Check direct HDMI connection, monitor power/DDC setting, KMS configuration, and `i2c-dev`. Run `sudo ddcutil environment` for diagnostics. |
| Works with sudo only | Check the optional I2C permissions instructions above. |
| Input command unsupported | Check feature `60` support and actual input values. Installing more software cannot guarantee monitor support. |
| Command errors after picture changes | The monitor may stop responding on the inactive input. Confirm visually and test a return command through SSH. |
| Cannot switch back through the Pi | Return using the monitor menu. If inactive-input DDC is unavailable, this HDMI control method cannot provide reliable switching in both directions. |

## 9. Completion checklist

- [ ] Pi boots and reconnects to its network after reboot.
- [ ] `iw dev wlan0 get power_save` reports `Power save: off` after reboot.
- [ ] SSH access works from the intended remote computer.
- [ ] ddcutil detects the G95NC after reboot.
- [ ] Actual input values are recorded and tested.
- [ ] Switching away from the Pi and back works over SSH.
- [ ] Any required Picture-by-Picture behavior has been tested separately.

These instructions were checked against upstream documentation, but have not been executed on your Pi or validated against your G95NC firmware.

## References

- [NetworkManager Wi-Fi power-saving settings](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless.html)
- [Raspberry Pi OS installation](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Raspberry Pi OS downloads and model compatibility](https://www.raspberrypi.com/software/operating-systems/)
- [Original Raspberry Pi Zero W hardware](https://www.raspberrypi.com/products/raspberry-pi-zero-w/)
- [Raspberry Pi remote access, SSH and network discovery](https://www.raspberrypi.com/documentation/computers/remote-access.html)
- [ddcutil installation and configuration](https://www.ddcutil.com/install_config_main/)
- [ddcutil Raspberry Pi configuration](https://www.ddcutil.com/raspberry/)
- [ddcutil setvcp command and value syntax](https://www.ddcutil.com/command_setvcp/)
- [ddcutil I2C permissions](https://www.ddcutil.com/i2c_permissions/)
