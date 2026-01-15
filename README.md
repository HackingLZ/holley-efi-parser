# Holley EFI Parser

Python toolkit for parsing Holley EFI data - including binary data logs (.DL/.DLZ) and real-time CAN bus communication.

## Features

- **DLZ Decompression**: Decompress DLZ files with 100% accuracy
- **Multi-Format DL Parsing**: Parse V3, V4, V5, and V6 Holley DL formats
- **Real-Time CAN Bus**: Live dashboard for monitoring ECU data via CAN bus
- **Batch Analysis**: Process multiple log files with comprehensive statistics
- **CSV Export**: Convert binary logs to CSV for analysis

## Project Structure

```
holley-efi-parser/
├── holley_parser/          # Binary datalog parsing
│   ├── dlz_decompressor.py     # DLZ → DL decompression (100% accurate)
│   ├── universal_dl_parser.py  # Main DL parser (V3/V5/V6 support)
│   ├── batch_dl_analyzer.py    # Batch file analysis
│   ├── dl_analyzer.py          # Raw hex analysis tool
│   ├── comprehensive_dl_mapper.py  # CSV-to-DL mapping tool
│   └── csv_dl_comparator.py    # CSV comparison tool
│
└── can/                    # Real-time CAN bus tools
    ├── holley_can_parser.py    # CAN message parser & live dashboard
    ├── holley_config.yaml      # Configuration template
    ├── *.dbc                   # Holley DBC files for decoding
    └── README.md               # CAN-specific documentation
```

## Installation

```bash
git clone https://github.com/HackingLZ/holley-efi-parser.git
cd holley-efi-parser
pip install -e .
```

For CAN bus support:
```bash
pip install -r can/requirements.txt
```

---

## holley_parser - Binary Datalog Tools

### DLZ Decompressor

Converts compressed .DLZ files to .DL format with **100% accuracy**.

```python
from holley_parser import decompress_dlz, decompress_file

# Decompress in memory
with open('mylog.DLZ', 'rb') as f:
    dl_data = decompress_dlz(f.read())

# Or decompress to file
decompress_file('mylog.DLZ', 'mylog.dl')
```

**Algorithm**:
1. Byte swap (endian conversion)
2. RLE decompress (0xFF COUNT VALUE)
3. Byte swap result

### Universal DL Parser

Parses decompressed .DL files into pandas DataFrames.

```python
from holley_parser import UniversalDLParser

parser = UniversalDLParser('mylog.dl')
df = parser.parse()

print(f"Parsed {len(df)} rows x {len(df.columns)} columns")
print(f"RPM range: {df['Param_002'].min():.0f} - {df['Param_002'].max():.0f}")
```

**Supported Formats:**

| Format | Magic | field_08 | Status |
|--------|-------|----------|--------|
| V3 (Terminator X) | 0x0095365F | 2-3 | Supported |
| V4 | 0x0085F41F | 4 | Partial |
| V5 | 0x0085F41F | 5 | Requires Holley conversion to V6 |
| V6 | 0x0085F41F | 6 | Fully supported |

### Full Pipeline Example

```python
from holley_parser import decompress_dlz, UniversalDLParser
import tempfile

# DLZ → decompress → parse (works for V6 DLZ files)
with open('mylog.DLZ', 'rb') as f:
    dl_data = decompress_dlz(f.read())

with tempfile.NamedTemporaryFile(suffix='.dl', delete=False) as f:
    f.write(dl_data)
    temp_path = f.name

parser = UniversalDLParser(temp_path)
df = parser.parse()
df.to_csv('mylog.csv', index=False)
```

### Other Tools

| Tool | Purpose |
|------|---------|
| `batch_dl_analyzer.py` | Analyze multiple DL files, identify format variations |
| `dl_analyzer.py` | Raw hex analysis for debugging |
| `comprehensive_dl_mapper.py` | Map CSV columns to DL binary offsets |
| `csv_dl_comparator.py` | Compare CSV exports with DL binary files |

---

## can/ - Real-Time CAN Bus Tools

Real-time monitoring of Holley ECU data via CAN bus with live dashboard, DBC decoding, and ECU serial filtering.

### Quick Start

```bash
cd can/

# Live dashboard on CAN interface
./holley_can_parser.py --interface can0 --ecu-serial 19838 \
    --dbc "HP Dominator & Terminator X DBC.dbc" --live

# With min/max tracking and recording
./holley_can_parser.py -i can0 -e 19838 \
    -d "HP Dominator & Terminator X DBC.dbc" \
    --live --minmax --record session.log
```

### Features

- **Direct CAN Interface**: Listen on can0/can1 without candump
- **Live Dashboard**: Real-time sensor display with color-coded safety thresholds
- **ECU Serial Filtering**: Filter by ECU serial number for multi-ECU setups
- **DBC Decoding**: Automatic message decoding using Holley DBC files
- **Multiple Outputs**: Human-readable, JSON, CSV formats
- **Safety Alerts**: Configurable thresholds (RPM, oil pressure, coolant temp, etc.)

### Included DBC Files

| File | Use With |
|------|----------|
| `HP Dominator & Terminator X DBC.dbc` | HP/Dominator (V4+), Terminator X |
| `HARDWIRE HOLLEY DBC FILE.dbc` | Alternative format |

### CAN Interface Setup (Linux)

```bash
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0

# Start monitoring
./holley_can_parser.py -i can0 -e YOUR_ECU_SERIAL \
    -d "HP Dominator & Terminator X DBC.dbc" --live
```

See `can/README.md` for full documentation.

---

## DL File Format Notes

### V5 vs V6 Format

- **V5**: Sparse storage format used by ECU. Cannot be parsed directly.
- **V6**: Full format created when V5 files are opened in Holley software.

**Workflow for V5 files:**
1. Decompress DLZ → DL (our tool)
2. Open DL in Holley EFI software (converts V5 → V6)
3. Parse V6 file (our tool)

**V6 DLZ files** (newer ECUs) work end-to-end without Holley software.

### Key Parameters

| Column | Parameter |
|--------|-----------|
| Param_000 | Point Number |
| Param_001 | RTC (timestamp) |
| Param_002 | RPM |
| Param_066 | TPS |
| ... | (516 total parameters) |

---

## Development Status

| Component | Status |
|-----------|--------|
| DLZ Decompression | **100% accurate** (verified against 9 file pairs) |
| V6 DL Parsing | Working |
| V5 DL Parsing | Requires Holley software conversion |
| V3 DL Parsing | Working |
| CAN Bus Parser | Working |

---

## License

MIT License - See LICENSE file for details.

## Disclaimer

This is an independent implementation not affiliated with Holley Performance Products. Use at your own risk.

## Contributing

Contributions welcome! Areas for improvement:
- V5 format direct parsing
- V4 format support
- Additional parameter mapping
- Unit tests
