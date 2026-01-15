#!/usr/bin/env python3
"""
Holley EFI CAN Bus Parser

Parses CAN bus messages from Holley EFI systems with support for:
- ECU serial number filtering
- DBC file-based message decoding
- YAML configuration
- CLI argument parsing
- Multiple output formats (human-readable, JSON, CSV)
"""

import argparse
import sys
import yaml
import json
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, TextIO
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import defaultdict
import struct


@dataclass
class CANMessage:
    """Represents a single CAN message"""
    timestamp: float
    arbitration_id: int
    data: bytes
    is_extended: bool = True

    # Holley CAN ID structure constants
    HOLLEY_MASK = 0xFFFFF800  # Mask to get base message ID (bits 31:11)
    SERIAL_MASK = 0x7FF       # Mask to get ECU serial (bits 10:0)
    CHANNEL_MASK = 0x1FFC000  # Mask to get channel index (bits 24:14)
    SOURCE_ID_MASK = 0x3800   # Mask to get source ID (bits 13:11)

    @property
    def ecu_serial(self) -> int:
        """Extract ECU serial number from arbitration ID (bits 10:0)"""
        return self.arbitration_id & self.SERIAL_MASK

    @property
    def channel_index(self) -> int:
        """Extract channel index from arbitration ID (bits 24:14)"""
        return (self.arbitration_id & self.CHANNEL_MASK) >> 14

    @property
    def source_id(self) -> int:
        """Extract source ID from arbitration ID (bits 13:11)"""
        return (self.arbitration_id & self.SOURCE_ID_MASK) >> 11

    @property
    def base_id(self) -> int:
        """Get base message ID by masking out ECU serial (for DBC lookup)"""
        return self.arbitration_id & self.HOLLEY_MASK

    @property
    def command_bit(self) -> int:
        """Extract command bit (bit 28)"""
        return (self.arbitration_id >> 28) & 0x1

    @property
    def target_id(self) -> int:
        """Extract target ID (bits 27:25)"""
        return (self.arbitration_id >> 25) & 0x7


@dataclass
class DecodedSignal:
    """Represents a decoded signal value"""
    name: str
    value: Union[int, float]
    unit: str
    raw_value: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def update_minmax(self, new_value: Union[int, float]):
        """Update min/max tracking"""
        if isinstance(new_value, (int, float)):
            if self.min_value is None or new_value < self.min_value:
                self.min_value = new_value
            if self.max_value is None or new_value > self.max_value:
                self.max_value = new_value


@dataclass
class DecodedMessage:
    """Represents a decoded CAN message"""
    timestamp: float
    arbitration_id: int
    ecu_serial: int
    channel_index: int
    message_name: str
    signals: List[DecodedSignal]


