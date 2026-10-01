# sonicu-serial-monitor

Monitors an ESP32-S3 over its built-in USB Serial/JTAG port, printing output to the
screen and appending it to `<ID>.log` with a UTC timestamp on every line
(e.g. `[2026-09-30 19:45:01.123Z]`). Unplugging and replugging the device does not
stop monitoring.

Logs are saved in **Documents › Sonicu Serial Logs** (the full path is shown when
the program starts).

## For users: download and run

Get the latest version from this repo's **Releases** page. No install, Python or
drivers needed.

**Windows** — download `Sonicu-Serial-Monitor-windows.exe` and double-click it.
The first time, Windows may say *"Windows protected your PC"*: click
**More info → Run anyway**.

**Mac** — download the zip for your Mac (`mac-arm64` for Apple M1/M2/M3/M4,
`mac-x86_64` for older Intel Macs; check  › About This Mac), then double-click the
zip to unpack it and double-click **Sonicu Serial Monitor**. The first time, macOS
blocks it because it isn't from the App Store:
1. Click **Done** on the warning.
2. Open **System Settings › Privacy & Security**, scroll down, click **Open Anyway**.
3. If asked, allow Terminal to access your Documents folder (that's where logs go).

Then:
1. Enter the last 4-6 characters of the device ID and confirm the log file name.
2. If several ESP32-S3s are plugged in, pick one by number. If none are, you can
   choose to wait up to 15 minutes for one to appear.
3. Press **Ctrl+C** to stop.

Only one program can use the port at a time, so close other serial monitors
(Arduino IDE, `idf.py monitor`, etc.) first.

## For developers

Run from source (Python 3.8+):

```sh
python -m pip install -r requirements.txt
python serial_monitor.py
```

### Releasing

GitHub Actions (`.github/workflows/release.yml`) builds the Windows `.exe` and both
Mac versions on every push to `master`. To publish a release, tag and push:

```sh
git tag v1.0.0
git push origin v1.0.0
```

A few minutes later the Release appears with all three downloads attached.

### Building locally

- Mac: `./build_mac.sh` → `dist/Sonicu-Serial-Monitor-mac-<arch>.zip` (builds for
  the CPU of the Python used; see the script for building Intel on Apple Silicon).
- Windows: double-click `build_windows.bat` → `dist\windows\Sonicu Serial Monitor.exe`.

A Mac can't build the Windows `.exe` or vice versa.
