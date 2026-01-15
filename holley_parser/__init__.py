"""
Holley EFI Parser - Reverse-engineered parser for Holley EFI data logs.

This package provides tools for parsing and analyzing Holley EFI binary log files
(.DL and .DLZ formats) commonly used in drag racing and performance tuning.

Key Features:
- Parse V3, V5, and V6 Holley DL formats (99.6% success rate)
- Decompress DLZ files (RLE compression)
- Batch analysis of multiple log files
- CSV export and comparison tools
- OCR-based timeslip extraction (optional)

Basic Usage:
    >>> from holley_parser import UniversalDLParser
    >>> parser = UniversalDLParser('mylog.dl')
    >>> df = parser.parse()
    >>> print(f"Parsed {len(df)} rows with {len(df.columns)} parameters")

For DLZ files:
    >>> from holley_parser import decompress_dlz
    >>> with open('mylog.DLZ', 'rb') as f:
    >>>     dlz_data = f.read()
    >>> dl_data = decompress_dlz(dlz_data)
    >>> with open('mylog.dl', 'wb') as f:
    >>>     f.write(dl_data)
"""

from .version import __version__
from .universal_dl_parser import UniversalDLParser
from .dlz_decompressor import decompress_dlz, decompress_file
from .batch_dl_analyzer import BatchDLAnalyzer
from .comprehensive_dl_mapper import ComprehensiveDLMapper
from .csv_dl_comparator import CSVDLComparator
from .dl_analyzer import DLFileAnalyzer

__all__ = [
    "__version__",
    "UniversalDLParser",
    "decompress_dlz",
    "decompress_file",
    "BatchDLAnalyzer",
    "ComprehensiveDLMapper",
    "CSVDLComparator",
    "DLFileAnalyzer",
]

# Package metadata
__author__ = "Justin"
__license__ = "MIT"
__description__ = "Reverse-engineered parser for Holley EFI binary data logs"
