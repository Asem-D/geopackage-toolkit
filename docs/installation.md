# Installation

geopackage-toolkit requires **SpatiaLite** to be installed on your system. The Python package itself has zero compiled dependencies.

## Prerequisites: SpatiaLite

SpatiaLite is a SQLite extension that adds spatial SQL support. It must be available as a shared library on your system.

### Windows

1. Download the latest SpatiaLite binaries from [gaia-gis.it](https://www.gaia-gis.it/gaia-sins/windows-bin-amd64/):
    - Get `mod_spatialite-5.1.0-amd64.exe` (or latest version)
    - Extract to `C:\spatialite`

2. Set the environment variable:
    ```powershell
    # PowerShell
    $env:SPATIALITE_DIR = "C:\spatialite"

    # Or permanently via System Properties > Environment Variables
    ```

3. Verify the DLL exists:
    ```
    C:\spatialite\mod_spatialite.dll
    ```

!!! note
    If you see `RuntimeError: Failed to load SpatiaLite`, check that `mod_spatialite.dll` exists in the `SPATIALITE_DIR` directory.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install libspatialite-dev
```

SpatiaLite loads automatically on Linux (no environment variable needed).

### macOS

```bash
brew install libspatialite
```

### Conda

```bash
conda install -c conda-forge libspatialite
```

### Docker

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y libspatialite-dev && rm -rf /var/lib/apt/lists/*
RUN pip install geopackage-toolkit
```

## Installing the Python Package

### From PyPI (recommended)

```bash
pip install geopackage-toolkit
```

### From Source

```bash
git clone https://github.com/Asem-D/geopackage-toolkit.git
cd geopackage-toolkit
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"
```

This installs `pytest` for running tests.

## Verifying Installation

```python
from geopkgtoolkit import connect, validate_layers
print("geopackage-toolkit installed successfully")
```

Or use the CLI:

```bash
geopkg --help
```

## Troubleshooting

### "Failed to load SpatiaLite"

**Cause**: SpatiaLite shared library not found.

**Fix**:

1. Verify SpatiaLite is installed:
    - Windows: Check `C:\spatialite\mod_spatialite.dll` exists
    - Linux: Run `dpkg -l | grep spatialite`
    - macOS: Run `brew list libspatialite`

2. Set the correct path:
    - Windows: Set `SPATIALITE_DIR` environment variable
    - Linux/macOS: Usually automatic; check library path with `ldconfig -p | grep spatialite`

### "No module named 'geopkgtoolkit'"

**Cause**: Package not installed or wrong Python environment.

**Fix**:

```bash
pip install -e .
# or
python -m pip install -e .
```

### Windows: "DLL load failed"

**Cause**: Missing Visual C++ runtime or architecture mismatch (32-bit Python with 64-bit SpatiaLite).

**Fix**:

1. Ensure you are using 64-bit Python with 64-bit SpatiaLite
2. Install [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

## System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.10 or later |
| SpatiaLite | 5.0 or later (recommended) |
| OS | Windows, Linux, macOS |
| Disk | <1 MB for the package itself |
| RAM | Depends on your data |

## Next Steps

Once installed, head to the [Quick Start](quickstart.md) guide to validate and query your first GeoPackage.
