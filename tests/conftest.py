"""Test fixtures for geopkgtoolkit tests."""

import os
import pytest

# Real test data path (requires Mashriq.gpkg to exist)
MASHRIQ_GPKG = os.environ.get(
    "GPKG_TEST_DATA",
    r"E:\Data\GIS\Mashreq\Mashriq.gpkg",
)


@pytest.fixture(scope="session")
def mashriq_exists():
    """Skip if test data not available."""
    if not os.path.exists(MASHRIQ_GPKG):
        pytest.skip(f"Test data not found: {MASHRIQ_GPKG}")


@pytest.fixture(scope="session")
def mashriq_path(mashriq_exists):
    """Path to Mashriq.gpkg test data."""
    return MASHRIQ_GPKG


@pytest.fixture(scope="session")
def mashriq_con(mashriq_path):
    """Open SpatiaLite connection to Mashriq.gpkg (session-scoped)."""
    from geopkgtoolkit._spatialite import connect

    con = connect(mashriq_path)
    yield con
    con.close()
