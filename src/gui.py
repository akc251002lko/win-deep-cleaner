"""Responsive Tkinter graphical interface for Win Deep Cleaner."""
from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Tuple

try:
    from .win_deep_cleaner import (
        CleanerError,
        DEFAULT_AGE_HOURS,
        LOGGER,
        clean_candidates,
        detect_platform,
        format_bytes,
        scan,
    )
except ImportError:
    from win_deep_cleaner import (
        CleanerError,
        DEFAULT_AGE_HOURS,
        LOGGER,
        clean_candidates,
        detect_platform,
        format_bytes,
        scan,
    )


def run_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise CleanerError("Tkinter is not available in this Python installation.") from exc

    root = tk.Tk()
    root.title("Win Deep Cleaner")
    root.geometry("560x380")
    root.minsize(480, 340)

    platform_info = detect_platform()
    heading = tk.Label(root, text="Win Deep Cleaner", font=("Segoe UI", 18, "bold"))
    heading.pack(pady=(16, 4))
    details = tk.Label(
        root,
        text="{} | {} | Python {}".format(
            platform_info["os"], platform_info["architecture"], platform_info["python"]
        ),
    )
    details.pack(pady=4)

    age_var = tk.StringVar(value=str(DEFAULT_AGE_HOURS))
    tk.Label(root, text="Only consider files older than (hours):").pack(pady=(14, 2))
    age_entry = tk.Entry(root, textvariable=age_var, width=10, justify="center")
    age_entry.pack()

    output = tk.Text(root, height=9, width=64, state="disabled", wrap="word")
    output.pack(fill="both", expand=True, padx=14, pady=12)

    status = tk.Label(root, text="Ready. Scanning is read-only; cleanup requires confirmation.")
    status.pack(pady=(0, 6))

    results: "queue.Queue[Tuple[str, bool, Any]]" = queue.Queue()
    state = {"busy": False}

    def show(message: str) -> None:
        output.configure(state="normal")
        output.insert("end", message + "\n")
        output.see("end")
        output.configure(state="disabled")

    def set_busy(busy: bool, message: str) -> None:
        state["busy"] = busy
        button_state = "disabled" if busy else "normal"
        scan_button.configure(state=button_state)
        clean_button.configure(state=button_state)
        age_entry.configure(state=button_state)
        status.configure(text=message)

    def start_task(
        task_name: str,
        task: Callable[..., Any],
        *args: Any,
    ) -> None:
        set_busy(True, "Scanning... The window remains responsive.")
        def worker() -> None:
            try:
                results.put((task_name, True, task(*args)))
            except Exception as exc:
                LOGGER.exception("GUI background task failed: %s", task_name)
                results.put((task_name, False, exc))
        threading.Thread(
            target=worker,
            name="WinDeepCleaner-{}".format(task_name),
            daemon=True,
        ).start()
        root.after(100, poll_results)

    def render_result(result: Any) -> None:
        show(
            "{}: considered {}; found {}; deleted {}; reclaimed {}; skipped {}; errors {}.".format(
                "Cleanup" if not result.dry_run else "Dry run",
                result.files_considered,
                format_bytes(result.bytes_found),
                result.files_deleted,
                format_bytes(result.bytes_deleted),
                result.files_skipped,
                result.errors,
            )
        )
        if result.errors:
            status.configure(text="Completed with errors. Review the result and log.")
        else:
            status.configure(text="Operation completed.")

    def poll_results() -> None:
        try:
            task_name, succeeded, payload = results.get_nowait()
        except queue.Empty:
            if state["busy"]:
                root.after(100, poll_results)
            return

        if not succeeded:
            set_busy(False, "Operation failed.")
            messagebox.showerror("Win Deep Cleaner", str(payload))
            return

        if task_name == "scan":
            scan_result, candidates, age_hours, apply_changes = payload
            show(
                "Preview — {} eligible file(s), {} total, older than {} hour(s).".format(
                    len(candidates), format_bytes(scan_result.bytes_found), age_hours
                )
            )

            if scan_result.errors:
                dry_result = clean_candidates(scan_result, candidates, False)
                render_result(dry_result)
                messagebox.showwarning(
                    "Incomplete scan",
                    "The scan reported {} error(s). Cleanup is disabled because the "
                    "complete deletion scope cannot be verified. Review the log and scan again.".format(
                        scan_result.errors
                    ),
                )
                set_busy(False, "Cleanup blocked because the scan was incomplete.")
                return

            if not apply_changes or not candidates:
                render_result(clean_candidates(scan_result, candidates, False))
                set_busy(False, "Scan completed. No files were deleted.")
                return

            confirmed = messagebox.askyesno(
                "Confirm cleanup",
                "The scan found {} eligible file(s) totaling {} older than {} hour(s).\n\n"
                "Permanently delete only these reviewed files? Files changed since the scan "
                "will be skipped.".format(
                    len(candidates), format_bytes(scan_result.bytes_found), age_hours
                ),
            )
            if not confirmed:
                show("Cleanup cancelled. No files were deleted.")
                set_busy(False, "Cleanup cancelled; no files were deleted.")
                return

            start_task("cleanup", clean_candidates, scan_result, candidates, True)
            return

        if task_name == "cleanup":
            render_result(payload)
            set_busy(False, "Cleanup finished. Review the result above.")
            return

        set_busy(False, "Unexpected task result.")
        LOGGER.error("Unknown GUI background task: %s", task_name)

    def scan_for_gui(age_hours: int, apply_changes: bool) -> Any:
        scan_result, candidates = scan(age_hours)
        return scan_result, candidates, age_hours, apply_changes

    def execute(apply_changes: bool) -> None:
        try:
            hours = int(age_var.get().strip())
            if hours < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid age threshold",
                "Enter a whole number of hours greater than zero.",
            )
            return
        start_task("scan", scan_for_gui, hours, apply_changes)

    controls = tk.Frame(root)
    controls.pack(pady=(0, 14))
    scan_button = tk.Button(
        controls, text="Scan / Dry Run", command=lambda: execute(False)
    )
    scan_button.pack(side="left", padx=6)
    clean_button = tk.Button(
        controls, text="Clean Now", command=lambda: execute(True)
    )
    clean_button.pack(side="left", padx=6)
    tk.Label(
        root,
        text="Safety: user temporary files only. Dry-run is the default.",
        fg="gray",
    ).pack(pady=(0, 10))

    def close_window() -> None:
        if state["busy"]:
            messagebox.showwarning(
                "Operation in progress",
                "Please wait for the current scan or cleanup to finish before closing.",
            )
            return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.mainloop()
    return 0
