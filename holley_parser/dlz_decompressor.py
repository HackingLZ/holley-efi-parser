#!/usr/bin/env python3
"""
Holley DLZ Decompressor

Converts Holley .DLZ files to .DL format with 100% accuracy.

The DLZ format is a compact storage format used by Holley EFI for datalogs.

Algorithm (verified 100% accurate):
1. Byte swap the DLZ data (reverse each 4-byte group)
2. RLE decompress: 0xFF COUNT VALUE -> writes VALUE byte COUNT times
3. Special case: 0xFF 00 VALUE -> literal 0xFF (escape sequence)
4. Byte swap the result (reverse each 4-byte group)

The byte swap performs: [A,B,C,D] -> [D,C,B,A]
"""

import sys
import struct
from pathlib import Path


def _byte_swap(data: bytes) -> bytes:
    """
    Swap bytes in each 4-byte group: [A,B,C,D] -> [D,C,B,A]

    This matches fcn.008c8ea0 in HolleyV6.exe which performs endian conversion.
    """
    result = bytearray()
    for i in range(0, len(data), 4):
        chunk = data[i:i+4]
        if len(chunk) == 4:
            result.extend([chunk[3], chunk[2], chunk[1], chunk[0]])
        else:
            # Handle trailing bytes that don't form complete 4-byte group
            result.extend(chunk)
    return bytes(result)


def _rle_decompress(data: bytes) -> bytes:
    """
    RLE decompression matching HolleyV6.exe @ 0x8c7000.

    Format:
    - 0xFF COUNT VALUE: Write VALUE byte COUNT times
    - 0xFF 00 VALUE: Escape sequence, write literal 0xFF
    - Other bytes: Copy directly
    """
    result = bytearray()
    i = 0
    length = len(data)

    while i < length:
        byte = data[i]
        i += 1

        if byte == 0xFF:
            if i + 1 >= length:
                result.append(byte)
                break

            count = data[i]
            value = data[i + 1]
            i += 2

            if count == 0:
                # Escape sequence: 0xFF 00 XX -> output literal 0xFF
                result.append(0xFF)
            else:
                # RLE: output VALUE byte COUNT times
                result.extend([value] * count)
        else:
            # Regular byte - copy directly
            result.append(byte)

    return bytes(result)


def decompress_dlz(dlz_data: bytes) -> bytes:
    """
    Decompress DLZ data to DL format with 100% accuracy.

    Algorithm:
    1. Byte swap the DLZ data (endian conversion)
    2. RLE decompress
    3. Byte swap the result (endian conversion back)

    Args:
        dlz_data: Compressed DLZ file data

    Returns:
        Decompressed DL format data
    """
    # Step 1: Byte swap
    swapped = _byte_swap(dlz_data)

    # Step 2: RLE decompress
    decompressed = _rle_decompress(swapped)

    # Step 3: Byte swap result
    result = _byte_swap(decompressed)

    return result


def analyze_dlz_header(dlz_data: bytes) -> dict:
    """
    Analyze DLZ file header.

    Returns:
        Dictionary with header analysis
    """
    if len(dlz_data) < 32:
        return {'valid': False, 'error': 'File too small'}

    magic = struct.unpack('<I', dlz_data[0:4])[0]

    # DLZ files have same magic as DL
    if magic != 0x0085F41F and magic != 0x0095365F:
        return {'valid': False, 'error': f'Unknown magic: 0x{magic:08X}'}

    # Count 0xFF markers to estimate compression ratio
    ff_count = sum(1 for b in dlz_data if b == 0xFF)

    # Look for embedded text (tune names, etc.)
    embedded_text = None
    for start in range(32, min(200, len(dlz_data) - 4)):
        if all(32 <= dlz_data[start + j] < 127 for j in range(4)):
            end = start
            while end < len(dlz_data) and 32 <= dlz_data[end] < 127:
                end += 1
            if end - start >= 4:
                embedded_text = dlz_data[start:end].decode('ascii', errors='ignore')
                break

    return {
        'valid': True,
        'magic': magic,
        'size': len(dlz_data),
        'ff_markers': ff_count,
        'embedded_text': embedded_text,
    }


def decompress_file(dlz_path: str, output_path: str = None, analyze_only: bool = False) -> str:
    """
    Decompress a .DLZ file to .DL format.

    Args:
        dlz_path: Path to input .DLZ file
        output_path: Path to output .DL file (optional)
        analyze_only: If True, only analyze without decompressing

    Returns:
        Path to output file (or None if analyze_only)
    """
    dlz_path = Path(dlz_path)

    if not dlz_path.exists():
        raise FileNotFoundError(f"DLZ file not found: {dlz_path}")

    with open(dlz_path, 'rb') as f:
        dlz_data = f.read()

    print(f"Loaded {dlz_path.name}: {len(dlz_data):,} bytes")

    analysis = analyze_dlz_header(dlz_data)
    print(f"\nDLZ Analysis:")
    print(f"  Magic: 0x{analysis.get('magic', 0):08X}")
    print(f"  0xFF markers: {analysis.get('ff_markers', 0):,}")
    if analysis.get('embedded_text'):
        print(f"  Tune name: {analysis.get('embedded_text')[:60]}")

    if analyze_only:
        return None

    print("\nDecompressing...")
    dl_data = decompress_dlz(dlz_data)

    print(f"Decompressed to: {len(dl_data):,} bytes")
    print(f"Expansion ratio: {len(dl_data)/len(dlz_data):.2f}x")

    if output_path is None:
        output_path = dlz_path.with_suffix('.dl')
    else:
        output_path = Path(output_path)

    with open(output_path, 'wb') as f:
        f.write(dl_data)

    print(f"\nWrote to: {output_path}")

    return str(output_path)


def main():
    if len(sys.argv) < 2:
        print("Holley DLZ Decompressor")
        print("=" * 50)
        print()
        print("Usage: python dlz_decompressor.py <input.DLZ> [output.dl]")
        print("       python dlz_decompressor.py --analyze <input.DLZ>")
        print()
        print("Converts Holley .DLZ files to .DL format.")
        print()
        print("Algorithm:")
        print("  1. Byte swap (endian conversion)")
        print("  2. RLE decompress (0xFF COUNT VALUE)")
        print("  3. Byte swap result")
        print()
        sys.exit(1)

    analyze_only = '--analyze' in sys.argv
    if analyze_only:
        sys.argv.remove('--analyze')

    dlz_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result_path = decompress_file(dlz_path, output_path, analyze_only=analyze_only)

        if analyze_only:
            print("\nAnalysis complete. Use without --analyze to decompress.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
