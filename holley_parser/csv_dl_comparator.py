#!/usr/bin/env python3
"""
CSV to DL File Comparator

Compares CSV data with DL binary format to map the data.
"""

import struct
import sys
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Dict


class CSVDLComparator:
    """Compares CSV and DL files to map the binary format."""

    def __init__(self, csv_path: str, dl_path: str):
        self.csv_path = Path(csv_path)
        self.dl_path = Path(dl_path)

        # Load CSV (try multiple encodings)
        print(f"Loading CSV: {self.csv_path.name}")
        encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                self.df = pd.read_csv(self.csv_path, skiprows=[1], encoding=encoding)
                print(f"  Loaded with encoding: {encoding}")
                break
            except UnicodeDecodeError:
                if encoding == encodings[-1]:
                    raise
                continue
        print(f"  Rows: {len(self.df)}, Columns: {len(self.df.columns)}")

        # Load DL binary
        print(f"Loading DL: {self.dl_path.name}")
        with open(self.dl_path, 'rb') as f:
            self.dl_data = f.read()
        print(f"  Size: {len(self.dl_data):,} bytes")
        print()

    def find_parameter_names(self) -> List[Tuple[int, str]]:
        """Extract parameter names from DL file."""
        print("FINDING PARAMETER NAMES IN DL FILE")
        print("-" * 80)

        param_names = []
        i = 0
        data = self.dl_data

        # Scan for printable strings
        while i < len(data):
            # Look for printable ASCII strings
            if 32 <= data[i] < 127:
                start = i
                while i < len(data) and 32 <= data[i] < 127:
                    i += 1

                string = data[start:i].decode('ascii', errors='ignore')

                # Filter for likely parameter names
                if len(string) >= 3 and any(c.isalpha() for c in string):
                    # Check if it looks like a CSV column name
                    for col in self.df.columns:
                        if col.lower() in string.lower() or string.lower() in col.lower():
                            param_names.append((start, string, col))
                            print(f"  Offset {start:8d}: '{string}' -> CSV column: '{col}'")
                            break
            i += 1

        print(f"\nFound {len(param_names)} matched parameter names")
        print()
        return param_names

    def search_for_data_values(self):
        """Search for CSV data values in the DL binary."""
        print("SEARCHING FOR DATA VALUES")
        print("-" * 80)

        # Pick a few distinctive columns to search for
        test_columns = []

        # Find columns with distinctive values
        for col in self.df.columns[:20]:  # Check first 20 columns
            try:
                values = self.df[col].dropna()
                if len(values) > 0:
                    # Look for numeric columns with non-zero values
                    if pd.api.types.is_numeric_dtype(values):
                        unique_count = len(values.unique())
                        if unique_count > 10:  # Has variety
                            test_columns.append(col)
                if len(test_columns) >= 5:
                    break
            except:
                pass

        print(f"Testing with columns: {test_columns}")
        print()

        for col_name in test_columns:
            print(f"Column: {col_name}")
            values = self.df[col_name].dropna().head(10).values

            print(f"  First 10 CSV values: {values[:10]}")

            # Search for these values as floats in the binary
            found_offsets = self._search_float_sequence(values[:5])

            if found_offsets:
                print(f"  ✓ Found matching sequence at offsets: {found_offsets[:3]}")
            else:
                print(f"  ✗ No matching sequence found")
            print()

    def _search_float_sequence(self, values: list, tolerance: float = 0.01) -> List[int]:
        """Search for a sequence of float values in the binary data."""
        found = []
        search_len = len(values)

        # Search through the file
        for offset in range(0, len(self.dl_data) - search_len * 4, 4):
            try:
                # Read sequence of floats
                floats = struct.unpack(f'<{search_len}f',
                                      self.dl_data[offset:offset + search_len * 4])

                # Check if matches
                matches = 0
                for f_val, csv_val in zip(floats, values):
                    if abs(f_val - csv_val) < tolerance or \
                       (abs(csv_val) > 0 and abs(f_val - csv_val) / abs(csv_val) < 0.01):
                        matches += 1

                if matches == search_len:
                    found.append(offset)

                # Also try as integers
                if offset % 4 == 0:
                    ints = struct.unpack(f'<{search_len}i',
                                        self.dl_data[offset:offset + search_len * 4])
                    if all(abs(int_val - csv_val) < tolerance for int_val, csv_val in zip(ints, values)):
                        found.append(offset)

            except:
                pass

        return found

    def analyze_data_section(self):
        """Try to identify the main data section."""
        print("ANALYZING DATA SECTION LAYOUT")
        print("-" * 80)

        num_rows = len(self.df)
        num_cols = len(self.df.columns)

        print(f"CSV has {num_rows} rows × {num_cols} columns")

        # Expected data size
        expected_size_float = num_rows * num_cols * 4  # 4 bytes per float
        expected_size_double = num_rows * num_cols * 8  # 8 bytes per double

        print(f"Expected data size: {expected_size_float:,} bytes (float) or {expected_size_double:,} bytes (double)")
        print(f"Actual DL file size: {len(self.dl_data):,} bytes")
        print()

        # Look for large sections of the file that could be data
        header = struct.unpack('<8I', self.dl_data[:32])
        print(f"Header values: {header}")

        # The third value (offset 24) is 7712, which might be number of records
        if header[6] > 0:  # offset 24
            potential_rows = header[6]
            potential_cols = num_cols

            # Try to find data section
            for start_offset in [256, 512, 1024, 2048, 4096, 8192, 16384]:
                if start_offset + potential_rows * potential_cols * 4 < len(self.dl_data):
                    print(f"\nTrying data section at offset {start_offset}:")
                    print(f"  Assuming {potential_rows} rows × {potential_cols} cols")

                    # Read first row
                    try:
                        first_row_data = struct.unpack(
                            f'<{potential_cols}f',
                            self.dl_data[start_offset:start_offset + potential_cols * 4]
                        )
                        print(f"  First row values: {first_row_data[:10]}")

                        # Compare with CSV first row
                        csv_first_row = self.df.iloc[0].values[:10]
                        print(f"  CSV first row:    {csv_first_row}")

                    except Exception as e:
                        print(f"  Error reading: {e}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python csv_dl_comparator.py <csv_file> <dl_file>")
        sys.exit(1)

    csv_path = sys.argv[1]
    dl_path = sys.argv[2]

    comparator = CSVDLComparator(csv_path, dl_path)

    # Find parameter names
    comparator.find_parameter_names()

    # Search for data values
    comparator.search_for_data_values()

    # Analyze data section
    comparator.analyze_data_section()


if __name__ == "__main__":
    main()
