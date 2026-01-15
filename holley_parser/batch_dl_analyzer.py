#!/usr/bin/env python3
"""
Batch DL File Analyzer

Recursively analyzes all DL files to identify:
- Holley V5 vs V6 vs Terminator X V3 formats
- Format variations
- Magic numbers and header structures
- Parsing success rate
"""

import struct
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json


class BatchDLAnalyzer:
    """Analyze multiple DL files to identify format variations."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.results = []

    def find_all_dl_files(self) -> List[Path]:
        """Recursively find all DL files."""
        dl_files = []
        for ext in ['*.dl', '*.DL']:
            dl_files.extend(self.root_path.rglob(ext))
        return sorted(dl_files)

    def identify_version_from_filename(self, filepath: Path) -> Optional[str]:
        """Identify version from filename if explicitly labeled."""
        name_lower = filepath.name.lower()
        if '.v5.' in name_lower or name_lower.endswith('.v5'):
            return 'V5'
        elif '.v6.' in name_lower or name_lower.endswith('.v6'):
            return 'V6'
        elif 'termx' in name_lower or 'term_x' in name_lower:
            return 'Terminator X V3'
        return None

    def analyze_header(self, filepath: Path) -> Dict:
        """Analyze DL file header structure."""
        try:
            with open(filepath, 'rb') as f:
                # Read first 512 bytes
                header = f.read(512)

                if len(header) < 32:
                    return {'error': 'File too small'}

                # Extract header fields
                magic = struct.unpack('<I', header[0:4])[0]
                field_08 = struct.unpack('<I', header[8:12])[0]
                field_16 = struct.unpack('<I', header[16:20])[0]
                field_24 = struct.unpack('<I', header[24:28])[0]

                # Get file size and calculate possible row count
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()

                # Try to find data start by searching for distinctive pattern
                f.seek(0)
                data = f.read()

                # Look for data section start (typically around 16456)
                # Search for non-zero float sequences
                data_start_candidates = []
                for offset in range(10000, min(20000, len(data) - 100), 100):
                    # Check if we have a sequence of reasonable float values
                    try:
                        vals = struct.unpack('<10f', data[offset:offset+40])
                        # Check if values are in reasonable range for sensor data
                        if any(0 < abs(v) < 10000 for v in vals):
                            data_start_candidates.append(offset)
                            if len(data_start_candidates) >= 3:
                                break
                    except:
                        pass

                estimated_data_start = data_start_candidates[0] if data_start_candidates else 16456

                # Calculate possible structure
                data_size = file_size - estimated_data_start

                # Test different row sizes
                possible_floats_per_row = []
                for floats in [516, 1030, 1032, 2060]:
                    bytes_per_row = floats * 4
                    if data_size % bytes_per_row == 0 or abs((data_size % bytes_per_row) / bytes_per_row) < 0.01:
                        rows = data_size // bytes_per_row
                        possible_floats_per_row.append((floats, rows))

                return {
                    'magic': f"0x{magic:08X}",
                    'field_08': field_08,
                    'field_16': field_16,
                    'field_24': field_24,
                    'file_size': file_size,
                    'estimated_data_start': estimated_data_start,
                    'possible_structures': possible_floats_per_row,
                    'header_hex': header[:32].hex()
                }

        except Exception as e:
            return {'error': str(e)}

    def test_parse(self, filepath: Path) -> Dict:
        """Test parsing with dynamic pattern detection for V5, V6, and Terminator X V3 formats."""
        try:
            with open(filepath, 'rb') as f:
                data = f.read()

            file_size = len(data)

            # Detect format based on magic number
            magic = struct.unpack('<I', data[0:4])[0]
            is_v6_termx = (magic == 0x0095365F)

            # For V6/Terminator X V3, find where 0xFE markers end
            fe_region_end = 10000
            if is_v6_termx:
                # Find last significant 0xFE byte cluster
                for i in range(8000, 15000, 100):
                    if i + 100 < len(data):
                        chunk = data[i:i+100]
                        if chunk.count(0xFE) > 50:  # More than 50% are 0xFE
                            fe_region_end = i + 100

            # Search multiple data start offsets
            possible_starts = [10000, 12000, 14000, 16000, 16172, 16236, 16372, 16456, 18000]
            if is_v6_termx:
                possible_starts = [max(fe_region_end, s) for s in possible_starts]

            best_match = None
            best_score = 0

            for data_start in possible_starts:
                if data_start >= file_size - 10000:
                    continue

                data_size = file_size - data_start

                # Dynamically find row sizes that evenly divide the data
                # Try bytes_per_row from 1000 to 10000, must be multiple of 4
                for bytes_per_row in range(1000, min(10000, data_size // 100), 4):
                    remainder = data_size % bytes_per_row

                    # Allow small remainder (incomplete last row)
                    if remainder > min(bytes_per_row * 0.02, 500):
                        continue

                    num_rows = data_size // bytes_per_row
                    floats_per_row = bytes_per_row // 4

                    # Need reasonable number of rows (100-10000)
                    if num_rows < 100 or num_rows > 10000:
                        continue

                    # Validate by checking for reasonable sensor value patterns
                    try:
                        score = 0
                        sample_values = []

                        # Check first 10 rows for reasonable float patterns
                        for row in range(min(10, num_rows)):
                            row_offset = data_start + (row * bytes_per_row)

                            # Read first 20 floats of this row (or fewer if row is shorter)
                            floats_to_read = min(20, floats_per_row)
                            bytes_to_read = floats_to_read * 4

                            floats = struct.unpack(f'<{floats_to_read}f', data[row_offset:row_offset+bytes_to_read])

                            # Count reasonable sensor values
                            # Sensor data typically: 0-10000 range, not too many exact zeros
                            reasonable = sum(1 for v in floats if 0.01 < abs(v) < 10000)
                            zero_count = sum(1 for v in floats if v == 0.0)
                            inf_nan_count = sum(1 for v in floats if not (-1e10 < v < 1e10))

                            # Good patterns: many reasonable values, not all zeros, no inf/nan
                            if reasonable >= 3 and zero_count <= floats_to_read - 2 and inf_nan_count == 0:
                                score += reasonable
                                if row == 0:
                                    sample_values = [f for f in floats[:10] if abs(f) < 10000]

                        # Keep track of best match
                        # Need at least 20 reasonable values across 10 rows = avg 2 per row
                        if score > best_score and score >= 20:
                            best_score = score
                            best_match = {
                                'parseable': True,
                                'data_start': data_start,
                                'num_rows': num_rows,
                                'floats_per_row': floats_per_row,
                                'sample_values': sample_values[:5],
                                'confidence_score': score,
                                'format_hint': 'v6_termx' if is_v6_termx else 'v5'
                            }

                    except Exception:
                        pass

            if best_match:
                return best_match

            return {'parseable': False, 'reason': 'Could not find valid data pattern'}

        except Exception as e:
            return {'parseable': False, 'error': str(e)}

    def analyze_all(self) -> List[Dict]:
        """Analyze all DL files."""
        dl_files = self.find_all_dl_files()

        print(f"Found {len(dl_files)} DL files")
        print("=" * 80)

        results = []

        for i, filepath in enumerate(dl_files, 1):
            print(f"\r[{i}/{len(dl_files)}] Analyzing: {filepath.name[:50]:<50}", end='', flush=True)

            # Get relative path from root
            rel_path = filepath.relative_to(self.root_path)

            # Identify version
            version_label = self.identify_version_from_filename(filepath)

            # Analyze header
            header_info = self.analyze_header(filepath)

            # Test parsing
            parse_info = self.test_parse(filepath)

            result = {
                'file': str(rel_path),
                'filename': filepath.name,
                'version_label': version_label,
                'size_bytes': filepath.stat().st_size,
                'header': header_info,
                'parsing': parse_info
            }

            results.append(result)

        print("\n" + "=" * 80)
        return results

    def summarize_results(self, results: List[Dict]):
        """Print summary of analysis."""
        print("\n" + "=" * 80)
        print("ANALYSIS SUMMARY")
        print("=" * 80)

        # Count by version label
        v5_count = sum(1 for r in results if r['version_label'] == 'V5')
        v6_count = sum(1 for r in results if r['version_label'] == 'V6')
        termx_count = sum(1 for r in results if r['version_label'] == 'Terminator X V3')
        unlabeled_count = sum(1 for r in results if r['version_label'] is None)

        print(f"\nVersion Labels:")
        print(f"  V5:        {v5_count}")
        print(f"  V6:        {v6_count}")
        print(f"  Terminator X V3:     {termx_count}")
        print(f"  Unlabeled: {unlabeled_count}")
        print(f"  Total:     {len(results)}")

        # Count parseable
        parseable = sum(1 for r in results if r['parsing'].get('parseable', False))
        print(f"\nParsing Success:")
        print(f"  Parseable:     {parseable}/{len(results)} ({100*parseable/len(results):.1f}%)")
        print(f"  Not Parseable: {len(results) - parseable}")

        # Magic numbers
        magic_numbers = {}
        for r in results:
            magic = r['header'].get('magic', 'unknown')
            magic_numbers[magic] = magic_numbers.get(magic, 0) + 1

        print(f"\nMagic Numbers:")
        for magic, count in sorted(magic_numbers.items(), key=lambda x: -x[1]):
            print(f"  {magic}: {count} files")

        # Structure variations
        print(f"\nStructure Variations:")
        structures = {}
        for r in results:
            if r['parsing'].get('parseable', False):
                floats = r['parsing'].get('floats_per_row', 0)
                structures[floats] = structures.get(floats, 0) + 1

        for floats, count in sorted(structures.items()):
            print(f"  {floats} floats/row: {count} files")

        # Version-specific analysis
        print(f"\n" + "=" * 80)
        print("VERSION-SPECIFIC ANALYSIS")
        print("=" * 80)

        for version in ['V5', 'V6', 'Terminator X V3']:
            version_files = [r for r in results if r['version_label'] == version]
            if not version_files:
                continue

            print(f"\n{version} Files ({len(version_files)}):")

            # Magic numbers for this version
            version_magics = {}
            for r in version_files:
                magic = r['header'].get('magic', 'unknown')
                version_magics[magic] = version_magics.get(magic, 0) + 1

            print(f"  Magic numbers: {', '.join(f'{m} ({c})' for m, c in version_magics.items())}")

            # Parsing success
            version_parseable = sum(1 for r in version_files if r['parsing'].get('parseable', False))
            print(f"  Parseable: {version_parseable}/{len(version_files)} ({100*version_parseable/len(version_files):.1f}%)")

            # Sample file
            sample = version_files[0]
            print(f"  Sample: {sample['filename']}")
            if sample['parsing'].get('parseable', False):
                print(f"    Data start: {sample['parsing']['data_start']}")
                print(f"    Rows: {sample['parsing']['num_rows']}")
                print(f"    Floats/row: {sample['parsing']['floats_per_row']}")

        # Check for format differences
        print(f"\n" + "=" * 80)
        print("FORMAT DIFFERENCES")
        print("=" * 80)

        # Compare V5 vs V6 parseable files
        v5_parseable = [r for r in results if r['version_label'] == 'V5' and r['parsing'].get('parseable', False)]
        v6_parseable = [r for r in results if r['version_label'] == 'V6' and r['parsing'].get('parseable', False)]

        if v5_parseable and v6_parseable:
            v5_starts = [r['parsing']['data_start'] for r in v5_parseable]
            v6_starts = [r['parsing']['data_start'] for r in v6_parseable]

            print(f"\nData Start Offsets:")
            print(f"  V5: min={min(v5_starts)}, max={max(v5_starts)}, avg={sum(v5_starts)/len(v5_starts):.0f}")
            print(f"  V6: min={min(v6_starts)}, max={max(v6_starts)}, avg={sum(v6_starts)/len(v6_starts):.0f}")

            if min(v5_starts) != min(v6_starts):
                print(f"  ⚠️  Different data start offsets detected!")
            else:
                print(f"  ✓ Same data start offset pattern")

    def export_results(self, results: List[Dict], output_path: str):
        """Export results to JSON."""
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Exported detailed results to: {output_path}")


def main():
    import sys

    root_path = sys.argv[1] if len(sys.argv) > 1 else "/home/justin/holley/holley_dl_parser/mess"
    output_json = sys.argv[2] if len(sys.argv) > 2 else "batch_analysis_results.json"

    print("Batch DL File Analyzer")
    print("=" * 80)
    print(f"Root path: {root_path}")
    print()

    analyzer = BatchDLAnalyzer(root_path)
    results = analyzer.analyze_all()
    analyzer.summarize_results(results)
    analyzer.export_results(results, output_json)

    print("\n" + "=" * 80)
    print("Analysis complete!")


if __name__ == "__main__":
    main()
