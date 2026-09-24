# Project Inventory & Full Cleanup Guide

This document maintains an exact inventory of every file, directory, tool, driver, and download associated with this project—both **inside** the project repository and **outside** across the system—so that you can audit everything or wipe all traces with 100% precision.

---

## 1. Everything INSIDE the Project Directory
**Path:** `C:\Users\arepe\Desktop\Teamspeak AI chatbot\`

| File / Folder | Purpose | Safe to Delete? |
| :--- | :--- | :--- |
| `.venv\` | Python 3.12 isolated virtual environment (managed by `uv`). Contains installed Python wheels (`sounddevice`, `numpy`, `scipy`, `faster-whisper`, `requests`, `edge-tts`, `av`). | Yes (can be deleted and re-created anytime) |
| `.git\` | Local git history tracking all changes and preservation commits. | Yes (removes version control) |
| `bot.py` | Main voice bot implementation. | Project Core |
| `capture_clip.py` | Audio capture and level testing utility. | Project Core |
| `test_bot.py` | Unit tests for bot logic. | Project Core |
| `test_capture_clip.py` | Unit tests for audio capture. | Project Core |
| `README.md` | Original project notes and requirements. | Project Core |
| `MASTER-PLAN.md` | Complete architectural specification and phase gate definitions. | Project Core |
| `MASTER-PLAN-PROGRESS.md` | Execution log of actions, findings, tests, and progress. | Project Core |
| `PROJECT-INVENTORY-AND-CLEANUP.md` | This exact inventory and cleanup guide. | Project Core |

---

## 2. Everything OUTSIDE the Project Directory

### 2.1 Downloaded Installers (`C:\Users\arepe\Downloads\`)
| Path | Description | How to Delete |
| :--- | :--- | :--- |
| `C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43.zip` | VB-CABLE driver package zip. | `Remove-Item "C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43.zip"` |
| `C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43\` | Extracted folder containing VB-CABLE driver setup. | `Remove-Item -Recurse -Force "C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43"` |
| `C:\Users\arepe\Downloads\VoicemeeterSetup_v1130.zip` | Voicemeeter installer zip. | `Remove-Item "C:\Users\arepe\Downloads\VoicemeeterSetup_v1130.zip"` |
| `C:\Users\arepe\Downloads\TeamSpeak3-Client-win64-3.6.2.exe` | Official TeamSpeak 3 Client installer. | `Remove-Item "C:\Users\arepe\Downloads\TeamSpeak3-Client-win64-3.6.2.exe"` |

### 2.2 Extracted Applications & Temporary Folders
| Path | Description | How to Delete |
| :--- | :--- | :--- |
| `C:\Users\arepe\AppData\Roaming\TeamSpeak_Bot\` | Temporary test profile directory created during TS6 instance test. | `Remove-Item -Recurse -Force "C:\Users\arepe\AppData\Roaming\TeamSpeak_Bot"` |
| `C:\Users\arepe\AppData\Local\Temp\hermes_test_scratch\` | Temporary audio scratch directory used by unit tests. | `Remove-Item -Recurse -Force "C:\Users\arepe\AppData\Local\Temp\hermes_test_scratch"` |
| `C:\Users\arepe\.gemini\antigravity\brain\0214d150-d514-4212-96fc-31dca160553c\` | Agent workspace scratch scripts, inspection logs, and session artifacts. | Managed automatically by Antigravity / can be wiped. |

### 2.3 System Software & Drivers (Windows Level)
| Software / Driver | Location / Component | How to Uninstall |
| :--- | :--- | :--- |
| **TeamSpeak 3 Client** | `C:\Users\arepe\AppData\Local\Programs\TeamSpeak 3 Client\` | Run uninstaller: `"C:\Users\arepe\AppData\Local\Programs\TeamSpeak 3 Client\uninstall.exe"` or via Windows Settings -> Installed Apps. |
| **VB-Audio Voicemeeter** | `C:\Program Files (x86)\VB\Voicemeeter\` | Open **Windows Settings -> Apps -> Installed Apps**, search for `Voicemeeter`, click **Uninstall** (or run `C:\Program Files (x86)\VB\Voicemeeter\voicemeetersetup.exe -u`). |
| **VB-Audio Virtual Cable (VB-CABLE)** | Kernel audio endpoints: `CABLE Input`, `CABLE Output` | Run `C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43\VBCABLE_Setup_x64.exe` as Admin and click **"Remove Driver"**, or uninstall from **Windows Settings -> Installed Apps**. |
| **TeamSpeak 6 Client** | `C:\Users\arepe\AppData\Local\Programs\TeamSpeak\` | Your primary existing client. *Do not delete unless you no longer want TeamSpeak on this PC.* |

---

## 3. Total Wipeout: Single-Command Full Cleanup Script

If at any point you wish to remove **EVERYTHING** created for this project outside and inside, run this in PowerShell:

```powershell
# 1. Remove external downloads and extracted directories
Remove-Item -Path "C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43.zip" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path "C:\Users\arepe\Downloads\VBCABLE_Driver_Pack43" -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\arepe\Downloads\VoicemeeterSetup_v1130.zip" -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\arepe\Downloads\TeamSpeak3-Client-win64-3.6.2.exe" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path "C:\Users\arepe\AppData\Local\Programs\TeamSpeak3_Bot" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path "C:\Users\arepe\AppData\Roaming\TeamSpeak_Bot" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path "C:\Users\arepe\AppData\Local\Temp\hermes_test_scratch" -ErrorAction SilentlyContinue

# 2. To remove the project virtual environment:
# Remove-Item -Recurse -Force "C:\Users\arepe\Desktop\Teamspeak AI chatbot\.venv"

# 3. Note on drivers:
# Windows requires drivers (Voicemeeter, VB-CABLE) to be uninstalled via Windows Settings > Installed Apps.
```
