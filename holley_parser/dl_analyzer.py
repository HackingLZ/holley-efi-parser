#!/usr/bin/env python3
"""
Holley DL File Format Analyzer

This tool analyzes Holley .DL binary files to understand the format.
"""

import struct
import sys
from pathlib import Path
from typing import BinaryIO, List, Tuple


class DLFileAnalyzer:
    """Analyzes Holley .DL files to understand the format."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_size = self.file_path.stat().st_size

    def analyze(self):
        """Run complete analysis on the file."""
        print(f"=" * 80)
        print(f"Analyzing: {self.file_path.name}")
        print(f"File size: {self.file_size:,} bytes ({self.file_size / 1024 / 1024:.2f} MB)")
        print(f"=" * 80)
        print()

        with open(self.file_path, 'rb') as f:
            self.analyze_header(f)
            self.find_strings(f)
            self.analyze_structure(f)

    def analyze_header(self, f: BinaryIO):
        """Analyze the file header."""
        print("HEADER ANALYSIS")
        print("-" * 80)

        f.seek(0)
        header = f.read(256)

        # Display first 256 bytes
        print("First 256 bytes (hex):")
        for i in range(0, 256, 16):
            hex_str = ' '.join(f'{b:02x}' for b in header[i:i+16])
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in header[i:i+16])
            print(f"{i:08x}  {hex_str:<48}  {ascii_str}")
        print()

        # Try to interpret header fields
        print("Header field interpretation (little-endian):")
        f.seek(0)

        fields = [
            (0, 4, "Magic/Version"),
            (4, 4, "Unknown 1"),
            (8, 4, "Count/Size 1"),
            (12, 4, "Unknown 2"),
            (16, 4, "Count/Size 2"),
            (20, 4, "Unknown 3"),
            (24, 4, "Count/Size 3"),
            (28, 4, "Unknown 4"),
        ]

        for offset, size, name in fields:
            f.seek(offset)
            data = f.read(size)
            val_uint = struct.unpack('<I', data)[0]
            val_int = struct.unpack('<i', data)[0]
            val_float = struct.unpack('<f', data)[0]

            hex_str = ' '.join(f'{b:02x}' for b in data)
            print(f"  Offset {offset:3d} ({name:15s}): {hex_str}  |  "
                  f"uint: {val_uint:12d}  int: {val_int:12d}  float: {val_float:12.4f}")
        print()

    def find_strings(self, f: BinaryIO):
        """Find readable strings in the file."""
        print("STRING ANALYSIS")
        print("-" * 80)

        f.seek(0)
        data = f.read()

        strings = []
        current_string = bytearray()

        for i, byte in enumerate(data):
            if 32 <= byte < 127:  # Printable ASCII
                current_string.append(byte)
            else:
                if len(current_string) >= 4:  # Minimum string length
                    strings.append((i - len(current_string), current_string.decode('ascii', errors='ignore')))
                current_string = bytearray()

        # Filter for parameter-like strings (common in Holley data)
        param_keywords = ['rpm', 'tps', 'afr', 'boost', 'pressure', 'temp', 'speed',
                         'gear', 'timing', 'fuel', 'oil', 'trans', 'knock', 'input', 'output']

        print(f"Found {len(strings)} strings (showing first 100):")
        for offset, string in strings[:100]:
            # Highlight likely parameter names
            marker = " ***" if any(kw in string.lower() for kw in param_keywords) else ""
            print(f"  Offset {offset:8d}: {string}{marker}")
        print()

    def analyze_structure(self, f: BinaryIO):
        """Try to identify structure patterns."""
        print("STRUCTURE ANALYSIS")
        print("-" * 80)

        # Look for repeating patterns
        f.seek(0)
        data = f.read()

        # Search for null-terminated string sections
        print("Looking for string table sections...")
        self._find_string_tables(data)

        # Search for data sections with regular patterns
        print("\nLooking for data array sections...")
        self._find_data_arrays(data)

    def _find_string_tables(self, data: bytes):
        """Find sections that look like string tables."""
        i = 0
        string_sections = []

        while i < len(data) - 100:
            # Look for clusters of printable strings
            strings_in_window = 0
            window_start = i

            for j in range(i, min(i + 1000, len(data))):
                if data[j] == 0 and j > i:
                    # Found null terminator
                    chunk = data[i:j]
                    if len(chunk) > 3 and all(32 <= b < 127 for b in chunk):
                        strings_in_window += 1
                        i = j + 1
                    else:
                        i += 1
                    break

            if strings_in_window > 5:
                string_sections.append((window_start, i, strings_in_window))

            i += 1

        print(f"  Found {len(string_sections)} potential string table sections:")
        for start, end, count in string_sections[:10]:
            print(f"    Offset {start:8d} - {end:8d}: {count} strings")

    def _find_data_arrays(self, data: bytes):
        """Find sections with regular numeric data patterns."""
        # Look for sections with regular float/int patterns
        chunk_size = 4096

        for offset in range(0, len(data) - chunk_size, chunk_size):
            chunk = data[offset:offset + chunk_size]

            # Try as float array
            try:
                floats = struct.unpack(f'<{chunk_size // 4}f', chunk)
                # Check if values look reasonable
                valid_floats = sum(1 for f in floats if -10000 < f < 10000 and not (f == 0))

                if valid_floats > chunk_size // 8:  # At least 12.5% valid
                    print(f"  Potential float array at offset {offset:8d}: "
                          f"{valid_floats}/{len(floats)} values in range")
                    print(f"    Sample values: {floats[:10]}")
            except:
                pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python dl_analyzer.py <path_to_dl_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    analyzer = DLFileAnalyzer(file_path)
    analyzer.analyze()


if __name__ == "__main__":
    main()
