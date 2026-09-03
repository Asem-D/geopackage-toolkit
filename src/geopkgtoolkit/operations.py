"""
Spatial operations for GeoPackage layers.

Provides buffer, clip, and intersect operations that create new
GeoPackage layers. All operations use SpatiaLite SQL and produce
non-destructive output (new layers, originals untouched).
"""

import sqlite3
import time
from typing import Optional

from geopkgtoolkit._spatialite import list_layers
from geopkgtoolkit.query import _get_geom_col, _get_rtree_table, _rtree_exists


def _get_srs_id(con: sqlite3.Connection, table: str, geom_col: Optional[str] = None) -> int:
    """Get the SRID for a table's geometry column."""
    if geom_col is None:
        geom_col = _get_geom_col(con, table)
    row = con.execute(
        "SELECT srs_id FROM gpkg_geometry_columns WHERE table_name=? AND column_name=?",
        (table, geom_col),
    ).fetchone()
    return row[0] if row else 4326


def _get_geom_type(con: sqlite3.Connection, table: str, geom_col: Optional[str] = None) -> str:
    """Get the geometry type name for a table."""
    if geom_col is None:
        geom_col = _get_geom_col(con, table)
    row = con.execute(
        "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name=? AND column_name=?",
        (table, geom_col),
    ).fetchone()
    return row[0] if row else "GEOMETRY"


