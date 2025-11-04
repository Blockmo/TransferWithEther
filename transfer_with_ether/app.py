"""Tkinter graphical user interface for TransferWithEther."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from . import network


class FileTransferApp:
    """Encapsulates the Tkinter GUI and background worker threads."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TransferWithEther")
        self.root.geometry("540x360")
        self.root.resizable(False, False)

        self.mode_var = tk.StringVar(value="sender")
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="5001")
        self.file_var = tk.StringVar()
        self.destination_var = tk.StringVar(value=str(os.getcwd()))
        self.status_var = tk.StringVar(value="Select sender or receiver mode to begin.")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ui_queue: queue.Queue[tuple[str, tuple]] = queue.Queue()

        self._build_ui()
        self._update_widget_state()
        self.root.after(100, self._process_ui_queue)

    # ------------------------------------------------------------------ UI SETUP
    def _build_ui(self) -> None:
        """Create all widgets."""
        mode_frame = ttk.LabelFrame(self.root, text="Mode")
        mode_frame.pack(fill="x", padx=12, pady=8)

        sender_radio = ttk.Radiobutton(
            mode_frame, text="Sender", variable=self.mode_var, value="sender", command=self._update_widget_state
        )
        receiver_radio = ttk.Radiobutton(
            mode_frame, text="Receiver", variable=self.mode_var, value="receiver", command=self._update_widget_state
        )
        sender_radio.grid(row=0, column=0, padx=8, pady=4, sticky="w")
        receiver_radio.grid(row=0, column=1, padx=8, pady=4, sticky="w")

        connection_frame = ttk.LabelFrame(self.root, text="Connection")
        connection_frame.pack(fill="x", padx=12, pady=8)

        ttk.Label(connection_frame, text="Host:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.host_entry = ttk.Entry(connection_frame, textvariable=self.host_var, width=25)
        self.host_entry.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(connection_frame, text="Port:").grid(row=0, column=2, sticky="e", padx=4, pady=4)
        self.port_entry = ttk.Entry(connection_frame, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, sticky="w", padx=4, pady=4)

        self.check_button = ttk.Button(connection_frame, text="Check Connection", command=self._check_connection)
        self.check_button.grid(row=0, column=4, padx=4, pady=4)

        file_frame = ttk.LabelFrame(self.root, text="File Selection")
        file_frame.pack(fill="x", padx=12, pady=8)

        ttk.Label(file_frame, text="File:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=40)
        self.file_entry.grid(row=0, column=1, sticky="we", padx=4, pady=4)
        self.browse_button = ttk.Button(file_frame, text="Browse", command=self._select_file)
        self.browse_button.grid(row=0, column=2, padx=4, pady=4)

        ttk.Label(file_frame, text="Save to:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self.destination_entry = ttk.Entry(file_frame, textvariable=self.destination_var, width=40)
        self.destination_entry.grid(row=1, column=1, sticky="we", padx=4, pady=4)
        self.destination_button = ttk.Button(file_frame, text="Choose", command=self._select_destination)
        self.destination_button.grid(row=1, column=2, padx=4, pady=4)

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=12, pady=8)

        self.start_button = ttk.Button(button_frame, text="Start", command=self._start_action)
        self.start_button.pack(side="left", padx=4)

        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel_action)
        self.cancel_button.pack(side="left", padx=4)
        self.cancel_button.configure(state="disabled")

        progress_frame = ttk.LabelFrame(self.root, text="Progress")
        progress_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.progress_bar = ttk.Progressbar(progress_frame, maximum=100.0, variable=self.progress_var)
        self.progress_bar.pack(fill="x", padx=8, pady=8)

        self.status_label = ttk.Label(progress_frame, textvariable=self.status_var, wraplength=500, justify="left")
        self.status_label.pack(fill="x", padx=8, pady=8)

    # ------------------------------------------------------------------ HELPERS
    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _post(self, action: str, *args) -> None:
        self._ui_queue.put((action, args))

    def _process_ui_queue(self) -> None:
        while True:
            try:
                action, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            else:
                getattr(self, f"_handle_{action}")(*args)
        self.root.after(100, self._process_ui_queue)

    def _handle_status(self, message: str) -> None:
        self._set_status(message)

    def _handle_progress(self, value: float) -> None:
        self.progress_var.set(value)

    def _reset_progress(self) -> None:
        self.progress_var.set(0.0)

    def _update_widget_state(self) -> None:
        mode = self.mode_var.get()
        is_sender = mode == "sender"

        self.host_entry.configure(state="normal" if is_sender else "disabled")
        self.check_button.configure(state="normal" if is_sender else "disabled")
        self.file_entry.configure(state="normal" if is_sender else "disabled")
        self.browse_button.configure(state="normal" if is_sender else "disabled")

        self.destination_entry.configure(state="disabled" if is_sender else "normal")
        self.destination_button.configure(state="disabled" if is_sender else "normal")

        if is_sender:
            self.status_var.set("Select a file and click Start to send.")
        else:
            self.status_var.set("Choose a destination folder and click Start to listen.")

    def _get_port(self) -> Optional[int]:
        try:
            port = int(self.port_var.get())
            if not (0 < port < 65536):
                raise ValueError
            return port
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a port number between 1 and 65535.")
            return None

    # ------------------------------------------------------------------ EVENT HANDLERS
    def _check_connection(self) -> None:
        port = self._get_port()
        if port is None:
            return

        host = self.host_var.get().strip()
        if not host:
            messagebox.showerror("Invalid Host", "Please provide a host name or IP address.")
            return

        self._set_status("Checking connection...")

        def worker() -> None:
            success, message = network.check_connection(host, port)
            self._post("status", message)

        threading.Thread(target=worker, daemon=True).start()

    def _select_file(self) -> None:
        file_path = filedialog.askopenfilename(title="Select file to send")
        if file_path:
            self.file_var.set(file_path)

    def _select_destination(self) -> None:
        directory = filedialog.askdirectory(title="Select destination folder", mustexist=True)
        if directory:
            self.destination_var.set(directory)

    def _start_action(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            messagebox.showinfo("Transfer in progress", "Please wait for the current operation to finish or cancel it.")
            return

        port = self._get_port()
        if port is None:
            return

        mode = self.mode_var.get()
        self._stop_event = threading.Event()
        self._post("progress", 0.0)

        if mode == "sender":
            file_path = self.file_var.get()
            host = self.host_var.get().strip()
            if not host:
                messagebox.showerror("Missing Host", "Enter the receiver's host name or IP address.")
                return
            if not file_path:
                messagebox.showerror("Missing File", "Choose a file to send.")
                return
            if not os.path.exists(file_path):
                messagebox.showerror("File Not Found", "The selected file no longer exists.")
                return

            self._set_status("Connecting to receiver...")
            self._disable_controls()
            self._worker_thread = threading.Thread(
                target=self._send_worker,
                args=(host, port, file_path, self._stop_event),
                daemon=True,
            )
            self._worker_thread.start()
        else:
            destination = self.destination_var.get()
            if not destination:
                messagebox.showerror("Missing Destination", "Select a folder to store the received file.")
                return

            self._set_status("Waiting for sender...")
            self._disable_controls()
            self._worker_thread = threading.Thread(
                target=self._receive_worker,
                args=(port, destination, self._stop_event),
                daemon=True,
            )
            self._worker_thread.start()

    def _cancel_action(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._set_status("Cancellation requested. Waiting for the current operation to stop...")
        else:
            self._set_status("Nothing to cancel.")

    # ------------------------------------------------------------------ WORKER MANAGEMENT
    def _disable_controls(self) -> None:
        for widget in (
            self.host_entry,
            self.port_entry,
            self.check_button,
            self.file_entry,
            self.browse_button,
            self.destination_entry,
            self.destination_button,
            self.start_button,
        ):
            widget.configure(state="disabled")
        self.cancel_button.configure(state="normal")

    def _enable_controls(self) -> None:
        self.port_entry.configure(state="normal")
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

        if self.mode_var.get() == "sender":
            self.host_entry.configure(state="normal")
            self.check_button.configure(state="normal")
            self.file_entry.configure(state="normal")
            self.browse_button.configure(state="normal")
            self.destination_entry.configure(state="disabled")
            self.destination_button.configure(state="disabled")
        else:
            self.host_entry.configure(state="disabled")
            self.check_button.configure(state="disabled")
            self.file_entry.configure(state="disabled")
            self.browse_button.configure(state="disabled")
            self.destination_entry.configure(state="normal")
            self.destination_button.configure(state="normal")

    def _send_worker(self, host: str, port: int, file_path: str, stop_event: threading.Event) -> None:
        try:
            def on_progress(bytes_sent: int, total_bytes: int) -> None:
                percent = (bytes_sent / total_bytes * 100) if total_bytes else 0.0
                self._post("progress", percent)

            def on_status(message: str) -> None:
                self._post("status", message)

            network.send_file(
                host,
                port,
                file_path,
                progress_callback=on_progress,
                status_callback=on_status,
                stop_event=stop_event,
            )
        except Exception as exc:  # pragma: no cover - GUI feedback path
            self._post("status", f"Error: {exc}")
        finally:
            self._post("finish", "")

    def _receive_worker(self, port: int, destination: str, stop_event: threading.Event) -> None:
        try:
            def on_progress(bytes_received: int, total_bytes: int) -> None:
                percent = (bytes_received / total_bytes * 100) if total_bytes else 0.0
                self._post("progress", percent)

            def on_status(message: str) -> None:
                self._post("status", message)

            network.receive_file(
                port,
                destination,
                progress_callback=on_progress,
                status_callback=on_status,
                stop_event=stop_event,
            )
        except Exception as exc:  # pragma: no cover - GUI feedback path
            self._post("status", f"Error: {exc}")
        finally:
            self._post("finish", "")

    def _handle_finish(self, _message: str) -> None:
        self._worker_thread = None
        self._enable_controls()
        current_status = self.status_var.get()
        lowered = current_status.lower()
        if any(keyword in lowered for keyword in ("error", "cancel")):
            return

        ready_message = "Ready to send another file." if self.mode_var.get() == "sender" else "Ready to receive another file."
        if current_status:
            self.status_var.set(f"{current_status}\n{ready_message}")
        else:
            self.status_var.set(ready_message)

    # ------------------------------------------------------------------ PUBLIC API
    def run(self) -> None:
        self.root.mainloop()


def launch_app() -> None:
    """Entry point used by ``main.py``."""
    root = tk.Tk()
    app = FileTransferApp(root)
    app.run()


__all__ = ["launch_app", "FileTransferApp"]
