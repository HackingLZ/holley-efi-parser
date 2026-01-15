# Holley EFI CAN Bus Parser

A Python tool for parsing and analyzing CAN bus data from Holley EFI systems with support for ECU serial number filtering, real-time live dashboards, and multiple output formats.

## Features

- **Direct CAN Interface Support**: Listen directly on can0, can1, etc. without needing candump
- **ECU Serial Number Filtering**: Filter messages by ECU serial number (configurable via CLI or YAML)
- **DBC File Support**: Automatic message decoding using Holley DBC files
- **Live Dashboard**: Real-time display of sensor data (similar to Unix `top` command)
  - **Color Coding**: Red/yellow/green values based on safety thresholds
  - **Min/Max Tracking**: Track minimum and maximum values for all parameters
  - **Recording**: Save CAN data to file while viewing live
- **Multiple Output Formats**: Human-readable, JSON, CSV
- **Holley CAN ID Parsing**: Proper handling of Holley's proprietary CAN ID structure
- **Channel Index Extraction**: Identifies parameter channel from CAN ID
- **Safety Alerts**: Configurable thresholds for critical parameters (RPM, oil pressure, coolant temp, etc.)

## Installation

```bash
# Clone or download the repository
cd /home/justin/holley/holley-efi-parser/can

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

- Python 3.7+
- `pyyaml` - YAML configuration file support
- `cantools` - DBC file parsing and CAN message decoding
- `python-can` - Direct CAN interface support (highly recommended)
- `curses` - Enhanced live dashboard with colors (included with Python on Linux/Mac)

## Holley CAN ID Structure

Holley EFI uses a proprietary CAN ID structure (29-bit extended):

```
Bits 28      - Command bit (=1)
Bits 27:25   - Target ID (=111 for broadcast)
Bits 24:14   - Target Serial / Channel Index (parameter identifier)
Bits 13:11   - Source ID (=010 for ECU)
Bits 10:0    - Source Serial (lower 11 bits of ECU serial number)
```

**Important**: The parser automatically extracts the lower 11 bits of your ECU serial number for matching. For example, ECU serial 19838 uses 0x57E (1406) in the CAN ID.

## Usage

### Quick Start

```bash
# Generate example configuration file
./holley_can_parser.py --create-config

# Edit the config to set your ECU serial number
# ecu_serial: 19838

# Live dashboard listening directly on CAN interface
./holley_can_parser.py --interface can0 --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" --live

# Live dashboard with min/max tracking and recording
./holley_can_parser.py -i can0 -e 19838 \
    -d "HP Dominator & Terminator X DBC.dbc" \
    --live --minmax --record session.log

# Parse saved candump log file
./holley_can_parser.py --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" \
    can_log.txt

# Use YAML configuration
./holley_can_parser.py --config holley_config.yaml can_log.txt
```

### Live Dashboard

The live dashboard provides a real-time view of all sensor values, automatically updating as new CAN messages arrive:

```bash
# Live dashboard listening directly on CAN interface
./holley_can_parser.py --interface can0 --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" --live

# Live dashboard with min/max tracking
./holley_can_parser.py -i can0 -e 19838 \
    -d "HP Dominator & Terminator X DBC.dbc" --live --minmax

# Live dashboard with recording to file
./holley_can_parser.py -i can0 -e 19838 \
    -d "HP Dominator & Terminator X DBC.dbc" \
    --live --record drag_pass_001.log

# Live dashboard from log file playback
./holley_can_parser.py --live --config holley_config.yaml can_log.txt
```

**Dashboard Controls**:
- Press `Ctrl+C` to exit
- Press `q` to quit (if curses is available)

**Display Features**:
- **Color Coding** (with curses):
  - 🟢 Green: Normal values
  - 🟡 Yellow: Warning thresholds
  - 🔴 Red: Critical thresholds
- **Min/Max Tracking**: Use `--minmax` flag to show minimum and maximum values
- **Recording**: Use `--record <file>` to save CAN data while viewing
- Shows all available parameters sorted alphabetically
- Automatically fits as many parameters as will display on your screen
- Real-time value updates as CAN messages arrive
- Message rate and parameter count statistics
- No filtering - displays everything received from the ECU

**Safety Thresholds** (configurable in code):
- RPM: Warning @ 7000, Critical @ 8000
- Oil Pressure: Warning @ 30 psi, Critical @ 20 psi
- Oil Temp: Warning @ 250°F, Critical @ 280°F
- Coolant Temp: Warning @ 210°F, Critical @ 230°F
- Fuel Pressure: Warning @ 40 psi, Critical @ 30 psi
- Knock Retard: Warning @ 2°, Critical @ 4°
- Boost: Warning @ 20 psi, Critical @ 25 psi

### Command Line Options

```
usage: holley_can_parser.py [-h] [-c CONFIG] [-i INTERFACE] [-e ECU_SERIAL]
                             [-d DBC] [-f {human,json,csv,live}] [--live]
                             [--minmax] [--record FILE] [--bitrate BITRATE]
                             [--create-config] [-o OUTPUT] [input]

