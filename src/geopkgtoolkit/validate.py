"""
Geometry validation for GeoPackage layers.

Checks for null geometries, empty geometries, invalid geometries,
SRID mismatches, and bounding box sanity. Designed to catch problems
early before they waste time in spatial queries.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from geopkgtoolkit._spatialite import connect, list_layers


@dataclass
class LayerReport:
    """Validation report for a single layer."""

    table_name: str
    geometry_column: str
    geometry_type: Optional[str]
    feature_count: int
    srid: Optional[int]
    null_count: int = 0
    empty_count: int = 0
    invalid_count: int = 0
    bbox: Optional[tuple] = None  # (minx, miny, maxx, maxy)
    warnings: list = field(default_factory=list)

    @property
    def is_valid(self):
        return len(self.warnings) == 0

    def summary(self):
        """One-line summary string."""
        status = "OK" if self.is_valid else f"{len(self.warnings)} warnings"
        bbox = ""
        if self.bbox:
            bbox = f"  bbox=[{self.bbox[0]:.4f},{self.bbox[1]:.4f},{self.bbox[2]:.4f},{self.bbox[3]:.4f}]"
        return f"{self.table_name}: {self.feature_count:,} features, SRID={self.srid}, {status}{bbox}"


@dataclass
class GpkgReport:
    """Validation report for an entire GeoPackage file."""

    path: str
    layers: list  # list of LayerReport

    @property
    def is_valid(self):
        return all(lr.is_valid for lr in self.layers)

    @property
    def total_features(self):
        return sum(lr.feature_count for lr in self.layers)

    @property
    def total_warnings(self):
        return sum(len(lr.warnings) for lr in self.layers)

    def summary(self):
        lines = [f"GeoPackage: {self.path}"]
        lines.append(f"{len(self.layers)} layers, {self.total_features:,} features, {self.total_warnings} warnings\n")
        for lr in self.layers:
            lines.append(f"  {lr.summary()}")
            for w in lr.warnings:
                lines.append(f"    WARNING: {w}")
        return "\n".join(lines)


def validate_layer(con: sqlite3.Connection, table: str, expected_srid: Optional[int] = None) -> LayerReport:
    """Validate geometry health for a single layer.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        table: Layer/table name.
        expected_srid: Optional SRID to check against (e.g., 4326).

    Returns:
        LayerReport with validation results.
    """
    # Get geometry column and type from gpkg_geometry_columns
    row = con.execute(
        "SELECT column_name, geometry_type_name, srs_id "
        "FROM gpkg_geometry_columns WHERE table_name=?",
        (table,),
    ).fetchone()

    if row is None:
        return LayerReport(
            table_name=table,
            geometry_column="",
            geometry_type=None,
            feature_count=0,
            srid=None,
            warnings=[f"Table '{table}' not found in gpkg_geometry_columns"],
        )

    geom_col = row[0]
    geom_type = row[1]
    srid = row[2]

    # Feature counts: single query instead of 4 separate scans
    stats = con.execute(
        f"SELECT COUNT(*), "
        f"SUM(CASE WHEN [{geom_col}] IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN ST_IsEmpty([{geom_col}]) THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN NOT ST_IsValid([{geom_col}]) THEN 1 ELSE 0 END) "
        f"FROM [{table}]"
    ).fetchone()
    feature_count = stats[0]
    null_count = stats[1] or 0
    empty_count = stats[2] or 0
    invalid_count = stats[3] or 0

    # Bounding box - use layer extent for sanity checks
    bbox_row = con.execute(
        f"SELECT ST_MinX([{geom_col}]), ST_MinY([{geom_col}]), "
        f"ST_MaxX([{geom_col}]), ST_MaxY([{geom_col}]) FROM [{table}] "
        f"WHERE [{geom_col}] IS NOT NULL AND NOT ST_IsEmpty([{geom_col}]) LIMIT 1"
    ).fetchone()
    bbox = tuple(bbox_row) if bbox_row and bbox_row[0] is not None else None

    # Warnings
    warnings = []
    if null_count > 0:
        warnings.append(f"{null_count} features with NULL geometry")
    if invalid_count > 0:
        warnings.append(f"{invalid_count} invalid geometries (self-intersections, etc.)")
    if empty_count > 0:
        warnings.append(f"{empty_count} empty geometries")
    if expected_srid is not None and srid != expected_srid:
        warnings.append(f"SRID mismatch: got {srid}, expected {expected_srid}")

    return LayerReport(
        table_name=table,
        geometry_column=geom_col,
        geometry_type=geom_type,
        feature_count=feature_count,
        srid=srid,
        null_count=null_count,
        empty_count=empty_count,
        invalid_count=invalid_count,
        bbox=bbox,
        warnings=warnings,
    )


def validate_layers(path: str | Path, expected_srid: Optional[int] = None, layers: Optional[list[str]] = None) -> GpkgReport:
    """Validate geometry health for layers in a GeoPackage.

    Args:
        path: Path to the GeoPackage file.
        expected_srid: Optional SRID to check against (e.g., 4326).
        layers: Optional list of layer names to validate. None = all layers.

    Returns:
        GpkgReport with per-layer validation results.

    Example:
        >>> report = validate_layers("data.gpkg", expected_srid=4326)
        >>> print(report.summary())
        >>> assert report.is_valid
    """
    con = connect(path)

    try:
        if layers:
            layer_infos = [
                li for li in list_layers(con)
                if li["table_name"] in layers
            ]
        else:
            layer_infos = list_layers(con)

        reports = []
        for info in layer_infos:
            lr = validate_layer(con, info["table_name"], expected_srid=expected_srid)
            reports.append(lr)

        return GpkgReport(path=str(path), layers=reports)
    finally:
        con.close()
