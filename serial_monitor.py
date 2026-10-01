#!/usr/bin/env python3
"""ESP32-S3 USB Serial/JTAG monitor.

Prints device output to the screen and appends it to <ID>.log (in
Documents/Sonicu Serial Logs), with a UTC timestamp on every line. Works on
Windows and macOS, as a plain script or as a double-clickable app built by
build_mac.sh / build_windows.bat.

Unplugging and replugging the device does not stop monitoring: the device is
tracked by its USB serial number (the chip's MAC address), so it is found again
even if the OS gives it a different port name.

Requires: python -m pip install pyserial
"""

import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is not installed. Run:  python -m pip install pyserial")

ESPRESSIF_VID = 0x303A
USB_JTAG_PID = 0x1001
BAUD = 115200  # ignored by USB Serial/JTAG, but pyserial needs a value
POLL_INTERVAL_S = 0.1
WAIT_FOR_DEVICE_S = 15 * 60
RECONNECT_SETTLE_S = 0.5  # let the OS finish enumerating a replugged device
PARTIAL_LINE_FLUSH_S = 0.5  # emit text with no trailing newline after this much quiet
PRESENCE_CHECK_S = 1.0  # while idle, confirm the device is still plugged in

LOG_FOLDER_NAME = "Sonicu Serial Logs"
ID_PATTERN = re.compile(r"^[A-Za-z0-9]{4,6}$")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


