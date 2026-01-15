#!/usr/bin/env python3
"""
Comprehensive DL File Mapper

Systematically maps all CSV columns to DL binary format.
Attempts to locate and parse every parameter.
"""

import struct
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json


class ComprehensiveDLMapper:
    """Maps all CSV columns to DL binary offsets."""

    def __init__(self, csv_path: str, dl_path: str):
        self.csv_path = Path(csv_path)
        self.dl_path = Path(dl_path)

        # Load CSV
        print(f"Loading CSV: {self.csv_path.name}")
        encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                self.df = pd.read_csv(self.csv_path, skiprows=[1], encoding=encoding)
                print(f"  ✓ Loaded with encoding: {encoding}")
                break
            except UnicodeDecodeError:
                continue

        print(f"  Rows: {len(self.df)}, Columns: {len(self.df.columns)}")

        # Load DL
        print(f"Loading DL: {self.dl_path.name}")
        with open(self.dl_path, 'rb') as f:
            self.dl_data = f.read()
        print(f"  Size: {len(self.dl_data):,} bytes\n")

        # Known structure from previous analysis
        self.FLOATS_PER_ROW = 1030
        self.BYTES_PER_ROW = self.FLOATS_PER_ROW * 4
        self.NUM_CSV_COLS = len(self.df.columns)
        self.NUM_ROWS = len(self.df)

        # Results
        self.column_map = {}
        self.unmapped_columns = []

    def find_data_start(self) -> int:
        """Find where the data section starts in the DL file."""
        print("Searching for data section start...")

        # Search for first few distinctive values
        test_cols = ['RPM', 'Inj PW', 'TPS', 'Speed']
        found_col = None
        found_offset = None

        for col in test_cols:
            if col not in self.df.columns:
                continue

            value = self.df[col].iloc[0]
            value_bytes = struct.pack('<f', value)

            offset = self.dl_data.find(value_bytes)
            if offset >= 0:
                found_col = col
                found_offset = offset
                print(f"  ✓ Found {col} ({value:.6f}) at offset {offset}")
                break

        if found_offset is None:
            print("  ✗ Could not find data start automatically")
            return 16456  # Use known default

        # Calculate column index in CSV
        col_idx = self.df.columns.get_loc(found_col)

        # Calculate row start (accounting for interleaved structure)
        # Each CSV column occupies 2 float positions in DL
        floats_before = col_idx * 2
        bytes_before = floats_before * 4

        data_start = found_offset - bytes_before
        print(f"  → Data section starts at offset: {data_start}\n")

        return data_start

    def map_all_columns(self, data_start: int) -> Dict:
        """
        Systematically map all CSV columns to DL positions.

        Returns dict with mapping results.
        """
        print("=" * 80)
        print("MAPPING ALL COLUMNS")
        print("=" * 80)

        mapped = 0
        unmapped = 0
        partial = 0

        # Try to map each column
        for col_idx, col_name in enumerate(self.df.columns):
            result = self._map_column(col_idx, col_name, data_start)

            if result['status'] == 'mapped':
                self.column_map[col_name] = result
                mapped += 1
                print(f"✓ {col_idx:3d}. {col_name:40s} → DL pos {result['dl_position']:4d} ({result['match_rate']:.1f}%)")

            elif result['status'] == 'partial':
                self.column_map[col_name] = result
                partial += 1
                print(f"⚠ {col_idx:3d}. {col_name:40s} → DL pos {result['dl_position']:4d} ({result['match_rate']:.1f}%) PARTIAL")

            else:
                self.unmapped_columns.append(col_name)
                unmapped += 1
                print(f"✗ {col_idx:3d}. {col_name:40s} → NOT FOUND")

        print("\n" + "=" * 80)
        print(f"RESULTS: {mapped} mapped, {partial} partial, {unmapped} unmapped")
        print("=" * 80)

        return {
            'mapped': mapped,
            'partial': partial,
            'unmapped': unmapped,
            'total': len(self.df.columns)
        }

    def _map_column(self, col_idx: int, col_name: str, data_start: int) -> Dict:
        """
        Attempt to map a single column.

        Strategy:
        1. Get first 5 values from CSV
        2. Search for matching pattern in DL
        3. Verify with multiple rows
        """
        # Get test values
        test_values = self.df[col_name].dropna().head(10).values

        if len(test_values) == 0:
            return {'status': 'unmapped', 'reason': 'no data'}

        # Convert to numeric if possible
        try:
            test_values = np.array(test_values, dtype=float)
        except:
            return {'status': 'unmapped', 'reason': 'non-numeric'}

        # Try hypothesis: column index * 2 (interleaved structure)
        dl_position = col_idx * 2

        # Verify this position across multiple rows
        matches = 0
        total_checked = min(10, len(self.df))

        for row_idx in range(total_checked):
            csv_val = self.df[col_name].iloc[row_idx]

            # Calculate DL offset for this row and column
            row_offset = data_start + (row_idx * self.BYTES_PER_ROW)
            col_offset = dl_position * 4  # 4 bytes per float

            dl_offset = row_offset + col_offset

            if dl_offset + 4 <= len(self.dl_data):
                dl_val = struct.unpack('<f', self.dl_data[dl_offset:dl_offset + 4])[0]

                # Check match
                if abs(csv_val - dl_val) < 0.001:
                    matches += 1

        match_rate = (matches / total_checked) * 100

        if matches == total_checked:
            return {
                'status': 'mapped',
                'dl_position': dl_position,
                'csv_index': col_idx,
                'match_rate': match_rate,
                'matches': matches,
                'total_checked': total_checked
            }
        elif matches >= total_checked * 0.7:  # 70% match
            return {
                'status': 'partial',
                'dl_position': dl_position,
                'csv_index': col_idx,
                'match_rate': match_rate,
                'matches': matches,
                'total_checked': total_checked
            }
        else:
            # Try searching for the value elsewhere
            first_val = test_values[0]
            val_bytes = struct.pack('<f', first_val)

            offset = self.dl_data.find(val_bytes, data_start, data_start + self.BYTES_PER_ROW * 5)

            if offset >= 0:
                # Found it elsewhere - calculate position
                offset_in_row = (offset - data_start) % self.BYTES_PER_ROW
                dl_pos_alt = offset_in_row // 4

                return {
                    'status': 'unmapped',
                    'reason': 'wrong position',
                    'expected_pos': dl_position,
                    'found_at': dl_pos_alt,
                    'match_rate': 0
                }

            return {
                'status': 'unmapped',
                'reason': 'value not found',
                'match_rate': 0
            }

    def export_mapping(self, output_path: str):
        """Export the mapping to JSON."""
        mapping_data = {
            'csv_file': str(self.csv_path.name),
            'dl_file': str(self.dl_path.name),
            'num_rows': self.NUM_ROWS,
            'num_csv_columns': self.NUM_CSV_COLS,
            'floats_per_dl_row': self.FLOATS_PER_ROW,
            'column_mapping': self.column_map,
            'unmapped_columns': self.unmapped_columns
        }

        with open(output_path, 'w') as f:
            json.dump(mapping_data, f, indent=2)

        print(f"\n✓ Exported mapping to: {output_path}")

    def generate_parser_code(self, output_path: str):
        """Generate Python code for a DL parser based on the mapping."""
        code = '''#!/usr/bin/env python3
"""
Auto-generated DL Parser

Generated from mapping analysis.
"""

import struct
import pandas as pd
import numpy as np

class HolleyDLParser:
    """Parse Holley DL files based on discovered structure."""

    def __init__(self, dl_path):
        with open(dl_path, 'rb') as f:
            self.dl_data = f.read()

        self.FLOATS_PER_ROW = {floats_per_row}
        self.BYTES_PER_ROW = self.FLOATS_PER_ROW * 4
        self.DATA_START = {data_start}

    def parse(self):
        """Parse the DL file to DataFrame."""
        # Calculate number of rows
        data_size = len(self.dl_data) - self.DATA_START
        num_rows = data_size // self.BYTES_PER_ROW

        # Column mapping
        columns = {columns_dict}

        # Parse data
        data = {{}}
        for col_name, dl_pos in columns.items():
            col_data = []

            for row_idx in range(num_rows):
                row_offset = self.DATA_START + (row_idx * self.BYTES_PER_ROW)
                col_offset = dl_pos * 4
                offset = row_offset + col_offset

                if offset + 4 <= len(self.dl_data):
                    value = struct.unpack('<f', self.dl_data[offset:offset + 4])[0]
                    col_data.append(value)
                else:
                    col_data.append(np.nan)

            data[col_name] = col_data

        return pd.DataFrame(data)


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <file.dl> [output.csv]")
        sys.exit(1)

    dl_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    parser = HolleyDLParser(dl_path)
    df = parser.parse()

    print(f"Parsed {{len(df)}} rows × {{len(df.columns)}} columns")

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"Saved to {{output_path}}")
    else:
        print(df.head())


if __name__ == "__main__":
    main()
'''

        # Fill in the template
        data_start = self.find_data_start()

        # Only include successfully mapped columns
        mapped_cols = {name: info['dl_position']
                      for name, info in self.column_map.items()
                      if info['status'] == 'mapped'}

        code = code.format(
            floats_per_row=self.FLOATS_PER_ROW,
            data_start=data_start,
            columns_dict=repr(mapped_cols)
        )

        with open(output_path, 'w') as f:
            f.write(code)

        print(f"✓ Generated parser code: {output_path}")
        print(f"  Includes {len(mapped_cols)} mapped columns")


