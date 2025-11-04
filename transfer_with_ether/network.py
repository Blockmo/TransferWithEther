"""Networking utilities for TransferWithEther.

This module implements a simple file transfer protocol over TCP. It is used by the
Tkinter based GUI, but can also be imported and reused programmatically.
"""
from __future__ import annotations

import os
import socket
import struct
from pathlib import Path
from typing import Callable, Optional

# Header format: unsigned int for the filename length, unsigned long long for file size.
_HEADER_STRUCT = struct.Struct("!IQ")

ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]


def check_connection(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """Check if a TCP connection to ``host``/``port`` can be established.

    Returns a tuple with ``(is_connected, message)``.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"Successfully connected to {host}:{port}."
    except OSError as exc:  # pragma: no cover - network errors vary by platform
        return False, f"Connection failed: {exc}"  # type: ignore[str-bytes-safe]


def get_local_ip_addresses(include_loopback: bool = True) -> list[str]:
    """Return IPv4 addresses associated with the current host.

    The list is deduplicated and sorted so that non-loopback addresses are
    preferred. The loopback address (``127.0.0.1``) can optionally be removed.
    """

    addresses: set[str] = set()

    try:
        hostname = socket.gethostname()
        _name, _alias, host_ips = socket.gethostbyname_ex(hostname)
        addresses.update(ip for ip in host_ips if ip)
    except socket.gaierror:
        pass

    try:
        # Attempt to determine the default outbound IP address.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass

    if include_loopback:
        addresses.add("127.0.0.1")
    else:
        addresses.discard("127.0.0.1")

    # Filter out malformed entries and sort, prioritising non-loopback values.
    valid_addresses = [ip for ip in addresses if ip.count(".") == 3]
    return sorted(valid_addresses, key=lambda value: (value.startswith("127."), value))
def _send_all(sock: socket.socket, data: bytes) -> None:
    """Send all bytes to the socket, retrying on interruptions."""
    view = memoryview(data)
    while view:
        sent = sock.send(view)
        view = view[sent:]


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    """Receive exactly ``size`` bytes from ``sock``."""
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Connection closed before enough data was received")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_file(
    host: str,
    port: int,
    file_path: os.PathLike[str] | str,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    status_callback: Optional[StatusCallback] = None,
    chunk_size: int = 64 * 1024,
    stop_event: Optional["threading.Event"] = None,
) -> None:
    """Send ``file_path`` to ``host``/``port``.

    ``progress_callback`` receives ``(bytes_sent, total_bytes)``.
    ``status_callback`` receives human readable status messages.
    ``stop_event`` can be provided to abort the transfer.
    """
    import threading

    if stop_event is None:
        stop_event = threading.Event()

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    file_size = file_path.stat().st_size
    filename_bytes = file_path.name.encode("utf-8")

    if status_callback:
        status_callback("Connecting to receiver...")
    with socket.create_connection((host, port)) as sock:
        header = _HEADER_STRUCT.pack(len(filename_bytes), file_size)
        _send_all(sock, header)
        _send_all(sock, filename_bytes)

        bytes_sent = 0
        if status_callback:
            status_callback("Transferring file...")

        with file_path.open("rb") as src:
            while not stop_event.is_set():
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                _send_all(sock, chunk)
                bytes_sent += len(chunk)
                if progress_callback:
                    progress_callback(bytes_sent, file_size)

        if stop_event.is_set():
            if status_callback:
                status_callback("Transfer cancelled by user.")
        else:
            if progress_callback:
                progress_callback(file_size, file_size)
            if status_callback:
                status_callback("Transfer completed successfully.")


def receive_file(
    port: int,
    destination_dir: os.PathLike[str] | str,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    status_callback: Optional[StatusCallback] = None,
    stop_event: Optional["threading.Event"] = None,
) -> Optional[Path]:
    """Listen for an incoming file transfer on ``port``.

    ``destination_dir`` is the directory where the received file will be stored.
    Returns the path of the stored file when completed, otherwise ``None``.
    """
    import threading

    if stop_event is None:
        stop_event = threading.Event()

    destination = Path(destination_dir)
    destination.mkdir(parents=True, exist_ok=True)

    if status_callback:
        status_callback("Waiting for sender to connect...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("", port))
        server_sock.listen(1)
        server_sock.settimeout(1.0)

        while not stop_event.is_set():
            try:
                conn, addr = server_sock.accept()
                break
            except socket.timeout:
                continue
        else:
            if status_callback:
                status_callback("Listening cancelled by user.")
            return None

        if status_callback:
            status_callback(f"Connected to sender {addr[0]}:{addr[1]}. Receiving file...")

        with conn:
            header = _recv_exact(conn, _HEADER_STRUCT.size)
            name_len, file_size = _HEADER_STRUCT.unpack(header)

            filename_bytes = _recv_exact(conn, name_len)

            filename = filename_bytes.decode("utf-8", errors="replace")
            target_path = destination / filename

            bytes_received = 0
            with target_path.open("wb") as dst:
                while bytes_received < file_size and not stop_event.is_set():
                    chunk = conn.recv(min(64 * 1024, file_size - bytes_received))
                    if not chunk:
                        raise ConnectionError("Connection closed before file transfer finished")
                    dst.write(chunk)
                    bytes_received += len(chunk)
                    if progress_callback:
                        progress_callback(bytes_received, file_size)

            if stop_event.is_set():
                target_path.unlink(missing_ok=True)
                if status_callback:
                    status_callback("Transfer cancelled by user.")
                return None

            if progress_callback:
                progress_callback(file_size, file_size)
            if status_callback:
                status_callback(f"File received: {target_path}")

            return target_path
