"""
Spatial queries for GeoPackage layers.

Provides rtree-accelerated spatial joins, point-in-polygon classification,
and bounding box filtering. All functions work with GeoPackage's native
rtree tables (not SpatiaLite's SpatialIndex virtual table).
"""

from typing import Optional


def _get_geom_col(con, table):
    """Auto-detect geometry column name from gpkg_geometry_columns."""
    row = con.execute(
        "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
        (table,),
    ).fetchone()
    return row[0] if row else "geom"


def _get_rtree_table(table, geom_col):
    """GeoPackage native rtree table name."""
    return f"rtree_{table}_{geom_col}"


def _rtree_exists(con, table, geom_col):
    """Check if rtree spatial index exists for a table."""
    rtree = _get_rtree_table(table, geom_col)
    try:
        con.execute(f"SELECT COUNT(*) FROM [{rtree}] LIMIT 1")
        return True
    except Exception:
        return False


def _create_rtree(con, table, geom_col):
    """Create rtree spatial index (idempotent)."""
    con.execute(f"SELECT CreateSpatialIndex('{table}', '{geom_col}')")


def count_in_zones(
    con,
    feature_table,
    zone_table,
    feature_geom=None,
    zone_geom=None,
    zone_id="fid",
    ensure_index=True,
):
    """Count features inside each zone using rtree spatial index.

    For each zone polygon, counts how many features from feature_table
    fall inside it. Uses rtree bbox pre-filter + ST_Contains for speed.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        feature_table: Table containing features to count (e.g., buildings).
        zone_table: Table containing zone polygons (e.g., admin3 boundaries).
        feature_geom: Geometry column name for features. Auto-detected if None.
        zone_geom: Geometry column name for zones. Auto-detected if None.
        zone_id: Column to identify zones (default: fid).
        ensure_index: Create rtree index if missing (default: True).

    Returns:
        List of (zone_id_value, feature_count) tuples.

    Example:
        >>> con = connect("mashriq.gpkg")
        >>> counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")
        >>> for zone_id, count in counts[:5]:
        ...     print(f"Zone {zone_id}: {count} buildings")
    """
    if feature_geom is None:
        feature_geom = _get_geom_col(con, feature_table)
    if zone_geom is None:
        zone_geom = _get_geom_col(con, zone_table)

    rtree_table = _get_rtree_table(feature_table, feature_geom)

    # Ensure rtree index exists
    if ensure_index and not _rtree_exists(con, feature_table, feature_geom):
        _create_rtree(con, feature_table, feature_geom)

    has_rtree = _rtree_exists(con, feature_table, feature_geom)

    # Use SQL ST_MinX/ST_MaxX instead of Python Envelope().bounds
    # because Envelope() returns (0,0,0,0) on GeoPackage blobs through SpatiaLite.
    zones = con.execute(
        f"SELECT [{zone_id}], [{zone_geom}], "
        f"ST_MinX([{zone_geom}]), ST_MinY([{zone_geom}]), "
        f"ST_MaxX([{zone_geom}]), ST_MaxY([{zone_geom}]) "
        f"FROM [{zone_table}]"
    ).fetchall()
    results = []

    for zid, zone_geom_blob, minx, miny, maxx, maxy in zones:
        if zone_geom_blob is None:
            results.append((zid, 0))
            continue

        # Skip degenerate envelopes (empty or null extent)
        if minx is None or miny is None or maxx is None or maxy is None:
            results.append((zid, 0))
            continue
        if minx == maxx and miny == maxy:
            # Degenerate zone (point or line), skip rtree pre-filter
            count = con.execute(
                f"SELECT COUNT(*) FROM [{feature_table}] "
                f"WHERE ST_Contains(?, [{feature_geom}])",
                (zone_geom_blob,),
            ).fetchone()[0]
            results.append((zid, count))
            continue

        if has_rtree:
            count = con.execute(
                f"""
                SELECT COUNT(*) FROM [{feature_table}] ft
                JOIN [{rtree_table}] r ON ft.fid = r.id
                WHERE r.maxx >= ? AND r.minx <= ?
                  AND r.maxy >= ? AND r.miny <= ?
                  AND ST_Contains(?, ft.[{feature_geom}])
                """,
                (minx, maxx, miny, maxy, zone_geom_blob),
            ).fetchone()[0]
        else:
            # Fallback: full table scan with ST_Contains
            count = con.execute(
                f"""
                SELECT COUNT(*) FROM [{feature_table}]
                WHERE ST_Contains(?, [{feature_geom}])
                """,
                (zone_geom_blob,),
            ).fetchone()[0]

        results.append((zid, count))

    return results