def main():
    import sys

    if len(sys.argv) < 3:
        print("Comprehensive DL Mapper")
        print()
        print("Usage: python comprehensive_dl_mapper.py <file.csv> <file.dl> [output_mapping.json]")
        print()
        print("Maps all CSV columns to DL binary positions.")
        sys.exit(1)

    csv_path = sys.argv[1]
    dl_path = sys.argv[2]
    output_json = sys.argv[3] if len(sys.argv) > 3 else "dl_mapping.json"

    mapper = ComprehensiveDLMapper(csv_path, dl_path)

    # Find data start
    data_start = mapper.find_data_start()

    # Map all columns
    results = mapper.map_all_columns(data_start)

    # Export results
    mapper.export_mapping(output_json)

    # Generate parser code
    parser_output = output_json.replace('.json', '_parser.py')
    mapper.generate_parser_code(parser_output)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total columns:     {results['total']}")
    print(f"✓ Fully mapped:    {results['mapped']} ({100*results['mapped']/results['total']:.1f}%)")
    print(f"⚠ Partially mapped: {results['partial']} ({100*results['partial']/results['total']:.1f}%)")
    print(f"✗ Unmapped:        {results['unmapped']} ({100*results['unmapped']/results['total']:.1f}%)")
    print()

    if mapper.unmapped_columns:
        print("Unmapped columns:")
        for col in mapper.unmapped_columns[:20]:
            print(f"  - {col}")
        if len(mapper.unmapped_columns) > 20:
            print(f"  ... and {len(mapper.unmapped_columns) - 20} more")

    print("\n✓ Mapping complete!")


if __name__ == "__main__":
    main()
