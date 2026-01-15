#!/usr/bin/env python3
"""
Universal Holley DL Parser

Supports multiple Holley ECU formats:
- V3 (Terminator X): Magic 0x0095365F, field_08=2-3, 516 floats/row, non-interleaved
- V5: Magic 0x0085F41F, field_08=5, sparse format (requires Holley software conversion)
- V6: Magic 0x0085F41F, field_08=6, 1030 floats/row, interleaved, data_start=16456

Version detection uses field_08 header value for reliable identification.
"""

import struct
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional


class UniversalDLParser:
    """Parse Holley DL files across V3, V5, and V6 formats."""

    # Known format signatures
    MAGIC_V3 = 0x0095365F  # V3 / Terminator X format
    MAGIC_V5_V6 = 0x0085F41F  # V5/V6 format

    # Header field at offset 8 indicates version
    VERSION_V3_OLD = 2  # Older Terminator X V3
    VERSION_V3 = 3      # Terminator X V3
    VERSION_V4 = 4      # V4 (rare)
    VERSION_V5 = 5      # V5 - sparse format, not directly parseable
    VERSION_V6 = 6      # V6 - full format, fully parseable

    # Known data start offsets
    V6_DATA_START = 16456
    V3_DATA_START_RANGE = (1000, 5000)

    def __init__(self, dl_path: str):
        self.dl_path = Path(dl_path)
        with open(self.dl_path, 'rb') as f:
            self.dl_data = f.read()

        # Detect format
        self.format_info = self.detect_format()

        if not self.format_info:
            raise ValueError(f"Unknown DL format: {self.dl_path.name}")

    def detect_format(self) -> Optional[Dict]:
        """Detect DL file format by analyzing header fields."""
        if len(self.dl_data) < 32:
            return None

        # Read header fields
        magic = struct.unpack('<I', self.dl_data[0:4])[0]
        field_08 = struct.unpack('<I', self.dl_data[8:12])[0]  # Version indicator

        if magic == self.MAGIC_V3:
            return self._detect_v3_format(field_08)
        elif magic == self.MAGIC_V5_V6:
            return self._detect_v5_v6_format(field_08)
        else:
            return None

    def _detect_v3_format(self, field_08: int) -> Dict:
        """Detect V3 / Terminator X format specifics."""
        # V3: 516 floats per row, no interleaving
        FLOATS_PER_ROW = 516
        BYTES_PER_ROW = FLOATS_PER_ROW * 4

        # Search for data start (typically around 3000-4000 bytes)
        for data_start in range(self.V3_DATA_START_RANGE[0], self.V3_DATA_START_RANGE[1], 100):
            data_size = len(self.dl_data) - data_start
            if data_size % BYTES_PER_ROW < 100:  # Allow small remainder
                num_rows = data_size // BYTES_PER_ROW

                # Validate by checking for reasonable float values
                try:
                    # Sample a few values
                    offset = data_start + (10 * 4)  # Position 10 (should be a sensor value)
                    val = struct.unpack('<f', self.dl_data[offset:offset+4])[0]
                    if 0 <= abs(val) < 50000:  # Reasonable sensor range
                        return {
                            'version': 'V3',
                            'version_field': field_08,
                            'magic': self.MAGIC_V3,
                            'floats_per_row': FLOATS_PER_ROW,
                            'bytes_per_row': BYTES_PER_ROW,
                            'data_start': data_start,
                            'num_rows': num_rows,
                            'interleaved': False
                        }
                except:
                    pass

        return None

    def _detect_v5_v6_format(self, field_08: int) -> Dict:
        """
        Detect V5/V6 format specifics using field_08 version indicator.

        V6 (field_08=6): Full format with fixed data_start=16456, 1030 floats/row interleaved
        V5 (field_08=5): Sparse format - NOT directly parseable, requires Holley software
        V4 (field_08=4): Older format, may have different structure
        """
        FLOATS_PER_ROW = 1030
        BYTES_PER_ROW = FLOATS_PER_ROW * 4

        # Handle V6 format (field_08 = 6) - fully supported
        if field_08 == self.VERSION_V6:
            data_start = self.V6_DATA_START
            data_size = len(self.dl_data) - data_start
            num_rows = data_size // BYTES_PER_ROW
            remainder = data_size % BYTES_PER_ROW

            # Validate the structure
            if num_rows > 0 and remainder < 100:
                return {
                    'version': 'V6',
                    'version_field': field_08,
                    'magic': self.MAGIC_V5_V6,
                    'floats_per_row': FLOATS_PER_ROW,
                    'bytes_per_row': BYTES_PER_ROW,
                    'data_start': data_start,
                    'num_rows': num_rows,
                    'interleaved': True
                }

        # Handle V5 format (field_08 = 5) - sparse format, not directly parseable
        elif field_08 == self.VERSION_V5:
            raise ValueError(
                f"V5 format detected (field_08={field_08}). "
                "V5 files use sparse storage and cannot be parsed directly. "
                "Please open this file in Holley EFI software first - it will "
                "automatically convert to V6 format (.V6.dl) which can be parsed."
            )

        # Handle V4 or other versions - try heuristic detection
        else:
            # Fall back to searching for data section
            return self._detect_v5_v6_heuristic(field_08)

    def _detect_v5_v6_heuristic(self, field_08: int) -> Optional[Dict]:
        """
        Heuristic detection for unknown V4/V5/V6 variants.
        Searches for RPM-like values to find data section.
        """
        FLOATS_PER_ROW = 1030
        BYTES_PER_ROW = FLOATS_PER_ROW * 4

        # Search for data start by looking for RPM values
        for search_offset in range(15000, 18000, 4):
            try:
                val = struct.unpack('<f', self.dl_data[search_offset:search_offset+4])[0]
                # Look for reasonable RPM values (300-10000)
                if 300 < val < 10000:
                    # Assume this is RPM at position 4 (byte 16 in row)
                    potential_data_start = search_offset - (4 * 4)

                    data_size = len(self.dl_data) - potential_data_start
                    remainder = data_size % BYTES_PER_ROW

                    if remainder < 100:
                        num_rows = data_size // BYTES_PER_ROW

                        # Verify with TPS check
                        tps_offset = potential_data_start + (66 * 4)
                        if tps_offset + 4 <= len(self.dl_data):
                            tps = struct.unpack('<f', self.dl_data[tps_offset:tps_offset+4])[0]
                            if 0 <= tps <= 100:
                                version = f'V{field_08}' if field_08 >= 4 else 'V5/V6'
                                return {
                                    'version': version,
                                    'version_field': field_08,
                                    'magic': self.MAGIC_V5_V6,
                                    'floats_per_row': FLOATS_PER_ROW,
                                    'bytes_per_row': BYTES_PER_ROW,
                                    'data_start': potential_data_start,
                                    'num_rows': num_rows,
                                    'interleaved': True
                                }
            except:
                pass

        return None

    def get_column_names_v3(self) -> list:
        """Get column names for V3 format (516 columns, not interleaved)."""
        # Standard Holley CSV column names
        # In V3, these map 1:1 to positions
        return [
            'Point Number', 'RTC', 'RPM', 'Inj PW', 'Duty Cycle', 'CL Comp',
            'Target AFR', 'AFR Left', 'AFR Right', 'AFR Average', 'Air Temp Enr',
            # ... (full list would be all 516 columns)
            # For now, use generic names
        ] + [f'Param_{i}' for i in range(10, 516)]

    def get_column_names_v5_v6(self) -> list:
        """Get column names for V5/V6 format (516 columns from 1030 positions)."""
        # Same as V3 but data is at every 2nd position
        return self.get_column_names_v3()

    def parse(self) -> pd.DataFrame:
        """Parse DL file based on detected format."""
        if not self.format_info:
            raise ValueError("Cannot parse: Unknown format")

        version = self.format_info['version']
        data_start = self.format_info['data_start']
        bytes_per_row = self.format_info['bytes_per_row']
        num_rows = self.format_info['num_rows']
        interleaved = self.format_info['interleaved']

        print(f"Parsing {self.dl_path.name}")
        print(f"  Format: {version}")
        print(f"  Rows: {num_rows}")
        print(f"  Data start: {data_start}")

        if interleaved:
            return self._parse_interleaved(data_start, bytes_per_row, num_rows)
        else:
            return self._parse_non_interleaved(data_start, bytes_per_row, num_rows)

    def _parse_non_interleaved(self, data_start: int, bytes_per_row: int, num_rows: int) -> pd.DataFrame:
        """Parse non-interleaved format (V3)."""
        floats_per_row = bytes_per_row // 4

        # Parse all data
        data_dict = {}

        for col_idx in range(floats_per_row):
            col_name = f'Param_{col_idx:03d}'
            col_data = []

            for row_idx in range(num_rows):
                row_offset = data_start + (row_idx * bytes_per_row)
                col_offset = col_idx * 4
                offset = row_offset + col_offset

                if offset + 4 <= len(self.dl_data):
                    value = struct.unpack('<f', self.dl_data[offset:offset+4])[0]
                    col_data.append(value)
                else:
                    col_data.append(np.nan)

            data_dict[col_name] = col_data

        return pd.DataFrame(data_dict)

    def _parse_interleaved(self, data_start: int, bytes_per_row: int, num_rows: int) -> pd.DataFrame:
        """Parse interleaved format (V5/V6)."""
        # Data is at every 2nd position (0, 2, 4, 6, ...)
        num_columns = 516  # Maximum CSV columns

        data_dict = {}

        for csv_col_idx in range(num_columns):
            dl_position = csv_col_idx * 2  # Interleaved: multiply by 2
            col_name = f'Param_{csv_col_idx:03d}'
            col_data = []

            for row_idx in range(num_rows):
                row_offset = data_start + (row_idx * bytes_per_row)
                col_offset = dl_position * 4
                offset = row_offset + col_offset

                if offset + 4 <= len(self.dl_data):
                    value = struct.unpack('<f', self.dl_data[offset:offset+4])[0]
                    col_data.append(value)
                else:
                    col_data.append(np.nan)

            data_dict[col_name] = col_data

        return pd.DataFrame(data_dict)

    def get_info(self) -> Dict:
        """Get format information."""
        return {
            'filename': self.dl_path.name,
            'file_size': len(self.dl_data),
            **self.format_info
        }


def main():
    import sys

    if len(sys.argv) < 2:
        print("Universal Holley DL Parser")
        print()
        print("Supports V3, V5, and V6 formats")
        print()
        print("Usage: python universal_dl_parser.py <file.dl> [output.csv]")
        sys.exit(1)

    dl_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        parser = UniversalDLParser(dl_path)

        # Show info
        info = parser.get_info()
        print(f"\nDetected Format:")
        print(f"  Version: {info['version']}")
        print(f"  Magic: 0x{info['magic']:08X}")
        print(f"  Rows: {info['num_rows']}")
        print(f"  Floats per row: {info['floats_per_row']}")
        print(f"  Interleaved: {info['interleaved']}")
        print()

        # Parse
        df = parser.parse()

        print(f"\nParsed: {len(df)} rows × {len(df.columns)} columns")
        print(f"\nFirst few rows:")
        print(df.head())

        # Save if output specified
        if output_path:
            df.to_csv(output_path, index=False)
            print(f"\n✓ Saved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
