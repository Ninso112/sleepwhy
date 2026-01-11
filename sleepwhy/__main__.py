#!/usr/bin/env python3
# sleepwhy - A tool to explain why a Linux system cannot suspend or stay asleep.
#
# Copyright (C) 2024  sleepwhy contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import json
import os
import re
import subprocess
import sys


def get_systemd_inhibitors(no_systemd=False):
    """Query systemd inhibitors via systemd-inhibit --list. Returns list of dicts."""
    if no_systemd:
        return []
    
    try:
        result = subprocess.run(
            ['systemd-inhibit', '--list'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []
        
        inhibitors = []
        lines = result.stdout.strip().split('\n')
        
        if len(lines) < 2:
            return inhibitors
        
        # Parse header to find column positions
        header = lines[0]
        # Find positions of column headers (they are separated by 2+ spaces)
        # Format: WHO            UID  USER  PID  COMM          WHAT     WHY                                                                     MODE
        header_parts = re.split(r'\s{2,}', header.strip())
        
        # Try to find column boundaries by looking for the headers
        col_starts = []
        col_names = ['WHO', 'UID', 'USER', 'PID', 'COMM', 'WHAT', 'WHY', 'MODE']
        for col_name in col_names:
            pos = header.find(col_name)
            if pos >= 0:
                col_starts.append((col_name, pos))
        
        # Parse data lines
        for line in lines[1:]:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            
            # If we found column positions, use them
            if col_starts:
                def get_field(start_idx, end_idx=None):
                    if end_idx is None:
                        end_idx = len(line)
                    start_pos = col_starts[start_idx][1] if start_idx < len(col_starts) else len(line)
                    end_pos = col_starts[start_idx + 1][1] if start_idx + 1 < len(col_starts) else len(line)
                    return line[start_pos:end_pos].strip()
                
                try:
                    who = get_field(0, 1) if len(col_starts) > 0 else ''
                    uid = get_field(1, 2) if len(col_starts) > 1 else ''
                    user = get_field(2, 3) if len(col_starts) > 2 else ''
                    pid_str = get_field(3, 4) if len(col_starts) > 3 else ''
                    pid = int(pid_str) if pid_str and pid_str.isdigit() else None
                    comm = get_field(4, 5) if len(col_starts) > 4 else ''
                    what = get_field(5, 6) if len(col_starts) > 5 else ''
                    why = get_field(6, 7) if len(col_starts) > 6 else ''
                    mode = get_field(7) if len(col_starts) > 7 else ''
                except IndexError:
                    # Fallback to simple splitting
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) >= 8:
                        who = parts[0]
                        uid = parts[1]
                        user = parts[2]
                        pid = int(parts[3]) if parts[3].isdigit() else None
                        comm = parts[4]
                        what = parts[5]
                        why = ' '.join(parts[6:-1])
                        mode = parts[-1]
                    else:
                        continue
            else:
                # Fallback: split on 2+ spaces
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 8:
                    who = parts[0]
                    uid = parts[1]
                    user = parts[2]
                    pid = parts[3] if parts[3].isdigit() else None
                    comm = parts[4]
                    what = parts[5]
                    why = ' '.join(parts[6:-1])
                    mode = parts[-1]
                else:
                    continue
            
            inhibitors.append({
                'who': who,
                'uid': uid,
                'user': user,
                'pid': pid,
                'comm': comm,
                'what': what,
                'why': why,
                'mode': mode
            })
        
        return inhibitors
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def parse_wakeup_devices():
    """Parse /proc/acpi/wakeup. Returns dict of device -> status."""
    wakeup_file = '/proc/acpi/wakeup'
    devices = {}
    
    try:
        with open(wakeup_file, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Device'):
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                device_name = parts[0]
                status_str = parts[2] if len(parts) > 2 else ''
                sysfs_node = ' '.join(parts[3:]) if len(parts) > 3 else ''
                
                # Status format: *enabled or *disabled
                if status_str.startswith('*'):
                    status = status_str[1:]  # Remove *
                    devices[device_name] = {
                        'status': status,
                        'sysfs': sysfs_node
                    }
                elif status_str in ('enabled', 'disabled'):
                    devices[device_name] = {
                        'status': status_str,
                        'sysfs': sysfs_node
                    }
        
        return devices
    except (FileNotFoundError, PermissionError, IOError):
        return {}


def check_sys_wakeup_devices():
    """Check /sys for wakeup-capable devices. Returns list."""
    wakeup_devices = []
    
    # Check /sys/devices/*/power/wakeup
    sys_devices = '/sys/devices'
    try:
        for root, dirs, files in os.walk(sys_devices):
            wakeup_path = os.path.join(root, 'power', 'wakeup')
            if os.path.exists(wakeup_path):
                try:
                    with open(wakeup_path, 'r') as f:
                        status = f.read().strip()
                    if status and status != 'disabled':
                        # Get device name from path
                        device_name = os.path.basename(root)
                        wakeup_devices.append({
                            'device': device_name,
                            'status': status,
                            'path': root
                        })
                except (PermissionError, IOError):
                    continue
    except (PermissionError, OSError):
        pass
    
    return wakeup_devices


def format_human_readable(inhibitors, wake_sources, use_color=True):
    """Format output for human consumption."""
    output = []
    
    # ANSI color codes
    if use_color:
        reset = '\033[0m'
        bold = '\033[1m'
        header = '\033[1;34m'  # Bold blue
    else:
        reset = ''
        bold = ''
        header = ''
    
    # Inhibitors section
    output.append(f"{header}=== systemd Inhibitors ==={reset}")
    if inhibitors:
        output.append(f"{bold}These inhibitors currently block suspend:{reset}")
        for inh in inhibitors:
            pid_info = f"PID {inh.get('pid')}" if inh.get('pid') else ""
            user_info = f"user: {inh.get('user', '')}" if inh.get('user') else ""
            comm_info = f"({inh.get('comm', '')})" if inh.get('comm') else ""
            info_parts = [p for p in [pid_info, user_info] if p]
            info_str = f" ({', '.join(info_parts)})" if info_parts else ""
            comm_str = f" {comm_info}" if comm_info else ""
            output.append(f"  • {inh.get('who', 'Unknown')}{comm_str}{info_str}")
            if inh.get('what') or inh.get('why'):
                what = inh.get('what', '')
                why = inh.get('why', '')
                if why:
                    output.append(f"    Reason: {what} ({why})")
                else:
                    output.append(f"    Reason: {what}")
    else:
        output.append("No active inhibitors found.")
    
    output.append("")
    
    # Wake sources section
    output.append(f"{header}=== Wake Sources ==={reset}")
    enabled_wake_sources = []
    
    # From /proc/acpi/wakeup
    for device, info in wake_sources.get('proc_acpi', {}).items():
        if info.get('status') == 'enabled':
            enabled_wake_sources.append((device, info.get('sysfs', '')))
    
    # From /sys
    for dev in wake_sources.get('sys_devices', []):
        if dev.get('status') != 'disabled':
            enabled_wake_sources.append((dev.get('device', ''), dev.get('path', '')))
    
    if enabled_wake_sources:
        output.append(f"{bold}These devices are configured as wake sources:{reset}")
        for device, path in enabled_wake_sources:
            if path:
                output.append(f"  • {device} (enabled) - {path}")
            else:
                output.append(f"  • {device} (enabled)")
    else:
        output.append("No wake-enabled devices found.")
    
    output.append("")
    
    # Summary
    output.append(f"{header}=== Summary ==={reset}")
    output.append(f"Found {len(inhibitors)} active inhibitor(s) blocking suspend.")
    output.append(f"Found {len(enabled_wake_sources)} wake-enabled device(s).")
    
    return '\n'.join(output)


def format_json(inhibitors, wake_sources, errors):
    """Format output as JSON."""
    # Combine wake sources
    combined_wake_sources = {}
    for device, info in wake_sources.get('proc_acpi', {}).items():
        if info.get('status') == 'enabled':
            combined_wake_sources[device] = info
    
    for dev in wake_sources.get('sys_devices', []):
        if dev.get('status') != 'disabled':
            combined_wake_sources[dev.get('device', '')] = {
                'status': dev.get('status'),
                'sysfs': dev.get('path', '')
            }
    
    result = {
        'inhibitors': inhibitors,
        'wake_sources': combined_wake_sources,
        'errors': errors,
        'summary': {
            'inhibitor_count': len(inhibitors),
            'wake_device_count': len(combined_wake_sources)
        }
    }
    
    return json.dumps(result, indent=2)


def main():
    """Main entry point: parse args, collect data, output."""
    parser = argparse.ArgumentParser(
        description='Explain why a Linux system cannot suspend or stay asleep.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output structured JSON instead of human-readable text'
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    parser.add_argument(
        '--no-systemd',
        action='store_true',
        help='Skip systemd-specific checks'
    )
    
    args = parser.parse_args()
    
    errors = []
    
    # Collect inhibitors
    inhibitors = get_systemd_inhibitors(no_systemd=args.no_systemd)
    
    # Collect wake sources
    wake_sources = {}
    wake_sources['proc_acpi'] = parse_wakeup_devices()
    wake_sources['sys_devices'] = check_sys_wakeup_devices()
    
    # Output
    if args.json:
        print(format_json(inhibitors, wake_sources, errors))
    else:
        output = format_human_readable(
            inhibitors,
            wake_sources,
            use_color=not args.no_color and sys.stdout.isatty()
        )
        print(output)


if __name__ == '__main__':
    main()