class Logger:
    """Writes timestamped lines to both the screen and the log file."""

    def __init__(self, path):
        self.file = open(path, "a", encoding="utf-8")

    def line(self, text):
        stamp = f"[{timestamp()}] "
        # Screen keeps the device's colors; reset at end of line so a color
        # never bleeds into the next timestamp. The file gets plain text.
        print(stamp + text + ("\x1b[0m" if "\x1b" in text else ""), flush=True)
        self.file.write(stamp + ANSI_ESCAPE.sub("", text) + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


def decode(raw):
    return raw.decode("utf-8", errors="replace").rstrip("\r")


def enable_windows_colors():
    """Turn on ANSI color handling in the classic Windows console."""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING


def documents_folder():
    if sys.platform == "win32":
        # Ask Windows, since Documents is often redirected to OneDrive.
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # CSIDL_PERSONAL
            return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")


def log_folder():
    try:
        folder = os.path.join(documents_folder(), LOG_FOLDER_NAME)
        os.makedirs(folder, exist_ok=True)
    except OSError:
        # e.g. the user declined macOS's "access your Documents folder" prompt
        folder = os.path.join(os.path.expanduser("~"), LOG_FOLDER_NAME)
        os.makedirs(folder, exist_ok=True)
    return folder


def pause_if_double_clicked():
    """A double-clicked app's window closes on exit; keep it open so messages can be read."""
    if getattr(sys, "frozen", False):
        try:
            input("\nPress Enter to close this window...")
        except (KeyboardInterrupt, EOFError):
            pass


# ---------------------------------------------------------------- prompts

def yes_no(prompt):
    while True:
        answer = input(f"{prompt} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def prompt_device_id():
    while True:
        device_id = input("Enter the last 4-6 digits of the device: ").strip()
        if ID_PATTERN.match(device_id):
            return device_id
        print("Please enter 4 to 6 letters or digits.")


def get_log_path(folder):
    while True:
        log_name = f"{prompt_device_id()}.log"
        if yes_no(f"This will log to the file name {log_name} is that right?"):
            return os.path.join(folder, log_name)


# ---------------------------------------------------------------- devices

def find_esp32s3_ports():
    ports = []
    for p in list_ports.comports():
        if p.vid != ESPRESSIF_VID:
            continue
        # macOS exposes each device as both /dev/cu.* and /dev/tty.*; use cu.
        if sys.platform == "darwin" and p.device.startswith("/dev/tty."):
            continue
        ports.append(p)
    return sorted(ports, key=lambda p: p.device)


def describe(port):
    kind = "USB Serial/JTAG" if port.pid == USB_JTAG_PID else f"USB PID 0x{port.pid:04X}"
    return f"{port.device}  ({kind}, serial {port.serial_number or 'unknown'})"


def wait_for_any_device(timeout_s):
    print(f"Waiting up to {timeout_s // 60} minutes for an ESP32-S3 to show up (Ctrl+C to quit)...")
    deadline = time.monotonic() + timeout_s
    next_status = time.monotonic() + 60
    while time.monotonic() < deadline:
        if find_esp32s3_ports():
            time.sleep(RECONNECT_SETTLE_S)
            return find_esp32s3_ports()
        if time.monotonic() >= next_status:
            minutes_left = round((deadline - time.monotonic()) / 60)
            print(f"  still waiting... about {minutes_left} minute(s) left")
            next_status += 60
        time.sleep(POLL_INTERVAL_S)
    return []


def choose_device(ports):
    if len(ports) == 1:
        print(f"Found ESP32-S3: {describe(ports[0])}")
        return ports[0]
    print(f"Found {len(ports)} ESP32-S3 devices:")
    for i, p in enumerate(ports, 1):
        print(f"  {i}. {describe(p)}")
    while True:
        choice = input(f"Select the device to monitor (1-{len(ports)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(ports):
            return ports[int(choice) - 1]
        print("Invalid selection.")


def find_port(device_serial, port_name):
    """Current port name of the monitored device, or None if it is not plugged in."""
    for p in find_esp32s3_ports():
        if device_serial:
            if p.serial_number == device_serial:
                return p.device
        elif p.device == port_name:
            return p.device
    return None


def open_port(port_name):
    ser = serial.Serial()
    ser.port = port_name
    ser.baudrate = BAUD
    ser.timeout = POLL_INTERVAL_S
    # The ESP32-S3's USB Serial/JTAG resets the chip when RTS is high while DTR
    # is low, so opening the port must never pass through that state.
    if sys.platform == "win32":
        # Windows applies both lines at once on open, so start them low.
        ser.dtr = False
        ser.rts = False
        ser.open()
    else:
        # macOS raises both lines on open and pyserial would drop DTR first
        # (-> reset). Leave them high, then drop RTS before DTR.
        ser.open()
        ser.rts = False
        ser.dtr = False
    return ser


def open_when_present(device_serial, port_name, settle_s=0.0):
    """Block until the device is plugged in and its port opens."""
    reported = False
    while True:
        current = find_port(device_serial, port_name)
        if current:
            time.sleep(settle_s)
            try:
                return open_port(current)
            except (serial.SerialException, OSError) as e:
                if not reported:
                    print(f"Can't open {current} yet ({e}). Is another program using it? Retrying...")
                    reported = True
        time.sleep(POLL_INTERVAL_S)


# ---------------------------------------------------------------- monitor

def monitor(port, logger):
    device_serial, port_name = port.serial_number, port.device
    ser = open_when_present(device_serial, port_name)
    logger.line(f"===== Session started | port {ser.port} | device {device_serial or 'unknown'} =====")

    buffer = b""
    last_rx = last_presence_check = time.monotonic()
    try:
        while True:
            try:
                data = ser.read(ser.in_waiting or 1)
                now = time.monotonic()
                if not data and now - last_presence_check >= PRESENCE_CHECK_S:
                    last_presence_check = now
                    if find_port(device_serial, port_name) != ser.port:
                        raise serial.SerialException("device no longer present")
            except (serial.SerialException, OSError):
                if buffer:
                    logger.line(decode(buffer))
                    buffer = b""
                try:
                    ser.close()
                except Exception:
                    pass
                logger.line("*** Device disconnected - waiting for it to reconnect... ***")
                ser = open_when_present(device_serial, port_name, RECONNECT_SETTLE_S)
                logger.line(f"*** Device reconnected on {ser.port} ***")
                last_rx = last_presence_check = time.monotonic()
                continue

            if data:
                buffer += data
                last_rx = now
                *lines, buffer = buffer.split(b"\n")
                for raw in lines:
                    logger.line(decode(raw))
            elif buffer and now - last_rx >= PARTIAL_LINE_FLUSH_S:
                logger.line(decode(buffer))
                buffer = b""
    finally:
        if buffer:
            logger.line(decode(buffer))
        logger.line("*** Monitoring stopped ***")
        ser.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # don't crash on odd bytes in a Windows console
    if sys.platform == "win32":
        enable_windows_colors()

    folder = log_folder()
    print("Sonicu Serial Monitor")
    print(f"Logs are saved in: {folder}\n")
    log_path = get_log_path(folder)

    ports = find_esp32s3_ports()
    if not ports:
        if not yes_no("No device present. Do you want me to wait for 15 minutes to see if a device shows up?"):
            return 0
        ports = wait_for_any_device(WAIT_FOR_DEVICE_S)
        if not ports:
            print("No device showed up within 15 minutes. Exiting.")
            return 1

    port = choose_device(ports)
    print(f"Logging to {log_path}  (press Ctrl+C to stop)")
    logger = Logger(log_path)
    try:
        monitor(port, logger)
    finally:
        logger.close()


if __name__ == "__main__":
    try:
        exit_code = main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        exit_code = 0
    except Exception:
        traceback.print_exc()
        exit_code = 1
    pause_if_double_clicked()
    sys.exit(exit_code)
