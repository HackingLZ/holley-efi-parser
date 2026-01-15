"""
Setup configuration for holley-efi-parser package.
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read the long description from README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read version from version.py
version = {}
with open(this_directory / "holley_parser" / "version.py") as f:
    exec(f.read(), version)

setup(
    name="holley-efi-parser",
    version=version["__version__"],
    author="Justin",
    author_email="",  # Add your email if publishing to PyPI
    description="Parser for Holley EFI binary data logs (DL/DLZ formats)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/HackingLZ/holley-efi-parser",
    packages=find_packages(exclude=["tests", "examples", "docs"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pandas>=1.3.0",
        "numpy>=1.20.0",
    ],
    extras_require={
        "ocr": [
            "pytesseract>=0.3.8",
            "opencv-python>=4.5.0",
            "Pillow>=8.0.0",
        ],
        "dev": [
            "pytest>=6.2.0",
            "pytest-cov>=2.12.0",
            "black>=21.0",
            "flake8>=3.9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "holley-parse=holley_parser.universal_dl_parser:main",
            "holley-analyze=holley_parser.batch_dl_analyzer:main",
            "holley-compare=holley_parser.csv_dl_comparator:main",
        ],
    },
    package_data={},
    include_package_data=True,
    keywords="holley efi parser drag-racing telemetry",
    project_urls={
        "Documentation": "https://github.com/HackingLZ/holley-efi-parser/blob/main/README.md",
        "Source": "https://github.com/HackingLZ/holley-efi-parser",
        "Tracker": "https://github.com/HackingLZ/holley-efi-parser/issues",
    },
)
