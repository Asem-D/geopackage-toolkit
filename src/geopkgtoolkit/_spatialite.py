"""
SpatiaLite connection helper.

Handles Windows-specific DLL loading and provides a clean
connect() function that returns a ready-to-use spatial connection.
"""

import os
import sqlite3
from pathlib import Path

# SpatiaLite DLL directory (Windows only)
_SPATIALITE_DIR = os.environ.get("SPATIALITE_DIR", r"C:\spatialite")


def connect(gpkg_path: str | Path, *, enable_gpkg_mode: bool = True) -> sqlite3.Connection:
    """Open a GeoPackage with SpatiaLite loaded.

    Args:
        gpkg_path: Path to the GeoPackage file.
        enable_gpkg_mode: Enable GeoPackage mode (default True).
            Set to False when you need ST_AsText/ST_AsBinary to work
            reliably after close/reopen cycles (SpatiaLite 5.1.0 bug).

    Returns:
        sqlite3.Connection with SpatiaLite extension loaded.

    Raises:
        FileNotFoundError: If the GeoPackage file does not exist.
        RuntimeError: If SpatiaLite cannot be loaded.

    Example:
        >>> con = connect("data.gpkg")
        >>> con.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
        515013
    """
    path = Path(gpkg_path)
    if not path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {path}")

    con = sqlite3.connect(str(path))
    con.enable_load_extension(True)

    # Windows: add SpatiaLite DLL directory before loading
    if os.name == "nt" and os.path.isdir(_SPATIALITE_DIR):
        os.add_dll_directory(_SPATIALITE_DIR)

    try:
        con.load_extension("mod_spatialite")
    except Exception as e:
        con.close()
        raise RuntimeError(
            f"Failed to load SpatiaLite. "
            f"Ensure mod_spatialite is installed and SPATIALITE_DIR is correct. "
            f"Current: {_SPATIALITE_DIR}. Error: {e}"
        ) from e

    # Enable GeoPackage extensions
    if enable_gpkg_mode:
        try:
            con.execute("SELECT EnableGpkgMode()")
        except Exception:
            pass  # Not all SpatiaLite builds support this

    return con


def list_layers(con: sqlite3.Connection) -> list[dict]:
    """List all feature layers in a GeoPackage connection.

    Args:
        con: A sqlite3 connection with SpatiaLite loaded.

    Returns:
        List of dicts with keys: table_name, column_name, geometry_type, srs_id.
    """
    rows = con.execute(
        "SELECT table_name, column_name, geometry_type_name, srs_id "
        "FROM gpkg_geometry_columns"
    ).fetchall()
    return [
        {
            "table_name": r[0],
            "column_name": r[1],
            "geometry_type": r[2],
            "srs_id": r[3],
        }
        for r in rows
    ]
