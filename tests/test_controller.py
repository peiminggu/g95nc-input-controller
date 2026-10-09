"""Hardware-independent checks: python3 -m unittest discover -s tests -v."""

import json
import subprocess
import threading
import unittest
from unittest.mock import Mock, mock_open, patch

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
        self.assertFalse(config["oled_enabled"])

    def test_oled_configuration_validation(self):
        self.assertEqual(self.config(oled_enabled=True)["oled_address"], 0x3c)
        for changes in ({"oled_enabled": "true"}, {"oled_address": True},
                        {"oled_address": "0xff"},
                        {"oled_enabled": True, "keys": [
                            {"name": "HDMI 1", "gpio": 2, "input": "0x11"}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)

    @patch("controller.subprocess.run")
    def test_current_source_labels_and_unknown(self, run):
        config = self.config(keys=[
            {"name": "HDMI 1", "gpio": 17, "input": "0x11"},
            {"name": "HDMI 2", "gpio": 27, "input": "0x12"},
            {"name": "HDMI 3", "gpio": 23, "input": "0x32"},
            {"name": "DP", "gpio": 22, "input": "0x0f"}])
        for output, expected in (("VCP 60 SNC x11\n", "HDMI 1"),
                                 ("VCP 60 SNC x12\n", "HDMI 2"),
                                 ("VCP 60 SNC x32\n", "HDMI 3"),
                                 ("VCP 60 SNC x0F\n", "DisplayPort"),
                                 ("VCP 60 SNC x99\n", "Ready"),
                                 ("malformed", "Ready")):
            run.return_value = subprocess.CompletedProcess([], 0, output, "")
            self.assertEqual(controller.current_source(config), expected)
        run.return_value = subprocess.CompletedProcess([], 1, "VCP 60 SNC x11", "error")
        self.assertEqual(controller.current_source(config), "Ready")
        run.side_effect = subprocess.TimeoutExpired("ddcutil", 15)
        self.assertEqual(controller.current_source(config), "Ready")
        run.side_effect = OSError("missing")
        self.assertEqual(controller.current_source(config), "Ready")

    def test_oled_startup_refresh_and_cleanup(self):
        config = self.config(oled_enabled=True)
        stop = threading.Event()
        button = Mock()
        oled = Mock()

        def switch(*args):
            return True

        def read_source(*args):
            if read_source.calls:
                stop.set()
                return "HDMI 2"
            read_source.calls += 1
            button.when_pressed()
            return "HDMI 1"

        read_source.calls = 0
        with patch("controller.OledStatus", return_value=oled), \
                patch("controller.current_source", side_effect=read_source), \
                patch("controller.switch_input", side_effect=switch):
            controller.monitor_keys(config, stop, button_factory=Mock(return_value=button))
        self.assertEqual([call.args[0] for call in oled.show.call_args_list],
                         ["Ready", "HDMI 1", "HDMI 2"])
        oled.close.assert_called_once()
        button.close.assert_called_once()

    def test_disabled_and_dry_run_skip_oled_and_source_reads(self):
        for enabled, dry_run in ((False, False), (True, True)):
            config = self.config(oled_enabled=enabled)
            stop = threading.Event()
            stop.set()
            with patch("controller.OledStatus") as oled, \
                    patch("controller.current_source") as read:
                controller.monitor_keys(config, stop, dry_run, button_factory=Mock())
            oled.assert_not_called()
            read.assert_not_called()

    def test_idle_poll_refreshes_source(self):
        config = self.config(oled_enabled=True)
        stop = threading.Event()
        oled = Mock()
        reads = []

        def source(*args):
            reads.append(True)
            if len(reads) == 2:
                stop.set()
                return "HDMI 2"
            return "Ready"

        presses = Mock()
        presses.get.side_effect = controller.queue.Empty
        with patch("controller.OledStatus", return_value=oled), \
                patch("controller.current_source", side_effect=source), \
                patch("controller.queue.Queue", return_value=presses), \
                patch("controller.time.monotonic", side_effect=[0, 6, 6]):
            controller.monitor_keys(config, stop, button_factory=Mock())
        self.assertEqual(len(reads), 2)
        oled.show.assert_called_with("HDMI 2")

    def test_unavailable_oled_does_not_block_switching(self):
        config = self.config(oled_enabled=True)
        stop = threading.Event()
        button = Mock()
        oled = Mock(device=None)
        oled.show.side_effect = lambda text: button.when_pressed()

        def switch(*args):
            stop.set()
            return True

        with patch("controller.OledStatus", return_value=oled), \
                patch("controller.current_source") as read, \
                patch("controller.switch_input", side_effect=switch) as switching:
            controller.monitor_keys(config, stop, button_factory=Mock(return_value=button))
        switching.assert_called_once()
        read.assert_not_called()
        oled.close.assert_called_once()

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
