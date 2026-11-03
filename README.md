# Globe AT HOME 5G WIFI (rain101 / the101): Full Openline & Root Access

[Quick Start](#quick-start) &nbsp;|&nbsp; [Supported Device](#supported-device--requirements) &nbsp;|&nbsp; [Advanced Guide](docs/ADVANCED.md) &nbsp;|&nbsp; [Security Audit](docs/AUDIT.md) &nbsp;|&nbsp; [Issues](../../issues)

Unlock your **Globe AT HOME 5G WIFI (rain101 / the101)** router for any SIM and remove the carrier's remote control and hidden backdoors, using a single command from an Android phone, Mac, Linux, or Windows.

---

## Quick Start

**📱 Android / 🍎 Mac / 🐧 Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/jobrac/openline-101/main/install.sh | sh
```

**🪟 Windows** (PowerShell)

```powershell
irm https://raw.githubusercontent.com/jobrac/openline-101/main/install.ps1 | iex
```

Then just three things:

1. Connect to the router's **Wi-Fi** and turn **mobile data OFF**.
2. Have your **admin password** ready; it's on the sticker under the router.
3. Run the line above and follow the prompt. It ends with 🎉 when done.

> **Android:** install [Termux from F-Droid](https://f-droid.org/packages/com.termux/) and run `pkg install -y python` once, first.

---

## Supported Device & Requirements

| | |
|---|---|
| **Device** | Globe AT HOME 5G WIFI (rain101 / the101), hardware V1.0 |
| **Firmware** | `RA_M1_v7.00.02g` |

The only thing the tool needs is **Python 3.6+**:

| Platform | Python |
|---|---|
| 🐧 **Linux** | Already installed on most distros. If not: `sudo apt install python3` (Debian/Ubuntu) or your package manager's equivalent. |
| 🍎 **Mac** | Already installed. If not: `brew install python` or get it from [python.org](https://www.python.org/downloads/). |
| 📱 **Android** | Install [Termux from F-Droid](https://f-droid.org/packages/com.termux/), then run `pkg install -y python` once. |
| 🪟 **Windows** | Optional. If you don't have Python, the command above **auto-downloads a prebuilt `openline.exe`** so you don't need to install anything. |

You don't need to check the firmware yourself; the script auto-detects it and **stops safely before changing anything** if it's not the supported device.

---

## More details

- **[Advanced Guide →](docs/ADVANCED.md)**: command-line options, manual API, recovery, reverting, rebuilding.
- **[Security & Audit Reference →](docs/AUDIT.md)**: exactly what it changes on the device and how to verify every claim.

_Screenshots and a short demo coming soon._

---

## Credits

- **PHCorner community**: firmware dumps and early analysis.
- **DeepSeek**: AI model used during reverse engineering and Lua patching.
- **The OpenWRT project**: the router's base OS and the ubus/LuCI architecture that made this possible.
