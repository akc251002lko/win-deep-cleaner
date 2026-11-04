"""Tkinter graphical interface for Win Deep Cleaner."""
from __future__ import annotations

try:
    from .win_deep_cleaner import CleanerError, DEFAULT_AGE_HOURS, LOGGER, clean, detect_platform, format_bytes
except ImportError:
    from win_deep_cleaner import CleanerError, DEFAULT_AGE_HOURS, LOGGER, clean, detect_platform, format_bytes


def run_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise CleanerError("Tkinter is not available in this Python installation.") from exc

    root = tk.Tk()
    root.title("Win Deep Cleaner")
    root.geometry("560x360")
    root.minsize(480, 320)

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

    def show(message: str) -> None:
        output.configure(state="normal")
        output.insert("end", message + "\n")
        output.see("end")
        output.configure(state="disabled")

    def execute(apply_changes: bool) -> None:
        try:
            hours = int(age_var.get())
            if hours < 1:
                raise ValueError("Enter a number of hours greater than zero.")
            if apply_changes and not messagebox.askyesno(
                "Confirm cleanup",
                "Permanently delete eligible files from user TEMP/TMP folders?",
            ):
                return
            result = clean(hours, apply_changes)
            show(
                "{}: considered {}; found bytes {}; deleted {}; reclaimed {}; skipped {}; errors {}.".format(
                    "Cleanup" if apply_changes else "Dry run",
                    result.files_considered,
                    format_bytes(result.bytes_found),
                    result.files_deleted,
                    format_bytes(result.bytes_deleted),
                    result.files_skipped,
                    result.errors,
                )
            )
        except (ValueError, CleanerError) as exc:
            messagebox.showerror("Win Deep Cleaner", str(exc))
        except Exception:
            LOGGER.exception("Unexpected GUI failure")
            messagebox.showerror("Win Deep Cleaner", "Unexpected error. Check the log file.")

    controls = tk.Frame(root)
    controls.pack(pady=(0, 14))
    tk.Button(controls, text="Scan / Dry Run", command=lambda: execute(False)).pack(
        side="left", padx=6
    )
    tk.Button(controls, text="Clean Now", command=lambda: execute(True)).pack(
        side="left", padx=6
    )
    tk.Label(
        root,
        text="Safety: user temporary files only. Dry-run is the default.",
        fg="gray",
    ).pack(pady=(0, 10))
    root.mainloop()
    return 0
