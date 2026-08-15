# Contributing

Contributions to geopackage-toolkit are welcome. This document explains how to get started.

## Development Setup

### Prerequisites

1. Python 3.10 or later
2. SpatiaLite installed (see [Installation](installation.md))
3. Git

### Clone and Install

```bash
git clone https://github.com/Asem-D/geopackage-toolkit.git
cd geopackage-toolkit
pip install -e ".[dev,docs]"
```

### Run Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_validate.py

# Run specific test
pytest tests/test_validate.py::TestValidateLayer::test_osm_buildings -v
```

Tests run against real GeoPackage data if available (set `GPKG_TEST_DATA` environment variable), or skip gracefully if not.

### Build Documentation

```bash
# Serve documentation locally (with live reload)
mkdocs serve

# Build static documentation
mkdocs build
```

The documentation will be available at `http://localhost:8000`.

## Code Style

- **Docstrings**: Google-style (used by mkdocstrings for API reference)
- **Type hints**: Used in function signatures
- **No external dependencies**: The core package has zero dependencies
- **Windows compatibility**: All code must work on Windows with SpatiaLite

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add tests for new functionality
5. Run the test suite: `pytest`
6. Update documentation if needed
7. Commit with a clear message
8. Push to your fork
9. Open a Pull Request

### Commit Messages

Use clear, descriptive commit messages:

- `Add validation for Multipart geometries`
- `Fix bbox_filter returning duplicate IDs`
- `Update documentation with new examples`

### Pull Request Description

Describe:

- What the change does
- Why it is needed
- How to test it

## Reporting Issues

Open an issue on [GitHub](https://github.com/Asem-D/geopackage-toolkit/issues) with:

- **Description**: What happened vs. what you expected
- **Reproduction**: Minimal code to reproduce the issue
- **Environment**: Python version, OS, SpatiaLite version
- **GeoPackage**: Sample data if possible (or describe the schema)

## Feature Requests

Open an issue with:

- **Use case**: What problem does this solve?
- **Proposed API**: How would you use it?
- **Alternatives**: What workarounds exist?

## Architecture

```
geopkgtoolkit/
  __init__.py       # Public API exports
  _spatialite.py    # SpatiaLite connection helper
  validate.py       # Geometry validation
  query.py          # Spatial queries
  cli.py            # Command-line interface
```

### Design Principles

1. **Zero compiled dependencies**: Pure Python + SpatiaLite (SQL extension)
2. **Windows-first**: All code tested on Windows with SpatiaLite
3. **Rtree by default**: Spatial queries use rtree indexing when available
4. **Auto-indexing**: Create rtree indexes automatically when missing
5. **Clean API**: Simple functions with sensible defaults

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
