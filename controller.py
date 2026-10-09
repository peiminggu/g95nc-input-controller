#!/usr/bin/env python3
"""Switch monitor inputs using the GPIO keys wired in Step 2."""

import argparse
import json
import logging
import math
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import time

LOG = logging.getLogger("g95nc")


def load_config(path):
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    display = config.get("display", 1)
    oled_enabled = config.get("oled_enabled", False)
    if type(oled_enabled) is not bool:
        raise ValueError("oled_enabled must be true or false")
    config["oled_enabled"] = oled_enabled
    address = config.get("oled_address", "0x3c")
    if isinstance(address, str):
        address = int(address, 16)
    if type(address) is not int or not 0x08 <= address <= 0x77:
        raise ValueError("oled_address must be a valid 7-bit I2C address")
    config["oled_address"] = address
    if type(display) is not int or display < 1:
        raise ValueError("display must be a positive integer")
    for field, default in (("bounce_time", 0.05), ("command_timeout", 15)):
        value = config.get(field, default)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(field + " must be a finite positive number")
        config[field] = value
    keys = config.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ValueError("keys must be a non-empty list")
    pins = set()
    enabled = []
    for key in keys:
        if not isinstance(key, dict):
            raise ValueError("Each key must be an object")
        pin = key.get("gpio")
        if type(pin) is not int or not 0 <= pin <= 27 or pin in pins:
            raise ValueError("Each gpio must be a unique BCM number from 0 to 27")
        pins.add(pin)
        if oled_enabled and pin in (2, 3):
            raise ValueError("GPIO2 and GPIO3 are reserved for the enabled OLED")
        name = key.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each key needs a non-empty name")
        value = key.get("input")
        if value is None:
            continue
        if isinstance(value, str):
            value = int(value, 16) if value.lower().startswith("0x") else int(value, 10)
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError("input must be an integer or a code such as 0x11, or null")
        enabled.append(dict(key, input="0x{:02x}".format(value)))
    if not enabled:
        raise ValueError("Set at least one key input to a verified VCP value; null disables a key")
    return dict(config, display=display, keys=enabled)


def current_source(config):
    """Read the actual VCP source; never guess from a successful set command."""
    try:
        result = subprocess.run(
            ["ddcutil", "--display", str(config["display"]), "--terse", "getvcp", "60"],
            capture_output=True, text=True, timeout=config["command_timeout"], check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "Ready"
    if result.returncode:
        return "Ready"
    match = re.search(r"^VCP 60 SNC x([0-9a-fA-F]+)\s*$", result.stdout, re.MULTILINE)
    if match:
        value = int(match.group(1), 16)
        for key in config["keys"]:
            if int(key["input"], 16) == value:
                name = key["name"]
                if name in ("DP", "DisplayPort"):
                    return "DisplayPort"
                if name in ("HDMI 1", "HDMI 2", "HDMI 3"):
                    return name
    return "Ready"


class OledStatus:
    """Optional SSD1306 display. Failures must not stop the GPIO controller."""

    def __init__(self, config):
        self.device = None
        self.last_text = None
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from PIL import ImageFont
            self.font = ImageFont.load_default()
            self.device = ssd1306(i2c(port=1, address=config["oled_address"]),
                                  width=128, height=32)
        except Exception as error:
            LOG.warning("OLED unavailable; keys remain enabled: %s", error)

    def show(self, text):
        if self.device is None or text == self.last_text:
            return
        try:
            from luma.core.render import canvas
            with canvas(self.device) as draw:
                box = draw.textbbox((0, 0), text, font=self.font)
                x = (128 - (box[2] - box[0])) // 2 - box[0]
                y = (32 - (box[3] - box[1])) // 2 - box[1]
                draw.text((x, y), text, font=self.font, fill="white")
            self.last_text = text
        except Exception as error:
            LOG.warning("OLED update failed; keys remain enabled: %s", error)
            self.close()

    def close(self):
        if self.device is not None:
            try:
                self.device.cleanup()
            except Exception as error:
                LOG.warning("OLED cleanup failed: %s", error)
            self.device = None


def switch_input(config, key, dry_run=False):
    command = ["ddcutil", "--display", str(config["display"]),
               "setvcp", "60", key["input"]]
    LOG.info("%s: select %s", key["name"], key["input"])
    if dry_run:
        LOG.info("Dry run: %s", " ".join(command))
        return True
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=config["command_timeout"], check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        LOG.error("Switch failed: %s", error)
        return False
    if result.returncode:
        LOG.error("ddcutil exited %s: %s", result.returncode,
                  (result.stderr or result.stdout).strip())
        return False
    LOG.info("Input command completed; confirm the selected source on the monitor")
    return True


def monitor_keys(config, stop, dry_run=False, button_factory=None):
    if button_factory is None:
        from gpiozero import Button
        button_factory = Button
    presses = queue.Queue(maxsize=16)
    buttons = []
    oled = None

    def enqueue(key):
        if stop.is_set():
            return
        try:
            presses.put_nowait(key)
        except queue.Full:
            LOG.warning("Too many pending presses; ignoring %s", key["name"])

    try:
        for key in config["keys"]:
            button = button_factory(key["gpio"], pull_up=True,
                                    bounce_time=config["bounce_time"])
            buttons.append(button)
            # A no-argument callback avoids GPIO Zero passing the device as key.
            button.when_pressed = lambda key=key: enqueue(key)
        LOG.info("Ready: %s. Press a key to switch; Ctrl+C stops.",
                 ", ".join(key["name"] for key in config["keys"]))
        if config["oled_enabled"] and not dry_run:
            oled = OledStatus(config)
            oled.show("Ready")
            if oled.device is not None:
                oled.show(current_source(config))
        next_refresh = time.monotonic() + 5
        while not stop.is_set():
            try:
                key = presses.get(timeout=0.2)
            except queue.Empty:
                if oled is not None and oled.device is not None and time.monotonic() >= next_refresh:
                    oled.show(current_source(config))
                    next_refresh = time.monotonic() + 5
                continue
            if not stop.is_set():
                switch_input(config, key, dry_run)
                if oled is not None and oled.device is not None and not stop.is_set():
                    oled.show(current_source(config))
                    next_refresh = time.monotonic() + 5
    finally:
        if oled is not None:
            oled.close()
        for button in buttons:
            button.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).with_name("config.json"))
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Monitor GPIO keys but only log switching commands")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        if args.check_config:
            LOG.info("Configuration valid: %s enabled keys", len(config["keys"]))
            return 0
        if not args.dry_run and shutil.which("ddcutil") is None:
            raise ValueError("ddcutil is missing; install it with apt")
        stop = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stop.set())
        monitor_keys(config, stop, args.dry_run)
        return 0
    except (OSError, ValueError, ImportError) as error:
        LOG.error("Controller could not start: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
