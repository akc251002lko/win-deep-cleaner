"""Windows-only smoke tests for the real Tkinter application window.

These tests require a Windows desktop session and the Tcl/Tk components shipped
with the configured Python installation. They are intentionally skipped on
non-Windows developer machines.
"""
from __future__ import annotations

import os
import threading
import time
import tkinter
import unittest
from typing import Any, Dict, List
from unittest import mock

import gui as gui_module
import win_deep_cleaner as cleaner


@unittest.skipUnless(os.name == "nt", "Tkinter desktop smoke test requires Windows")
class WindowsGuiSmokeTests(unittest.TestCase):
    def test_window_opens_and_event_loop_stays_responsive_during_scan(self) -> None:
        state: Dict[str, Any] = {
            "heartbeat": False,
            "scan_started": False,
            "title": "",
            "button_labels": [],
        }
        scan_started = threading.Event()

        def delayed_scan(age_hours: int):
            scan_started.set()
            time.sleep(0.30)
            return cleaner.ScanResult(), []

        original_tk = tkinter.Tk

        def create_test_root(*args: Any, **kwargs: Any):
            root = original_tk(*args, **kwargs)

            def walk_widgets(parent: Any) -> List[Any]:
                found: List[Any] = []
                for child in parent.winfo_children():
                    found.append(child)
                    found.extend(walk_widgets(child))
                return found

            def click_scan() -> None:
                state["title"] = root.title()
                widgets = walk_widgets(root)
                state["button_labels"] = [
                    str(widget.cget("text"))
                    for widget in widgets
                    if isinstance(widget, tkinter.Button)
                ]
                scan_buttons = [
                    widget
                    for widget in widgets
                    if isinstance(widget, tkinter.Button)
                    and widget.cget("text") == "Scan / Dry Run"
                ]
                if not scan_buttons:
                    root.destroy()
                    return
                root.after(40, lambda: state.__setitem__("heartbeat", True))
                scan_buttons[0].invoke()

            def finish_test() -> None:
                state["scan_started"] = scan_started.is_set()
                root.destroy()

            root.after(25, click_scan)
            root.after(700, finish_test)
            return root

        with mock.patch.object(tkinter, "Tk", side_effect=create_test_root):
            with mock.patch.object(gui_module, "scan", side_effect=delayed_scan):
                result = gui_module.run_gui()

        self.assertEqual(result, 0)
        self.assertEqual(state["title"], "Win Deep Cleaner")
        self.assertIn("Scan / Dry Run", state["button_labels"])
        self.assertTrue(state["scan_started"], "GUI did not start its scan worker")
        self.assertTrue(
            state["heartbeat"],
            "Tkinter event loop stalled while the background scan was running",
        )


if __name__ == "__main__":
    unittest.main()