def _register_layer(
    con: sqlite3.Connection,
    table_name: str,
    geom_col: str,
    srs_id: int,
    geom_type: str,
) -> None:
    """Register a new layer in gpkg_contents and gpkg_geometry_columns."""
    # Remove existing registration if present (for idempotency)
    con.execute("DELETE FROM gpkg_contents WHERE table_name=?", (table_name,))
    con.execute("DELETE FROM gpkg_geometry_columns WHERE table_name=?", (table_name,))

    # Register in gpkg_contents
    con.execute(
        "INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES (?, 'features', ?)",
        (table_name, srs_id),
    )

    # Register in gpkg_geometry_columns
    # OGC geometry type names: POINT, LINESTRING, POLYGON, MULTIPOINT, MULTILINESTRING, MULTIPOLYGON, GEOMETRYCOLLECTION
    con.execute(
        "INSERT INTO gpkg_geometry_columns "
        "(table_name, column_name, geometry_type_name, srs_id, z, m) "
        "VALUES (?, ?, ?, ?, 0, 0)",
        (table_name, geom_col, geom_type, srs_id),
    )


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def buffer(
    con: sqlite3.Connection,
    table: str,
    distance: float,
    output_table: str = "buffered",
    geom_col: Optional[str] = None,
    keep_attrs: bool = True,
) -> str:
    """Buffer features by a distance and store as a new layer.

    Creates polygon buffers around all features (points, lines, or polygons)
    at the specified distance. The distance is in the layer's CRS units
    (e.g., meters for projected CRS, degrees for geographic CRS).

    Args:
        con: SQLite connection with SpatiaLite loaded.
        table: Source table to buffer.
        distance: Buffer distance in CRS units. Use negative values for
            inward buffers on polygons.
        output_table: Name for the output layer (default: "buffered").
        geom_col: Geometry column name. Auto-detected if None.
        keep_attrs: Copy source attributes to output (default: True).

    Returns:
        Name of the output table.

    Raises:
        ValueError: If the table has no features.

    Example:
        >>> con = connect("data.gpkg")
        >>> buffer(con, "buildings", 100, "buildings_100m")
        >>> # Buildings buffered by 100 meters (in projected CRS)
    """
    if geom_col is None:
        geom_col = _get_geom_col(con, table)

    srs_id = _get_srs_id(con, table, geom_col)

    # Check feature count
    count = con.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    if count == 0:
        raise ValueError(f"Table '{table}' has no features to buffer")

    # Drop output table if it exists
    con.execute(f"DROP TABLE IF EXISTS [{output_table}]")

    # Create buffered layer
    if keep_attrs:
        # Copy all columns + buffered geometry
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT [{geom_col}] AS [{geom_col}],
                   t.*
            FROM [{table}] t
            WHERE [{geom_col}] IS NOT NULL
        """)
        # Replace the original geom column with buffered version
        # First, get all column names except the geom
        cols = con.execute(f"PRAGMA table_info([{table}])").fetchall()
        attr_cols = [c[1] for c in cols if c[1] != "fid" and c[1] != geom_col]

        # Rebuild with buffer applied
        con.execute(f"DROP TABLE [{output_table}]")
        select_expr = f"ST_Buffer(t.[{geom_col}], {distance}) AS [{geom_col}]"
        if attr_cols:
            select_expr += ", " + ", ".join(f"t.[{c}]" for c in attr_cols)
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{table}] t
            WHERE t.[{geom_col}] IS NOT NULL
        """)
    else:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT ST_Buffer([{geom_col}], {distance}) AS [{geom_col}]
            FROM [{table}]
            WHERE [{geom_col}] IS NOT NULL
        """)

    # Register layer
    _register_layer(con, output_table, geom_col, srs_id, "POLYGON")

    con.commit()
    return output_table


def clip(
    con: sqlite3.Connection,
    source_table: str,
    clip_table: str,
    output_table: str = "clipped",
    source_geom: Optional[str] = None,
    clip_geom: Optional[str] = None,
    keep_attrs: str = "source",
) -> str:
    """Clip source features by a clip layer boundary.

    Intersects each source feature with the clip layer polygons and keeps
    only the portions that fall inside the clip boundary. Attributes from
    the clipped features are preserved.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        source_table: Table containing features to clip.
        clip_table: Table containing clipping polygons.
        output_table: Name for the output layer (default: "clipped").
        source_geom: Geometry column for source. Auto-detected if None.
        clip_geom: Geometry column for clip layer. Auto-detected if None.
        keep_attrs: Which attributes to keep: "source" (default),
            "clip", "both", or "none".

    Returns:
        Name of the output table.

    Raises:
        ValueError: If either table has no features.

    Example:
        >>> con = connect("data.gpkg")
        >>> clip(con, "buildings", "districts", "buildings_in_district")
    """
    if source_geom is None:
        source_geom = _get_geom_col(con, source_table)
    if clip_geom is None:
        clip_geom = _get_geom_col(con, clip_table)

    srs_id = _get_srs_id(con, source_table, source_geom)

    # Check feature counts
    src_count = con.execute(f"SELECT COUNT(*) FROM [{source_table}]").fetchone()[0]
    clip_count = con.execute(f"SELECT COUNT(*) FROM [{clip_table}]").fetchone()[0]
    if src_count == 0:
        raise ValueError(f"Source table '{source_table}' has no features")
    if clip_count == 0:
        raise ValueError(f"Clip table '{clip_table}' has no features")

    # Build select expression based on keep_attrs
    geom_expr = f"ST_Intersection(s.[{source_geom}], c.[{clip_geom}]) AS [{source_geom}]"

    if keep_attrs == "source" or keep_attrs == "a":
        # Get source attribute columns (exclude fid and geom)
        cols = con.execute(f"PRAGMA table_info([{source_table}])").fetchall()
        attr_cols = [c[1] for c in cols if c[1] != "fid" and c[1] != source_geom]
        attr_expr = ", ".join(f"s.[{c}]" for c in attr_cols)
        if attr_expr:
            select_expr = f"{geom_expr}, {attr_expr}"
        else:
            select_expr = geom_expr
    elif keep_attrs == "both":
        src_cols = con.execute(f"PRAGMA table_info([{source_table}])").fetchall()
        clip_cols = con.execute(f"PRAGMA table_info([{clip_table}])").fetchall()
        src_attrs = [c[1] for c in src_cols if c[1] != "fid" and c[1] != source_geom]
        clip_attrs = [c[1] for c in clip_cols if c[1] != "fid" and c[1] != clip_geom]
        parts = [geom_expr]
        parts.extend(f"s.[{c}] AS s_{c}" for c in src_attrs)
        parts.extend(f"c.[{c}] AS c_{c}" for c in clip_attrs)
        select_expr = ", ".join(parts)
    elif keep_attrs == "clip" or keep_attrs == "b":
        clip_cols = con.execute(f"PRAGMA table_info([{clip_table}])").fetchall()
        clip_attrs = [c[1] for c in clip_cols if c[1] != "fid" and c[1] != clip_geom]
        attr_expr = ", ".join(f"c.[{c}]" for c in clip_attrs)
        if attr_expr:
            select_expr = f"{geom_expr}, {attr_expr}"
        else:
            select_expr = geom_expr
    else:  # "none"
        select_expr = geom_expr

    # Build the rtree join for performance
    rtree_s = _get_rtree_table(source_table, source_geom)
    rtree_c = _get_rtree_table(clip_table, clip_geom)

    has_rtree_s = _rtree_exists(con, source_table, source_geom)
    has_rtree_c = _rtree_exists(con, clip_table, clip_geom)

    con.execute(f"DROP TABLE IF EXISTS [{output_table}]")

    if has_rtree_s and has_rtree_c:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{source_table}] s
            JOIN [{rtree_s}] rs ON s.fid = rs.id
            JOIN [{rtree_c}] rc ON rs.maxx >= rc.minx AND rs.minx <= rc.maxx
                               AND rs.maxy >= rc.miny AND rs.miny <= rc.maxy
            JOIN [{clip_table}] c ON c.fid = rc.id
            WHERE ST_Intersects(s.[{source_geom}], c.[{clip_geom}]) = 1
              AND s.[{source_geom}] IS NOT NULL
              AND c.[{clip_geom}] IS NOT NULL
        """)
    elif has_rtree_s:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{source_table}] s
            JOIN [{rtree_s}] rs ON s.fid = rs.id
            JOIN [{clip_table}] c
            WHERE rs.maxx >= ST_MinX(c.[{clip_geom}]) AND rs.minx <= ST_MaxX(c.[{clip_geom}])
              AND rs.maxy >= ST_MinY(c.[{clip_geom}]) AND rs.miny <= ST_MaxY(c.[{clip_geom}])
              AND ST_Intersects(s.[{source_geom}], c.[{clip_geom}])
              AND s.[{source_geom}] IS NOT NULL
              AND c.[{clip_geom}] IS NOT NULL
        """)
    else:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{source_table}] s
            JOIN [{clip_table}] c
            WHERE ST_Intersects(s.[{source_geom}], c.[{clip_geom}]) = 1
              AND s.[{source_geom}] IS NOT NULL
              AND c.[{clip_geom}] IS NOT NULL
        """)

    # Register layer
    _register_layer(con, output_table, source_geom, srs_id, "GEOMETRY")

    con.commit()
    return output_table


