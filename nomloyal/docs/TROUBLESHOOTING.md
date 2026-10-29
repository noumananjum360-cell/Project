# Troubleshooting

## Building (build.bat)
| Problem | Fix |
|---|---|
| "Python 3.11 or 3.12 was not found" | Install Python 3.12 from python.org, tick *Add python.exe to PATH*, run again. Python 3.13 is not supported by the pinned Qt version. |
| pip errors / timeouts | Check the internet connection or proxy; run again. Delete `.venv` if it is half-installed. |
| Tests failed | The build stops on purpose. Read the failing test name; send the output to support. |
| "Access is denied" during build | Close `NomLoyal.exe` (also check the system tray) and run again. |
| Antivirus deletes NomLoyal.exe | Add an exception for the project folder; PyInstaller programs are sometimes flagged. |
| Self-test failed | The message is printed; usually a missing package - delete `.venv` and build again. |

## Running
| Problem | Fix |
|---|---|
| Forgot the Admin password | Another Admin can reset it under Staff. If there is no other Admin, restore a backup or contact Devnom. |
| "Too many failed attempts" | Wait 5 minutes. |
| The window locks itself | Auto-lock after inactivity (Store settings > Security). Unlock with your password. |
| Customer not found at the till | Check the loyalty ID / phone; QR scanners must be in keyboard mode and send Enter. |
| Camera does not connect | Use Test connection. USB: try index 0, 1, 2. RTSP: check IP, user, password, and use the sub-stream URL. The app works without a camera. |
| No Windows notifications | Check Store settings > Alerts and Windows Focus Assist. Failures are logged and stored on the alert. |
| "Database created by a newer NomLoyal" | Install the newer program version. |
| Something else | Help & About > Diagnostics, and send `logs\nomloyal.log`. |