class HolleyCANParser:
    """Main parser for Holley EFI CAN bus data"""

    def __init__(self, config_path: Optional[str] = None, ecu_serial: Optional[int] = None,
                 dbc_path: Optional[str] = None):
        """
        Initialize the parser

        Args:
            config_path: Path to YAML configuration file
            ecu_serial: ECU serial number to filter (overrides config)
            dbc_path: Path to DBC file (overrides config)
        """
        self.config = self._load_config(config_path)

        # Override config with CLI arguments if provided
        if ecu_serial is not None:
            self.config['ecu_serial'] = ecu_serial
        if dbc_path is not None:
            self.config['dbc_path'] = dbc_path

        self.dbc_db = None
        if self.config.get('dbc_path'):
            self.dbc_db = self._load_dbc(self.config['dbc_path'])

        self.ecu_serial = self.config.get('ecu_serial')
        self.message_filter = self.config.get('message_filter', [])

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file"""
        default_config = {
            'ecu_serial': None,
            'dbc_path': None,
            'message_filter': [],
            'output_format': 'human',
            'decode_signals': True,
            'show_raw_data': False,
        }

        if not config_path:
            return default_config

        try:
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    default_config.update(user_config)
        except FileNotFoundError:
            print(f"Warning: Config file '{config_path}' not found, using defaults")
        except yaml.YAMLError as e:
            print(f"Warning: Error parsing config file: {e}, using defaults")

        return default_config

    def _load_dbc(self, dbc_path: str):
        """Load DBC file for message decoding"""
        try:
            import cantools
            return cantools.database.load_file(dbc_path)
        except ImportError:
            print("Warning: cantools library not installed. Install with: pip install cantools")
            print("Falling back to basic parsing without DBC decoding")
            return None
        except Exception as e:
            print(f"Warning: Error loading DBC file '{dbc_path}': {e}")
            return None

    def parse_message(self, raw_message: CANMessage) -> Optional[DecodedMessage]:
        """
        Parse and decode a single CAN message

        Args:
            raw_message: Raw CAN message to parse

        Returns:
            DecodedMessage if parsing successful, None otherwise
        """
        # Filter by ECU serial number if specified
        # Note: ecu_serial can be the full serial (>11 bits) or just lower 11 bits
        if self.ecu_serial is not None:
            ecu_serial_lower_11 = self.ecu_serial & 0x7FF
            if raw_message.ecu_serial != ecu_serial_lower_11:
                return None

        # Try to decode using DBC if available
        if self.dbc_db:
            try:
                # Use base_id (masked with 0xFFFFF800) to look up message in DBC
                message = self.dbc_db.get_message_by_frame_id(raw_message.base_id)
                decoded_data = message.decode(raw_message.data)

                signals = []
                for signal_name, value in decoded_data.items():
                    signal = message.get_signal_by_name(signal_name)
                    signals.append(DecodedSignal(
                        name=signal_name,
                        value=value,
                        unit=signal.unit or "",
                        raw_value=int(value) if isinstance(value, (int, float)) else 0
                    ))

                return DecodedMessage(
                    timestamp=raw_message.timestamp,
                    arbitration_id=raw_message.arbitration_id,
                    ecu_serial=raw_message.ecu_serial,
                    channel_index=raw_message.channel_index,
                    message_name=message.name,
                    signals=signals
                )
            except (KeyError, ValueError) as e:
                # Message not in DBC or decode error, fall through to basic parsing
                pass

        # Basic parsing without DBC
        return DecodedMessage(
            timestamp=raw_message.timestamp,
            arbitration_id=raw_message.arbitration_id,
            ecu_serial=raw_message.ecu_serial,
            channel_index=raw_message.channel_index,
            message_name=f"UNKNOWN_0x{raw_message.base_id:08X}",
            signals=[DecodedSignal(
                name="raw_data",
                value=raw_message.data.hex(),
                unit="",
                raw_value=0
            )]
        )

    def parse_candump_line(self, line: str, base_timestamp: float = 0) -> Optional[CANMessage]:
        """
        Parse a line from candump format

        Format: (timestamp) interface arbitration_id#data
        Example: (1234.567890) can0 9E005000#0100000000000000

        Args:
            line: Line to parse
            base_timestamp: Base timestamp for relative times

        Returns:
            CANMessage if parsing successful, None otherwise
        """
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        try:
            # Parse candump format: (timestamp) interface id#data
            parts = line.split()
            if len(parts) < 3:
                return None

            # Extract timestamp
            timestamp_str = parts[0].strip('()')
            timestamp = float(timestamp_str) if timestamp_str else base_timestamp

            # Extract arbitration ID and data
            msg_parts = parts[2].split('#')
            if len(msg_parts) != 2:
                return None

            arb_id = int(msg_parts[0], 16)
            data = bytes.fromhex(msg_parts[1])

            return CANMessage(
                timestamp=timestamp,
                arbitration_id=arb_id,
                data=data,
                is_extended=True
            )
        except (ValueError, IndexError) as e:
            print(f"Warning: Failed to parse line: {line[:50]}... ({e})")
            return None

    def format_output(self, decoded_msg: DecodedMessage, format_type: str = 'human') -> str:
        """
        Format decoded message for output

        Args:
            decoded_msg: Decoded message to format
            format_type: Output format ('human', 'json', 'csv')

        Returns:
            Formatted string
        """
        if format_type == 'json':
            return json.dumps(asdict(decoded_msg), indent=2)

        elif format_type == 'csv':
            # CSV header: timestamp,arb_id,ecu_serial,channel,message,signal,value,unit
            lines = []
            for signal in decoded_msg.signals:
                lines.append(
                    f"{decoded_msg.timestamp},{decoded_msg.arbitration_id:08X},"
                    f"{decoded_msg.ecu_serial},{decoded_msg.channel_index},"
                    f"{decoded_msg.message_name},{signal.name},{signal.value},{signal.unit}"
                )
            return '\n'.join(lines)

        else:  # human-readable
            output = []
            output.append(f"\n[{decoded_msg.timestamp:.6f}] {decoded_msg.message_name}")
            output.append(f"  CAN ID: 0x{decoded_msg.arbitration_id:08X} | ECU Serial: {decoded_msg.ecu_serial} (0x{decoded_msg.ecu_serial:03X}) | Channel: {decoded_msg.channel_index}")

            for signal in decoded_msg.signals:
                unit_str = f" {signal.unit}" if signal.unit else ""
                output.append(f"  {signal.name:30s} = {signal.value}{unit_str}")

            return '\n'.join(output)


class LiveDashboard:
    """Live updating dashboard for Holley EFI data (similar to Unix 'top')"""

    # Safety thresholds for color coding
    THRESHOLDS = {
        'RPM': {'warning': 7000, 'critical': 8000},
        'OIL_PRESSURE': {'warning_low': 30, 'critical_low': 20},
        'OIL_TEMP': {'warning': 250, 'critical': 280},
        'COOLANT_TEMP': {'warning': 210, 'critical': 230},
        'FUEL_PRESSURE': {'warning_low': 40, 'critical_low': 30},
        'KNOCK_RETARD': {'warning': 2, 'critical': 4},
        'BOOST_PSIG': {'warning': 20, 'critical': 25},
    }

    def __init__(self, ecu_serial: Optional[int] = None, record_file: Optional[str] = None,
                 show_minmax: bool = False):
        """Initialize the live dashboard"""
        self.ecu_serial = ecu_serial
        self.latest_values: Dict[str, DecodedSignal] = {}
        self.message_count = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.use_curses = False
        self.show_minmax = show_minmax
        self.record_file = None

        # Open recording file if specified
        if record_file:
            self.record_file = open(record_file, 'w')
            self.record_file.write(f"# Holley EFI CAN recording started: {datetime.now()}\n")

        # Try to use curses for better display
        try:
            import curses
            self.curses = curses
            self.use_curses = True
        except ImportError:
            self.curses = None
            self.use_curses = False

    def update(self, decoded_msg: DecodedMessage, raw_line: Optional[str] = None):
        """Update dashboard with new message data"""
        self.message_count += 1
        self.last_update = time.time()

        # Record to file if enabled
        if self.record_file and raw_line:
            self.record_file.write(raw_line)
            self.record_file.flush()

        # Update latest values for each signal
        for signal in decoded_msg.signals:
            # Skip status signals
            if 'status' in signal.name.lower() or signal.name == 'raw_data':
                continue

            # Update min/max if tracking
            if self.show_minmax and signal.name in self.latest_values:
                signal.min_value = self.latest_values[signal.name].min_value
                signal.max_value = self.latest_values[signal.name].max_value
                signal.update_minmax(signal.value)
            elif self.show_minmax:
                signal.update_minmax(signal.value)

            self.latest_values[signal.name] = signal

    def get_value_color(self, signal: DecodedSignal) -> int:
        """Get color code for value based on thresholds"""
        if not self.use_curses:
            return 0

        param_name = signal.name.upper()
        if param_name not in self.THRESHOLDS:
            return 0  # Default color

        thresholds = self.THRESHOLDS[param_name]
        value = signal.value if isinstance(signal.value, (int, float)) else 0

        # Check critical thresholds
        if 'critical' in thresholds and value >= thresholds['critical']:
            return self.curses.color_pair(1)  # Red
        if 'critical_low' in thresholds and value <= thresholds['critical_low']:
            return self.curses.color_pair(1)  # Red

        # Check warning thresholds
        if 'warning' in thresholds and value >= thresholds['warning']:
            return self.curses.color_pair(2)  # Yellow
        if 'warning_low' in thresholds and value <= thresholds['warning_low']:
            return self.curses.color_pair(2)  # Yellow

        return self.curses.color_pair(3)  # Green (normal)

    def render_simple(self):
        """Render dashboard using simple terminal escape codes"""
        # Clear screen
        os.system('clear' if os.name != 'nt' else 'cls')

        # Header
        runtime = time.time() - self.start_time
        msg_rate = self.message_count / runtime if runtime > 0 else 0

        print("=" * 100)
        print(f"  HOLLEY EFI LIVE DASHBOARD")
        if self.ecu_serial is not None:
            print(f"  ECU Serial: {self.ecu_serial} (0x{self.ecu_serial & 0x7FF:04d})")
        print("=" * 100)
        print(f"  Runtime: {runtime:.1f}s | Messages: {self.message_count} | Rate: {msg_rate:.1f} msg/s")
        print(f"  Last Update: {time.strftime('%H:%M:%S', time.localtime(self.last_update))}")
        print(f"  Parameters: {len(self.latest_values)}")
        if self.record_file:
            print(f"  Recording: {self.record_file.name}")
        print("=" * 100)
        print()

        # Display all parameters sorted alphabetically
        if self.show_minmax:
            print(f"{'PARAMETER':<35} {'VALUE':>12} {'MIN':>12} {'MAX':>12} {'UNIT':<15}")
            print("-" * 100)
        else:
            print(f"{'PARAMETER':<35} {'VALUE':>15} {'UNIT':<15}")
            print("-" * 100)

        sorted_params = sorted(self.latest_values.keys())
        for param in sorted_params:
            signal = self.latest_values[param]
            value_str = f"{signal.value:.2f}" if isinstance(signal.value, float) else str(signal.value)
            unit_str = signal.unit if signal.unit else ""

            if self.show_minmax:
                min_str = f"{signal.min_value:.2f}" if signal.min_value is not None else "---"
                max_str = f"{signal.max_value:.2f}" if signal.max_value is not None else "---"
                print(f"{signal.name:<35} {value_str:>12} {min_str:>12} {max_str:>12} {unit_str:<15}")
            else:
                print(f"{signal.name:<35} {value_str:>15} {unit_str:<15}")

        print()
        print("=" * 100)
        print("Press Ctrl+C to exit")

    def run(self, parser: 'HolleyCANParser', input_stream):
        """Run the live dashboard"""
        if self.use_curses:
            self.run_curses(parser, input_stream)
        else:
            self.run_simple(parser, input_stream)

    def run_simple(self, parser: 'HolleyCANParser', input_stream):
        """Run dashboard with simple terminal updates"""
        try:
            update_counter = 0
            for line in input_stream:
                raw_msg = parser.parse_candump_line(line)
                if not raw_msg:
                    continue

                decoded_msg = parser.parse_message(raw_msg)
                if decoded_msg:
                    self.update(decoded_msg, line if line.endswith('\n') else line + '\n')

                    # Update display every 10 messages or every 0.1 seconds
                    update_counter += 1
                    if update_counter >= 10 or (time.time() - self.last_update) > 0.1:
                        self.render_simple()
                        update_counter = 0

        except KeyboardInterrupt:
            print("\n\nDashboard stopped by user")
        finally:
            if self.record_file:
                self.record_file.close()
                print(f"\nRecording saved to: {self.record_file.name}")

    def run_curses(self, parser: 'HolleyCANParser', input_stream):
        """Run dashboard with curses for better display"""
        def curses_main(stdscr):
            # Setup colors
            self.curses.start_color()
            self.curses.init_pair(1, self.curses.COLOR_RED, self.curses.COLOR_BLACK)      # Critical
            self.curses.init_pair(2, self.curses.COLOR_YELLOW, self.curses.COLOR_BLACK)   # Warning
            self.curses.init_pair(3, self.curses.COLOR_GREEN, self.curses.COLOR_BLACK)    # Normal
            self.curses.init_pair(4, self.curses.COLOR_CYAN, self.curses.COLOR_BLACK)     # Info

            # Setup
            self.curses.curs_set(0)  # Hide cursor
            stdscr.nodelay(1)  # Non-blocking input
            stdscr.timeout(100)  # 100ms timeout

            try:
                for line in input_stream:
                    # Check for quit
                    key = stdscr.getch()
                    if key == ord('q') or key == ord('Q'):
                        break

                    raw_msg = parser.parse_candump_line(line)
                    if not raw_msg:
                        continue

                    decoded_msg = parser.parse_message(raw_msg)
                    if decoded_msg:
                        self.update(decoded_msg, line if line.endswith('\n') else line + '\n')
                        self.render_curses(stdscr)

            except KeyboardInterrupt:
                pass
            finally:
                if self.record_file:
                    self.record_file.close()

        self.curses.wrapper(curses_main)

    def render_curses(self, stdscr):
        """Render dashboard using curses"""
        stdscr.clear()
        max_rows, max_cols = stdscr.getmaxyx()

        # Header
        runtime = time.time() - self.start_time
        msg_rate = self.message_count / runtime if runtime > 0 else 0

        row = 0
        try:
            stdscr.addstr(row, 0, "=" * min(100, max_cols - 1), self.curses.A_BOLD)
            row += 1
            stdscr.addstr(row, 0, "  HOLLEY EFI LIVE DASHBOARD", self.curses.A_BOLD | self.curses.color_pair(4))
            row += 1
            if self.ecu_serial is not None:
                stdscr.addstr(row, 0, f"  ECU Serial: {self.ecu_serial} (0x{self.ecu_serial & 0x7FF:03X})")
                row += 1
            stdscr.addstr(row, 0, "=" * min(100, max_cols - 1), self.curses.A_BOLD)
            row += 1
            stdscr.addstr(row, 0, f"  Runtime: {runtime:.1f}s | Messages: {self.message_count} | Rate: {msg_rate:.1f} msg/s")
            row += 1
            status_line = f"  Last Update: {time.strftime('%H:%M:%S', time.localtime(self.last_update))} | Parameters: {len(self.latest_values)}"
            if self.record_file:
                status_line += f" | Recording: {self.record_file.name}"
            stdscr.addstr(row, 0, status_line[:max_cols - 1])
            row += 1
            stdscr.addstr(row, 0, "=" * min(100, max_cols - 1), self.curses.A_BOLD)
            row += 2

            # Column headers
            if self.show_minmax:
                header = f"{'PARAMETER':<35} {'VALUE':>12} {'MIN':>12} {'MAX':>12} {'UNIT':<15}"
            else:
                header = f"{'PARAMETER':<35} {'VALUE':>15} {'UNIT':<15}"
            stdscr.addstr(row, 0, header[:max_cols - 1], self.curses.A_BOLD)
            row += 1
            stdscr.addstr(row, 0, "-" * min(100, max_cols - 1))
            row += 1

            # Display all parameters sorted alphabetically, as many as fit
            sorted_params = sorted(self.latest_values.keys())
            for param in sorted_params:
                if row >= max_rows - 2:  # Leave room for footer
                    break

                signal = self.latest_values[param]
                value_str = f"{signal.value:.2f}" if isinstance(signal.value, float) else str(signal.value)
                unit_str = signal.unit if signal.unit else ""

                # Get color for value
                color = self.get_value_color(signal)

                if self.show_minmax:
                    min_str = f"{signal.min_value:.2f}" if signal.min_value is not None else "---"
                    max_str = f"{signal.max_value:.2f}" if signal.max_value is not None else "---"
                    line = f"{signal.name:<35} {value_str:>12} {min_str:>12} {max_str:>12} {unit_str:<15}"
                else:
                    line = f"{signal.name:<35} {value_str:>15} {unit_str:<15}"

                stdscr.addstr(row, 0, line[:max_cols - 1], color)
                row += 1

            # Footer
            if row < max_rows - 1:
                stdscr.addstr(max_rows - 2, 0, "=" * min(100, max_cols - 1))
                stdscr.addstr(max_rows - 1, 0, "Press 'q' or Ctrl+C to exit")

        except self.curses.error:
            # Ignore curses errors from writing outside screen bounds
            pass

        stdscr.refresh()


def create_can_stream(interface: str, bitrate: int = 1000000):
    """
    Create a stream from a CAN interface using python-can

    Args:
        interface: CAN interface name (e.g., 'can0', 'can1')
        bitrate: CAN bus bitrate (default: 1000000 for 1Mbit/s)

    Yields:
        Lines in candump format
    """
    try:
        import can
    except ImportError:
        print("Error: python-can library not installed")
        print("Install with: pip install python-can")
        sys.exit(1)

    # Try to setup the interface
    try:
        bus = can.interface.Bus(channel=interface, bustype='socketcan', bitrate=bitrate)
    except Exception as e:
        print(f"Error: Could not open CAN interface '{interface}': {e}")
        print(f"\nTroubleshooting:")
        print(f"  1. Check interface exists: ip link show {interface}")
        print(f"  2. Bring interface up: sudo ip link set {interface} up type can bitrate {bitrate}")
        print(f"  3. Check permissions: sudo chmod 666 /dev/{interface}")
        sys.exit(1)

    print(f"Listening on {interface} at {bitrate} bps...", file=sys.stderr)

    try:
        for msg in bus:
            # Convert to candump format: (timestamp) interface arbitration_id#data
            timestamp = msg.timestamp if msg.timestamp else time.time()
            arb_id_str = f"{msg.arbitration_id:08X}"
            data_str = msg.data.hex().upper()

            # Format as pairs of hex digits
            data_formatted = ''.join([data_str[i:i+2] for i in range(0, len(data_str), 2)])

            line = f"({timestamp:.6f}) {interface} {arb_id_str}#{data_formatted}\n"
            yield line

    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()


def create_example_config(output_path: str = 'holley_config.yaml'):
    """Create an example YAML configuration file"""
    example_config = {
        'ecu_serial': 19838,  # ECU serial number (full serial, lower 11 bits will be used)
        'dbc_path': 'HP Dominator & Terminator X DBC.dbc',
        'message_filter': [
            'RPM',
            'FUEL_AFR_AVERAGE',
            'OIL_PRESSURE',
            'COOLANT_TEMP'
        ],
        'output_format': 'human',  # human, json, csv, live
        'decode_signals': True,
        'show_raw_data': False,
    }

    with open(output_path, 'w') as f:
        f.write("# Holley EFI CAN Parser Configuration\n")
        f.write("# Serial number of the ECU to monitor (0-255)\n")
        f.write("# Set to null to monitor all ECUs\n")
        yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)

    print(f"Example configuration written to: {output_path}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Holley EFI CAN Bus Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Listen directly on CAN interface with live dashboard
  %(prog)s --interface can0 --ecu-serial 19838 --dbc "HP Dominator & Terminator X DBC.dbc" --live

  # Parse candump file
  %(prog)s --ecu-serial 19838 --dbc "HP Dominator & Terminator X DBC.dbc" can_log.txt

  # Use YAML config file
  %(prog)s --config holley_config.yaml can_log.txt

  # Live dashboard with min/max tracking and recording
  %(prog)s -i can0 -e 19838 -d "HP Dominator & Terminator X DBC.dbc" --live --minmax --record session.log

  # Generate example config
  %(prog)s --create-config
        """
    )

    parser.add_argument('input', nargs='?', default=None,
                       help='Input file (candump format) or "-" for stdin')
    parser.add_argument('-c', '--config', type=str,
                       help='Path to YAML configuration file')
    parser.add_argument('-i', '--interface', type=str,
                       help='CAN interface to listen on (e.g., can0, can1)')
    parser.add_argument('-e', '--ecu-serial', type=lambda x: int(x, 0),
                       help='ECU serial number (hex or decimal, e.g., 19838 or 0x4D7E)')
    parser.add_argument('-d', '--dbc', type=str,
                       help='Path to DBC file')
    parser.add_argument('-f', '--format', choices=['human', 'json', 'csv', 'live'],
                       default='human', help='Output format')
    parser.add_argument('--live', action='store_true',
                       help='Enable live dashboard view (like Unix top)')
    parser.add_argument('--minmax', action='store_true',
                       help='Show min/max values in live dashboard')
    parser.add_argument('--record', type=str, metavar='FILE',
                       help='Record CAN data to file while viewing live')
    parser.add_argument('--bitrate', type=int, default=1000000,
                       help='CAN bus bitrate (default: 1000000 for 1Mbit/s)')
    parser.add_argument('--create-config', action='store_true',
                       help='Create example configuration file and exit')
    parser.add_argument('-o', '--output', type=str,
                       help='Output file (default: stdout)')

    args = parser.parse_args()

    # Handle config creation
    if args.create_config:
        create_example_config()
        return 0

    # Initialize parser
    can_parser = HolleyCANParser(
        config_path=args.config,
        ecu_serial=args.ecu_serial,
        dbc_path=args.dbc
    )

    # Determine input source
    if args.interface:
        # Direct CAN interface
        input_stream = create_can_stream(args.interface, args.bitrate)
        input_is_generator = True
    elif args.input == '-' or args.input is None:
        # Stdin
        input_stream = sys.stdin
        input_is_generator = False
    else:
        # File
        try:
            input_stream = open(args.input, 'r')
            input_is_generator = False
        except FileNotFoundError:
            print(f"Error: Input file '{args.input}' not found")
            return 1

    # Handle live dashboard mode
    if args.live or args.format == 'live':
        dashboard = LiveDashboard(
            ecu_serial=args.ecu_serial,
            record_file=args.record,
            show_minmax=args.minmax
        )
        dashboard.run(can_parser, input_stream)
        if not input_is_generator and input_stream != sys.stdin:
            input_stream.close()
        return 0

    # Open output stream
    if args.output:
        output_stream = open(args.output, 'w')
    else:
        output_stream = sys.stdout

    # Print CSV header if needed
    if args.format == 'csv':
        output_stream.write("timestamp,arb_id,ecu_serial,channel,message,signal,value,unit\n")

    # Process input line by line
    try:
        message_count = 0
        decoded_count = 0

        for line in input_stream:
            raw_msg = can_parser.parse_candump_line(line)
            if not raw_msg:
                continue

            message_count += 1
            decoded_msg = can_parser.parse_message(raw_msg)

            if decoded_msg:
                decoded_count += 1
                output_stream.write(can_parser.format_output(decoded_msg, args.format))
                output_stream.write('\n')
                output_stream.flush()

        # Print summary to stderr so it doesn't interfere with output
        if args.input != '-':
            print(f"\nProcessed {message_count} messages, decoded {decoded_count}",
                  file=sys.stderr)

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)

    finally:
        if not input_is_generator and input_stream != sys.stdin:
            input_stream.close()
        if output_stream != sys.stdout:
            output_stream.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