def intersect(
    con: sqlite3.Connection,
    table_a: str,
    table_b: str,
    output_table: str = "intersection",
    geom_a: Optional[str] = None,
    geom_b: Optional[str] = None,
    keep_attrs: str = "both",
) -> str:
    """Find the spatial intersection of two layers.

    Computes the geometric intersection of two layers and produces
    a new layer with the intersection geometry and selected attributes
    from both inputs.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        table_a: First input table.
        table_b: Second input table.
        output_table: Name for the output layer (default: "intersection").
        geom_a: Geometry column for table_a. Auto-detected if None.
        geom_b: Geometry column for table_b. Auto-detected if None.
        keep_attrs: Which attributes to keep: "both" (default),
            "a", "b", or "none".

    Returns:
        Name of the output table.

    Raises:
        ValueError: If either table has no features.

    Example:
        >>> con = connect("data.gpkg")
        >>> intersect(con, "buildings", "flood_zones", "buildings_in_flood")
    """
    if geom_a is None:
        geom_a = _get_geom_col(con, table_a)
    if geom_b is None:
        geom_b = _get_geom_col(con, table_b)

    srs_id = _get_srs_id(con, table_a, geom_a)

    # Check feature counts
    count_a = con.execute(f"SELECT COUNT(*) FROM [{table_a}]").fetchone()[0]
    count_b = con.execute(f"SELECT COUNT(*) FROM [{table_b}]").fetchone()[0]
    if count_a == 0:
        raise ValueError(f"Table '{table_a}' has no features")
    if count_b == 0:
        raise ValueError(f"Table '{table_b}' has no features")

    # Build select expression
    geom_expr = f"ST_Intersection(a.[{geom_a}], b.[{geom_b}]) AS [{geom_a}]"

    if keep_attrs == "a":
        cols = con.execute(f"PRAGMA table_info([{table_a}])").fetchall()
        attr_cols = [c[1] for c in cols if c[1] != "fid" and c[1] != geom_a]
        attr_expr = ", ".join(f"a.[{c}]" for c in attr_cols)
        select_expr = f"{geom_expr}, {attr_expr}" if attr_expr else geom_expr
    elif keep_attrs == "b":
        cols = con.execute(f"PRAGMA table_info([{table_b}])").fetchall()
        attr_cols = [c[1] for c in cols if c[1] != "fid" and c[1] != geom_b]
        attr_expr = ", ".join(f"b.[{c}]" for c in attr_cols)
        select_expr = f"{geom_expr}, {attr_expr}" if attr_expr else geom_expr
    elif keep_attrs == "both":
        cols_a = con.execute(f"PRAGMA table_info([{table_a}])").fetchall()
        cols_b = con.execute(f"PRAGMA table_info([{table_b}])").fetchall()
        attrs_a = [c[1] for c in cols_a if c[1] != "fid" and c[1] != geom_a]
        attrs_b = [c[1] for c in cols_b if c[1] != "fid" and c[1] != geom_b]
        parts = [geom_expr]
        parts.extend(f"a.[{c}] AS a_{c}" for c in attrs_a)
        parts.extend(f"b.[{c}] AS b_{c}" for c in attrs_b)
        select_expr = ", ".join(parts)
    else:  # "none"
        select_expr = geom_expr

    rtree_a = _get_rtree_table(table_a, geom_a)
    rtree_b = _get_rtree_table(table_b, geom_b)

    has_rtree_a = _rtree_exists(con, table_a, geom_a)
    has_rtree_b = _rtree_exists(con, table_b, geom_b)

    con.execute(f"DROP TABLE IF EXISTS [{output_table}]")

    if has_rtree_a and has_rtree_b:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{table_a}] a
            JOIN [{rtree_a}] ra ON a.fid = ra.id
            JOIN [{rtree_b}] rb ON ra.maxx >= rb.minx AND ra.minx <= rb.maxx
                               AND ra.maxy >= rb.miny AND ra.miny <= rb.maxy
            JOIN [{table_b}] b ON b.fid = rb.id
            WHERE ST_Intersects(a.[{geom_a}], b.[{geom_b}]) = 1
              AND a.[{geom_a}] IS NOT NULL
              AND b.[{geom_b}] IS NOT NULL
        """)
    else:
        con.execute(f"""
            CREATE TABLE [{output_table}] AS
            SELECT {select_expr}
            FROM [{table_a}] a
            JOIN [{table_b}] b
            WHERE ST_Intersects(a.[{geom_a}], b.[{geom_b}]) = 1
              AND a.[{geom_a}] IS NOT NULL
              AND b.[{geom_b}] IS NOT NULL
        """)

    # Register layer
    _register_layer(con, output_table, geom_a, srs_id, "GEOMETRY")

    con.commit()
    return output_table
