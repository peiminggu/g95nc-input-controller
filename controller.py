#!/usr/bin/env python3
"""Switch monitor inputs using the GPIO keys wired in Step 2."""

import argparse
import json
import logging
import math
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading

LOG = logging.getLogger("g95nc")


def load_config(path):
    with open(path, encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    display = config.get("display", 1)
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
        while not stop.is_set():
            try:
                key = presses.get(timeout=0.2)
            except queue.Empty:
                continue
            if not stop.is_set():
                switch_input(config, key, dry_run)
    finally:
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