Arguments:
  input                 Input file (candump format) or "-" for stdin

Options:
  -c, --config CONFIG   Path to YAML configuration file
  -i, --interface       CAN interface to listen on (e.g., can0, can1)
  -e, --ecu-serial      ECU serial number (hex or decimal, e.g., 19838 or 0x4D7E)
  -d, --dbc DBC         Path to DBC file
  -f, --format          Output format: human, json, csv, live
  --live                Enable live dashboard view
  --minmax              Show min/max values in live dashboard
  --record FILE         Record CAN data to file while viewing live
  --bitrate BITRATE     CAN bus bitrate (default: 1000000 for 1Mbit/s)
  --create-config       Create example configuration file
  -o, --output OUTPUT   Output file (default: stdout)
```

### YAML Configuration

Create a configuration file for easy reuse:

```yaml
# holley_config.yaml
ecu_serial: 19838  # Your ECU serial number
dbc_path: HP Dominator & Terminator X DBC.dbc

message_filter:
  - RPM
  - FUEL_AFR_AVERAGE
  - OIL_PRESSURE
  - COOLANT_TEMP

output_format: human  # human, json, csv, live
decode_signals: true
show_raw_data: false
```

### Output Formats

#### Human-Readable (default)
```
[1234.567890] RPM
  CAN ID: 0x9E005000 | ECU Serial: 1406 (0x57E) | Channel: 8
  RPM                            = 6500.00 rpm
```

#### JSON
```json
{
  "timestamp": 1234.567890,
  "arbitration_id": 2650820608,
  "ecu_serial": 1406,
  "channel_index": 8,
  "message_name": "RPM",
  "signals": [
    {
      "name": "RPM",
      "value": 6500.0,
      "unit": "rpm",
      "raw_value": 6500
    }
  ]
}
```

#### CSV
```csv
timestamp,arb_id,ecu_serial,channel,message,signal,value,unit
1234.567890,9E005000,1406,8,RPM,RPM,6500.0,rpm
```

## Examples

### Example 1: Real-time CAN Monitoring

```bash
# Connect directly to CAN interface and monitor ECU 19838
./holley_can_parser.py \
    --interface can0 \
    --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" \
    --live

# With min/max tracking and recording
./holley_can_parser.py -i can0 -e 19838 \
    -d "HP Dominator & Terminator X DBC.dbc" \
    --live --minmax --record pass_001.log
```

### Example 2: Export Data to CSV

```bash
# Parse log file and export to CSV
./holley_can_parser.py \
    --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" \
    --format csv \
    --output parsed_data.csv \
    can_log.txt
```

### Example 3: JSON Output for Analysis

```bash
# Parse and output as JSON for further processing
./holley_can_parser.py \
    --config holley_config.yaml \
    --format json \
    can_log.txt | jq '.signals[] | select(.name == "RPM")'
```

### Example 4: Filter Specific ECU in Multi-ECU Setup

If you have multiple ECUs on the bus, filter by serial number:

```bash
# Only show messages from ECU 19838
./holley_can_parser.py \
    --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" \
    multi_ecu_log.txt
```

## DBC Files

The tool supports the official Holley DBC files:

- `HP Dominator & Terminator X DBC.dbc` - For HP/Dominator (V4+) and Terminator X products
- `Sniper V2 DBC.dbc` - For Sniper EFI products (V2+)
- `HARDWIRE HOLLEY DBC FILE.dbc` - Alternative format

Place the appropriate DBC file in the same directory or specify the full path via `--dbc` or in your config file.

## CAN Interface Setup (Linux)

To use direct CAN interface support:

```bash
# Setup CAN interface (SocketCAN on Linux)
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0

# Verify interface is up
ip link show can0

# Start live monitoring (no candump needed!)
./holley_can_parser.py --interface can0 --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" --live
```

### Alternative: Using candump

If you prefer using candump or need to use other CAN tools:

```bash
# Pipe candump output to parser
candump can0 | ./holley_can_parser.py --live --config holley_config.yaml -

# Or save to file first
candump -l can0  # Saves to candump-*.log
./holley_can_parser.py --live candump-2025-01-15_123456.log
```

## Troubleshooting

### DBC File Not Loading
- Ensure `cantools` is installed: `pip install cantools`
- Check the DBC file path is correct
- Try the absolute path to the DBC file

### No Messages Displayed
- Verify ECU serial number is correct (check lower 11 bits)
- Check that candump is receiving messages: `candump can0`
- Ensure the DBC file matches your ECU model

### Live Dashboard Not Updating
- Check input stream is providing data
- Verify ECU serial filter matches your ECU
- Ensure messages are in candump format

## License

This tool is provided as-is for Holley EFI data analysis.

## References

- Holley EFI CAN Communication Protocol (Revision 1: November 8, 2024)
- Holley EFI official DBC files
