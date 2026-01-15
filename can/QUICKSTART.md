# Holley CAN Parser - Quick Start Guide

## Installation

```bash
cd /home/justin/holley/holley-efi-parser/can
pip install -r requirements.txt
```

## Setup CAN Interface (Linux)

```bash
# One-time setup
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0

# Verify
ip link show can0
```

## Most Common Commands

### Live Dashboard (Recommended for Racing)
```bash
# Basic live monitoring
./holley_can_parser.py -i can0 -e 19838 -d "HP Dominator & Terminator X DBC.dbc" --live

# With min/max tracking
./holley_can_parser.py -i can0 -e 19838 -d "HP Dominator & Terminator X DBC.dbc" --live --minmax

# Record while viewing (for drag passes)
./holley_can_parser.py -i can0 -e 19838 -d "HP Dominator & Terminator X DBC.dbc" --live --record pass_001.log
```

### Replay Recorded Data
```bash
# View recorded pass
./holley_can_parser.py --live --minmax pass_001.log

# Export to CSV for analysis
./holley_can_parser.py -f csv -o pass_001.csv pass_001.log
```

## Color Codes (in live dashboard)

- 🟢 **Green** = Normal (safe values)
- 🟡 **Yellow** = Warning (approaching limits)
- 🔴 **Red** = Critical (immediate attention needed!)

## Controls

- **Ctrl+C** = Exit
- **q** = Quit (if colors are working)

## Your ECU Configuration

- **ECU Serial**: 19838 (0x4D7E)
- **CAN Serial** (lower 11 bits): 1406 (0x57E)
- **DBC File**: HP Dominator & Terminator X DBC.dbc
- **CAN Bitrate**: 1000000 (1 Mbit/s)

## Typical Drag Racing Workflow

```bash
# 1. Start monitoring before staging
./holley_can_parser.py -i can0 -e 19838 -d "HP Dominator & Terminator X DBC.dbc" --live --record run_001.log

# 2. Make your pass, then Ctrl+C when done

# 3. Review the run
./holley_can_parser.py --live --minmax run_001.log

# 4. Export for detailed analysis
./holley_can_parser.py -f csv -o run_001.csv run_001.log
```

## Troubleshooting

**CAN interface not found?**
```bash
sudo ip link set can0 up type can bitrate 1000000
```

**Permission denied?**
```bash
sudo chmod 666 /dev/can0
# OR run with sudo
sudo ./holley_can_parser.py -i can0 --live
```

**No data showing?**
- Check ECU serial number is correct (19838)
- Verify CAN bus is active: `candump can0`
- Check DBC file path is correct

**Colors not working?**
- Install curses: Already included in Python on Linux
- Terminal must support colors

## Files

- `holley_can_parser.py` - Main program
- `holley_config.yaml` - Your saved configuration
- `README.md` - Full documentation
- `IMPROVEMENTS.md` - Feature changelog
- `HP Dominator & Terminator X DBC.dbc` - Message definitions

## Safety Thresholds (built-in)

| Parameter | Warning | Critical |
|-----------|---------|----------|
| RPM | 7000 | 8000 |
| Oil Pressure | <30 psi | <20 psi |
| Oil Temp | 250°F | 280°F |
| Coolant Temp | 210°F | 230°F |
| Fuel Pressure | <40 psi | <30 psi |
| Knock Retard | 2° | 4° |
| Boost | 20 psi | 25 psi |

Edit `holley_can_parser.py` line 317-325 to customize thresholds for your engine.

## Pro Tips

1. **Always record your passes** - use `--record` to save data for later analysis
2. **Use --minmax** - helps you see peak boost, max RPM, lowest oil pressure, etc.
3. **Name your recordings** - `run_001.log`, `pass_5.59.log`, `baseline_tuning.log`
4. **Export to CSV** - easier to analyze in Excel or Google Sheets
5. **Watch the colors** - red = stop and investigate!

---

For more info, see README.md
