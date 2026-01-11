# sleepwhy

`sleepwhy` is a small Linux command-line tool that explains why your system does not suspend or stay asleep. It inspects common blockers (systemd inhibitors, devices, wake sources) and summarizes which components are preventing low-power states.

## Description

`sleepwhy` analyzes your Linux system to identify what's preventing it from suspending or keeping it from staying asleep. It provides information about:

- **systemd inhibitors**: Active processes or services that are blocking suspend
- **Wake sources**: Hardware devices configured to wake the system from suspend
- **Device wake capabilities**: Information from `/proc/acpi/wakeup` and `/sys` filesystem

The tool is designed as the counterpart to `wakewhy`, focusing on current blockers and configured wake sources.

## Installation

### From Source

1. Clone or download this repository
2. Run the tool directly using Python:

```bash
python3 -m sleepwhy
```

### Making it Executable

To run `sleepwhy` as a standalone command, you can create a symlink or wrapper script:

```bash
# Create a symlink (if sleepwhy is in your PATH)
ln -s /path/to/sleepwhy/sleepwhy/__main__.py /usr/local/bin/sleepwhy
chmod +x /usr/local/bin/sleepwhy
```

Or add the repository directory to your `PATH` environment variable.

## Usage

### Basic Usage

Run `sleepwhy` without arguments to get a human-readable summary:

```bash
sleepwhy
```

Example output:
```
=== systemd Inhibitors ===
These inhibitors currently block suspend:
  • Realtime Kit (rtkit-daemon) (PID 1768, user: root)
    Reason: sleep (Demote realtime scheduling and stop canary.)
  • UPower (upowerd) (PID 2281, user: root)
    Reason: sleep (Pause device polling)

=== Wake Sources ===
These devices are configured as wake sources:
  • USB2 (enabled) - /sys/bus/usb/devices/1-1
  • XHC (enabled) - /sys/bus/usb/devices/pci0000:00/0000:00:14.0

=== Summary ===
Found 2 active inhibitor(s) blocking suspend.
Found 2 wake-enabled device(s).
```

### JSON Output

Use the `--json` flag to get structured JSON output:

```bash
sleepwhy --json
```

Example output:
```json
{
  "inhibitors": [
    {
      "who": "Realtime Kit",
      "uid": "0",
      "user": "root",
      "pid": 1768,
      "comm": "rtkit-daemon",
      "what": "sleep",
      "why": "Demote realtime scheduling and stop canary.",
      "mode": "delay"
    }
  ],
  "wake_sources": {
    "USB2": {
      "status": "enabled",
      "sysfs": "pci:0000:00:14.0"
    }
  },
  "errors": [],
  "summary": {
    "inhibitor_count": 2,
    "wake_device_count": 2
  }
}
```

### Disable Colors

Use `--no-color` to disable colored output (useful for scripts or when redirecting output):

```bash
sleepwhy --no-color > output.txt
```

### Skip systemd Checks

On systems without systemd, use `--no-systemd` to skip systemd-specific checks:

```bash
sleepwhy --no-systemd
```

## Typical Sources Explained

### systemd Inhibitors

systemd inhibitors are mechanisms that prevent the system from suspending, shutting down, or idle handling. Common inhibitors include:

- **Applications**: Programs that request to delay suspend (e.g., video players, download managers)
- **System services**: Services like `upowerd` (power management), `rtkit-daemon` (realtime kit)
- **Session managers**: Desktop environments that manage power settings

You can check inhibitors manually using:
```bash
systemd-inhibit --list
```

To remove inhibitors, you typically need to close the application or service that created them.

### USB Wake Devices

USB devices (keyboards, mice, network adapters) can be configured to wake the system. These are often listed in `/proc/acpi/wakeup` as devices like:

- `USB2`, `USB3`: USB controllers
- `XHC`, `XHC0`, `XHC1`: USB 3.0 controllers (eXtensible Host Controller)
- Individual USB devices

To disable wake on a specific device:
```bash
# Find the device in /proc/acpi/wakeup
cat /proc/acpi/wakeup

# Disable wake (replace DEVICE_NAME with actual device name)
echo DEVICE_NAME > /proc/acpi/wakeup
```

**Warning**: Editing `/proc/acpi/wakeup` requires root privileges and changes are temporary (reset on reboot).

### Network Wake (WoL)

Wake-on-LAN (WoL) allows a system to be woken by network packets. This is typically configured at the network interface level in `/sys`:

```bash
# Check WoL status for an interface
cat /sys/class/net/eth0/power/wakeup

# Common values: "disabled", "enabled"
```

Network wake is not directly reported by `sleepwhy` but may be visible in the `/sys` device wake sources.

## Limitations

- **systemd dependency**: systemd-specific features (inhibitor detection) require systemd and the `systemd-inhibit` command. Use `--no-systemd` on non-systemd systems.

- **ACPI wakeup file**: `/proc/acpi/wakeup` is not available on all systems (particularly newer systems using ACPI 6.x). The tool will gracefully skip this source if unavailable.

- **Read-only**: `sleepwhy` only reads system interfaces and does not modify any configuration. It is purely informational.

- **Permissions**: Some information may require root privileges to access (e.g., reading certain `/sys` files). The tool handles permission errors gracefully.

- **Kernel-specific**: Wake source detection depends on kernel interfaces that may vary between kernel versions.

## Requirements

- Python 3.6 or higher
- Linux system (tested on systemd-based distributions)
- Standard Python library only (uses `subprocess` for system commands)

## License

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See the [LICENSE](LICENSE) file for details.

## See Also

- `wakewhy`: Tool to analyze why a system woke up from suspend
- `systemd-inhibit`: Manual tool to create and list systemd inhibitors
- `/proc/acpi/wakeup`: Kernel interface for ACPI wakeup device configuration