def points_in_polygons(
    con,
    points_table,
    polygon_table,
    points_geom=None,
    polygon_geom=None,
    polygon_id="fid",
    ensure_index=True,
):
    """Classify points into containing polygons.

    For each point, finds which polygon contains it. Uses rtree
    spatial index on the points table for speed.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        points_table: Table containing point features.
        polygon_table: Table containing polygon features.
        points_geom: Geometry column name for points. Auto-detected if None.
        polygon_geom: Geometry column name for polygons. Auto-detected if None.
        polygon_id: Column to identify polygons (default: fid).
        ensure_index: Create rtree index on points if missing (default: True).

    Returns:
        List of (point_fid, polygon_id_value) tuples. Points not inside
        any polygon have polygon_id_value of None.

    Example:
        >>> con = connect("data.gpkg")
        >>> result = points_in_polygons(con, "POIs", "districts")
        >>> for poi_id, district_id in result[:5]:
        ...     print(f"POI {poi_id} is in district {district_id}")
    """
    if points_geom is None:
        points_geom = _get_geom_col(con, points_table)
    if polygon_geom is None:
        polygon_geom = _get_geom_col(con, polygon_table)

    # Ensure rtree index on points
    if ensure_index and not _rtree_exists(con, points_table, points_geom):
        _create_rtree(con, points_table, points_geom)

    # Load all polygons
    polygons = con.execute(
        f"SELECT [{polygon_id}], [{polygon_geom}] FROM [{polygon_table}]"
    ).fetchall()

    # Load all points
    points = con.execute(
        f"SELECT fid, [{points_geom}] FROM [{points_table}]"
    ).fetchall()

    results = []
    for pt_fid, pt_geom in points:
        if pt_geom is None:
            results.append((pt_fid, None))
            continue

        matched = None
        for poly_id, poly_geom in polygons:
            if poly_geom is None:
                continue
            try:
                if con.execute(
                    "SELECT ST_Contains(?, ?)", (poly_geom, pt_geom)
                ).fetchone()[0]:
                    matched = poly_id
                    break
            except Exception:
                continue

        results.append((pt_fid, matched))

    return results


def bbox_filter(
    con,
    table,
    bbox,
    geom_col=None,
    ensure_index=True,
):
    """Return feature IDs within a bounding box.

    Uses rtree spatial index for fast bbox filtering.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        table: Table to query.
        bbox: Bounding box as (minx, miny, maxx, maxy).
        geom_col: Geometry column name. Auto-detected if None.
        ensure_index: Create rtree index if missing (default: True).

    Returns:
        List of feature IDs (fid values) within the bbox.

    Example:
        >>> con = connect("data.gpkg")
        >>> fids = bbox_filter(con, "buildings", (35.4, 33.8, 35.6, 33.9))
        >>> print(f"{len(fids)} buildings in bbox")
    """
    if geom_col is None:
        geom_col = _get_geom_col(con, table)

    if ensure_index and not _rtree_exists(con, table, geom_col):
        _create_rtree(con, table, geom_col)

    rtree_table = _get_rtree_table(table, geom_col)
    minx, miny, maxx, maxy = bbox

    has_rtree = _rtree_exists(con, table, geom_col)

    if has_rtree:
        rows = con.execute(
            f"""
            SELECT ft.fid FROM [{table}] ft
            JOIN [{rtree_table}] r ON ft.fid = r.id
            WHERE r.maxx >= ? AND r.minx <= ?
              AND r.maxy >= ? AND r.miny <= ?
            """,
            (minx, maxx, miny, maxy),
        ).fetchall()
    else:
        rows = con.execute(
            f"SELECT fid FROM [{table}] "
            f"WHERE ST_MinX([{geom_col}]) >= ? AND ST_MaxX([{geom_col}]) <= ? "
            f"AND ST_MinY([{geom_col}]) >= ? AND ST_MaxY([{geom_col}]) <= ?",
            (minx, maxx, miny, maxy),
        ).fetchall()

    return [r[0] for r in rows]
