"""Hardware-independent checks: python3 -m unittest discover -s tests -v."""

import json
import subprocess
import threading
import unittest
from unittest.mock import mock_open, patch

import controller


class ControllerTests(unittest.TestCase):
    def config(self, **changes):
        config = {"display": 2, "keys": [
            {"name": "Work", "gpio": 17, "input": "0x11"},
            {"name": "Unused", "gpio": 27, "input": None}]}
        config.update(changes)
        with patch("builtins.open", mock_open(read_data=json.dumps(config))):
            return controller.load_config("config.json")

    def test_disabled_keys_and_hex_values(self):
        config = self.config()
        self.assertEqual(config["keys"], [
            {"name": "Work", "gpio": 17, "input": "0x11"}])
        self.assertEqual(config["bounce_time"], 0.05)

    def test_rejects_invalid_configuration(self):
        for changes in (
            {"display": True}, {"command_timeout": -1},
            {"bounce_time": float("inf")},
            {"keys": [{"name": "Unset", "gpio": 17, "input": None}]},
            {"keys": [{"name": "A", "gpio": 17, "input": "0x11"},
                      {"name": "B", "gpio": 17, "input": "0x12"}]},
            {"keys": [{"name": "Bad", "gpio": 17, "input": "0x11; reboot"}]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)

    @patch("controller.subprocess.run")
    def test_command_uses_selected_display_and_input(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        config = self.config()
        self.assertTrue(controller.switch_input(config, config["keys"][0]))
        run.assert_called_once_with(
            ["ddcutil", "--display", "2", "setvcp", "60", "0x11"],
            capture_output=True, text=True, timeout=15, check=False)

    @patch("controller.subprocess.run")
    def test_failures_are_reported_and_next_press_can_succeed(self, run):
        run.side_effect = [subprocess.TimeoutExpired("ddcutil", 15),
                           subprocess.CompletedProcess([], 1, "", "DDC unavailable"),
                           subprocess.CompletedProcess([], 0, "", "")]
        config = self.config()
        with self.assertLogs("g95nc", level="ERROR"):
            self.assertFalse(controller.switch_input(config, config["keys"][0]))
            self.assertFalse(controller.switch_input(config, config["keys"][0]))
        self.assertTrue(controller.switch_input(config, config["keys"][0]))

    @patch("controller.subprocess.run")
    def test_dry_run_never_invokes_ddcutil(self, run):
        config = self.config()
        self.assertTrue(controller.switch_input(config, config["keys"][0], True))
        run.assert_not_called()

    def test_callbacks_preserve_key_mapping_and_close_on_stop(self):
        config = self.config(keys=[
            {"name": "A", "gpio": 17, "input": "0x11"},
            {"name": "B", "gpio": 27, "input": "0x12"}])
        stop = threading.Event()
        buttons = []
        dispatched = []

        class FakeButton:
            def __init__(self, pin, **options):
                self.pin = pin
                self.options = options
                self.closed = False
                buttons.append(self)

            @property
            def when_pressed(self):
                return self.callback

            @when_pressed.setter
            def when_pressed(self, callback):
                self.callback = callback
                if len(buttons) == 2:
                    # Both handlers are attached: simulate separate key presses.
                    buttons[0].callback()
                    buttons[1].callback()

            def close(self):
                self.closed = True

        def switch(config, key, dry_run):
            dispatched.append(key["input"])
            if len(dispatched) == 2:
                stop.set()

        with patch("controller.switch_input", side_effect=switch):
            controller.monitor_keys(config, stop, button_factory=FakeButton)
        self.assertEqual(dispatched, ["0x11", "0x12"])
        self.assertTrue(all(button.closed for button in buttons))
        self.assertEqual(buttons[0].options, {"pull_up": True, "bounce_time": 0.05})

    def test_closes_opened_buttons_when_gpio_setup_fails(self):
        config = self.config(keys=[
            {"name": "A", "gpio": 17, "input": "0x11"},
            {"name": "B", "gpio": 27, "input": "0x12"}])
        from unittest.mock import Mock
        button = Mock()
        factory = Mock(side_effect=[button, OSError("GPIO unavailable")])
        with self.assertRaises(OSError):
            controller.monitor_keys(config, threading.Event(), button_factory=factory)
        button.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
