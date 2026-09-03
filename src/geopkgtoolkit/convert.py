"""
Format conversion for GeoPackage layers.

Export GeoPackage layers to GeoJSON and Shapefile.
Import GeoJSON and Shapefile data into GeoPackage layers.

GeoJSON is pure Python (no dependencies). Shapefile requires pyshp.

Example:
    >>> from geopkgtoolkit._spatialite import connect
    >>> from geopkgtoolkit.convert import export_geojson, import_geojson
    >>> con = connect("data.gpkg")
    >>> export_geojson(con, "buildings", "buildings.geojson")
    >>> import_geojson("new_data.gpkg", "input.geojson", "buildings")
"""

import json
import os
import re
import sqlite3
import struct
import tempfile
from pathlib import Path
from typing import Optional

from geopkgtoolkit._spatialite import connect, list_layers
from geopkgtoolkit.operations import _get_geom_col, _get_srs_id, _register_layer


# ---------------------------------------------------------------------------
# WKT to GeoJSON conversion
# ---------------------------------------------------------------------------

def _wkt_to_geojson_geom(wkt: str) -> dict:
    """Convert a WKT geometry string to a GeoJSON geometry dict.

    Handles Point, LineString, Polygon, MultiPoint, MultiLineString,
    MultiPolygon, and GeometryCollection (2D).
    """
    if not wkt:
        return None

    wkt = wkt.strip()

    # Strip Z/M suffixes from type name
    wkt = re.sub(
        r'(MULTI(?:POINT|LINESTRING|POLYGON)|GEOMETRYCOLLECTION|POINT|LINESTRING|POLYGON)[ZM]+\b',
        lambda m: m.group(1),
        wkt,
        count=1,
        flags=re.IGNORECASE,
    )

    # Extract the type and body
    match = re.match(
        r'(MULTI(?:POINT|LINESTRING|POLYGON)|GEOMETRYCOLLECTION|POINT|LINESTRING|POLYGON)\s*(.*)',
        wkt,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    geom_type = match.group(1).upper()
    body = match.group(2).strip()

    # Helper: extract coordinate pairs from a flat string like "0 0, 1 0, 1 1"
    def _coords_from_str(s: str) -> list:
        coords = []
        for pair in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s+[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', s):
            parts = pair.split()
            coords.append([float(parts[0]), float(parts[1])])
        return coords

    # Helper: split a parenthesized body into top-level groups
    # e.g. "((0 0, 1 0, 1 1, 0 1, 0 0), (2 2, 3 2, 3 3, 2 2))" -> ["(0 0, ...)", "(2 2, ...)"]
    def _split_parens(s: str) -> list:
        """Split a string into top-level parenthesized groups."""
        groups = []
        depth = 0
        start = None
        for i, ch in enumerate(s):
            if ch == '(':
                if depth == 0:
                    start = i + 1
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and start is not None:
                    groups.append(s[start:i])
                    start = None
        return groups

    # Strip the outer wrapping parens
    def _unwrap(s: str) -> str:
        s = s.strip()
        if s.startswith('(') and s.endswith(')') and s.count('(') == s.count(')'):
            return s[1:-1]
        return s

    if geom_type == 'POINT':
        coords = _coords_from_str(body)
        return {"type": "Point", "coordinates": coords[0] if coords else None}

    elif geom_type == 'LINESTRING':
        coords = _coords_from_str(body)
        return {"type": "LineString", "coordinates": coords}

    elif geom_type == 'POLYGON':
        rings = []
        inner = _unwrap(body)
        for group in _split_parens(inner):
            rings.append(_coords_from_str(group))
        return {"type": "Polygon", "coordinates": rings}

    elif geom_type == 'MULTIPOINT':
        # MULTIPLE POINTS: ((x y), (x y)) or (x y, x y)
        inner = _unwrap(body)
        groups = _split_parens(inner)
        if groups:
            # Each group is one coordinate pair
            coords = []
            for g in groups:
                pts = _coords_from_str(g)
                if pts:
                    coords.append(pts[0])
            return {"type": "MultiPoint", "coordinates": coords}
        else:
            # Flat form: x y, x y, ...
            return {"type": "MultiPoint", "coordinates": _coords_from_str(body)}

    elif geom_type == 'MULTILINESTRING':
        lines = []
        inner = _unwrap(body)
        for group in _split_parens(inner):
            lines.append(_coords_from_str(group))
        return {"type": "MultiLineString", "coordinates": lines}

    elif geom_type == 'MULTIPOLYGON':
        polys = []
        inner = _unwrap(body)
        for group in _split_parens(inner):
            rings = []
            for ring_group in _split_parens(group):
                rings.append(_coords_from_str(ring_group))
            if rings:
                polys.append(rings)
        return {"type": "MultiPolygon", "coordinates": polys}

    elif geom_type == 'GEOMETRYCOLLECTION':
        # For simplicity, parse sub-geometries by finding type keywords
        geoms = []
        for sub_match in re.finditer(
            r'(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON)\s*\(.*?\)(?:\s*\))*',
            body,
            re.IGNORECASE | re.DOTALL,
        ):
            sub_geom = _wkt_to_geojson_geom(sub_match.group(0))
            if sub_geom:
                geoms.append(sub_geom)
        return {"type": "GeometryCollection", "geometries": geoms}

    return None


# ---------------------------------------------------------------------------
# Export: GeoPackage -> GeoJSON
# ---------------------------------------------------------------------------

def export_geojson(
    con: sqlite3.Connection,
    layer: str,
    output_path: str | Path,
    geom_col: Optional[str] = None,
) -> Path:
    """Export a GeoPackage layer to a GeoJSON FeatureCollection file.

    Uses SpatiaLite's ST_AsText() for geometry conversion and reads
    all attribute columns. Produces a standards-compliant GeoJSON file
    with a default WGS84 CRS.

    Args:
        con: SQLite connection with SpatiaLite loaded.
        layer: Name of the layer to export.
        output_path: Path for the output .geojson file.
        geom_col: Geometry column name. Auto-detected if None.

    Returns:
        Path to the written GeoJSON file.

    Raises:
        FileNotFoundError: If the source GeoPackage does not exist.
        ValueError: If the layer does not exist or has no geometry column.

    Example:
        >>> con = connect("data.gpkg")
        >>> export_geojson(con, "buildings", "buildings.geojson")
        PosixPath('buildings.geojson')
    """
    if geom_col is None:
        geom_col = _get_geom_col(con, layer)

    # Get attribute columns (exclude fid and geom)
    cols_info = con.execute(f"PRAGMA table_info([{layer}])").fetchall()
    attr_cols = [c[1] for c in cols_info if c[1] != "fid" and c[1] != geom_col]

    # Use ST_AsText (WKT) for geometry, parse in Python
    select_parts = [f"ST_AsText([{geom_col}]) AS _wkt"]
    for col in attr_cols:
        select_parts.append(f"[{col}]")
    select = ", ".join(select_parts)

    rows = con.execute(
        f"SELECT {select} FROM [{layer}] WHERE [{geom_col}] IS NOT NULL"
    ).fetchall()

    features = []
    for row in rows:
        wkt_str = row[0]
        if not wkt_str:
            continue
        geometry = _wkt_to_geojson_geom(wkt_str)
        if geometry is None:
            continue
        properties = {}
        for i, col in enumerate(attr_cols):
            val = row[i + 1]
            if isinstance(val, bytes):
                val = val.hex()
            properties[col] = val
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties,
        })

    fc = {
        "type": "FeatureCollection",
        "features": features,
    }

    out = Path(output_path)
    out.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Export: GeoPackage -> Shapefile
# ---------------------------------------------------------------------------

# Map GeoPackage geometry types to pyshp shape types
_GPKG_TO_SHP_TYPE = {
    "POINT": 1,
    "LINESTRING": 3,
    "POLYGON": 5,
    "MULTIPOINT": 8,
    "MULTILINESTRING": 3,
    "MULTIPOLYGON": 5,
}


def _sqlite_type_to_shp_field(sqlite_type: str) -> str:
    """Map SQLite column type to pyshp field type character."""
    if sqlite_type is None:
        return "C"
    t = sqlite_type.upper()
    if "INT" in t:
        return "N"
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t or "NUMERIC" in t:
        return "N"
    if "BLOB" in t:
        return "B"
    return "C"


def export_shapefile(
    con: sqlite3.Connection,
    layer: str,
    output_path: str | Path,
    geom_col: Optional[str] = None,
) -> Path:
    """Export a GeoPackage layer to an Esri Shapefile.

    Creates .shp, .shx, .dbf, and .prj files.

    Requires the ``pyshp`` package (pip install geopackage-toolkit[convert]).

    Args:
        con: SQLite connection with SpatiaLite loaded.
        layer: Name of the layer to export.
        output_path: Path for the output .shp file.
        geom_col: Geometry column name. Auto-detected if None.

    Returns:
        Path to the written .shp file.
    """
    try:
        import shapefile as shp
    except ImportError:
        raise ImportError(
            "pyshp is required for Shapefile export. "
            "Install it with: pip install geopackage-toolkit[convert]"
        )

    if geom_col is None:
        geom_col = _get_geom_col(con, layer)

    # Detect geometry type
    gpkg_type = con.execute(
        "SELECT geometry_type_name FROM gpkg_geometry_columns "
        "WHERE table_name=? AND column_name=?",
        (layer, geom_col),
    ).fetchone()
    gpkg_type_name = gpkg_type[0] if gpkg_type else "GEOMETRY"
    shp_type = _GPKG_TO_SHP_TYPE.get(gpkg_type_name, 5)

    # Get attribute columns
    cols_info = con.execute(f"PRAGMA table_info([{layer}])").fetchall()
    attr_cols = [c[1] for c in cols_info if c[1] != "fid" and c[1] != geom_col]
    col_types = {c[1]: c[2] for c in cols_info if c[1] != "fid" and c[1] != geom_col}

    # Get SRID for .prj file
    srs_id = _get_srs_id(con, layer, geom_col)
    prj_wkt = _srid_to_prj(srs_id)

    # Read WKT
    select_parts = [f"ST_AsText([{geom_col}]) AS _wkt"]
    for col in attr_cols:
        select_parts.append(f"[{col}]")
    select = ", ".join(select_parts)
    rows = con.execute(
        f"SELECT {select} FROM [{layer}] WHERE [{geom_col}] IS NOT NULL"
    ).fetchall()

    # Create shapefile writer
    out_path = Path(output_path)
    w = shp.Writer(str(out_path.with_suffix("")), shapeType=shp_type)
    w.autoBalance = 1

    # Add fields
    for col in attr_cols:
        sf_type = _sqlite_type_to_shp_field(col_types.get(col))
        size = 18 if sf_type == "N" else 254
        w.field(col, sf_type, size=size, decimal=4)

    # Write features
    skipped = 0
    for row in rows:
        wkt_str = row[0]
        if wkt_str is None:
            skipped += 1
            continue

        geom = _wkt_to_geojson_geom(wkt_str)
        if geom is None:
            skipped += 1
            continue

        geom_type = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if geom_type == "Point":
            w.point(coords[0], coords[1])
        elif geom_type == "MultiPoint":
            w.multipoint([[c[0], c[1]] for c in coords])
        elif geom_type == "LineString":
            w.line([[[c[0], c[1]] for c in coords]])
        elif geom_type == "MultiLineString":
            w.line([[[c[0], c[1]] for c in line] for line in coords])
        elif geom_type == "Polygon":
            w.poly([[[c[0], c[1]] for c in ring] for ring in coords])
        elif geom_type == "MultiPolygon":
            w.poly([[[c[0], c[1]] for c in ring] for ring in poly] for poly in coords)
        else:
            skipped += 1
            continue

        attrs = {}
        for i, col in enumerate(attr_cols):
            attrs[col] = row[i + 1]
        w.record(**attrs)

    w.close()

    # Write .prj
    if prj_wkt:
        prj_path = out_path.with_suffix(".prj")
        prj_path.write_text(prj_wkt, encoding="utf-8")

    return out_path


def _srid_to_prj(srid: int) -> str:
    """Convert common SRIDs to .prj WKT strings."""
    prj_map = {
        4326: 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
        3857: 'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Mercator"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],UNIT["Meter",1.0]]',
        32637: 'PROJCS["WGS_1984_UTM_Zone_37N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",39.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]',
    }
    return prj_map.get(srid, "")


# ---------------------------------------------------------------------------
# Import: GeoJSON -> GeoPackage
# ---------------------------------------------------------------------------

def _ensure_gpkg_metadata(con: sqlite3.Connection) -> None:
    """Ensure GeoPackage metadata tables exist."""
    con.execute("""CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
        srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
        organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
        description TEXT
    )""")
    con.execute("""INSERT OR IGNORE INTO gpkg_spatial_ref_sys
        (srs_name, srs_id, organization, organization_coordsys_id, description)
        VALUES ('WGS 84', 4326, 'EPSG', 4326, 'WGS 84 geodetic')""")
    con.execute("""CREATE TABLE IF NOT EXISTS gpkg_contents (
        table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
        identifier TEXT, description TEXT DEFAULT '',
        last_change DATETIME DEFAULT (datetime('now')),
        min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
        srs_id INTEGER
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
        table_name TEXT NOT NULL, column_name TEXT NOT NULL,
        geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
        z TINYINT NOT NULL DEFAULT 0, m TINYINT NOT NULL DEFAULT 0,
        PRIMARY KEY (table_name, column_name)
    )""")
    con.commit()


def import_geojson(
    gpkg_path: str | Path,
    geojson_path: str | Path,
    layer_name: str,
    geom_col: str = "geom",
    srid: int = 4326,
) -> str:
    """Import a GeoJSON file into a new GeoPackage layer.

    Creates the GeoPackage if it does not exist. Geometry is inserted
    via SpatiaLite's GeomFromGeoJSON(). Attribute fields are
    auto-detected from the first feature with properties.

    Args:
        gpkg_path: Path to the output GeoPackage (created if missing).
        geojson_path: Path to the input .geojson file.
        layer_name: Name for the output layer.
        geom_col: Name for the geometry column (default: "geom").
        srid: Spatial reference ID (default: 4326).

    Returns:
        Name of the created layer.

    Raises:
        FileNotFoundError: If the GeoJSON file does not exist.
        ValueError: If the GeoJSON has no features or no geometry.
    """
    gpkg_path = Path(gpkg_path)
    geojson_path = Path(geojson_path)

    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    # Open (or create) the GeoPackage (without GPKG mode for reliable ST_AsText)
    if gpkg_path.exists():
        con = connect(gpkg_path, enable_gpkg_mode=False)
    else:
        # Create empty file first (connect requires file to exist)
        sqlite3.connect(str(gpkg_path)).close()
        con = connect(gpkg_path, enable_gpkg_mode=False)
    _ensure_gpkg_metadata(con)

    # Fresh files may lack SpatiaLite metadata tables; without spatial_ref_sys
    # geometry functions (ST_Intersects, ST_Intersection) behave inconsistently
    has_srs = con.execute(
        "SELECT name FROM sqlite_master WHERE name = 'spatial_ref_sys'"
    ).fetchone()
    if has_srs is None:
        con.execute("SELECT InitSpatialMetaData(1)")
        con.commit()

    # Load GeoJSON
    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = fc.get("features", [])
    if not features:
        con.close()
        raise ValueError(f"GeoJSON has no features: {geojson_path}")

    # Detect geometry type and attribute fields
    geom_type_name = "GEOMETRY"
    all_props: dict[str, str] = {}

    for feat in features:
        geom = feat.get("geometry")
        if geom and geom.get("type"):
            t = geom["type"]
            if t not in ("GeometryCollection",):
                geom_type_name = t.upper()
        props = feat.get("properties", {})
        for k, v in props.items():
            if k not in all_props:
                all_props[k] = _python_type_to_sqlite(v)

    # Create the table (include geometry column)
    col_defs = []
    for col, sql_type in all_props.items():
        col_defs.append(f"[{col}] {sql_type}")
    col_defs.append(f"[{geom_col}] GEOMETRY")
    create_sql = f"CREATE TABLE [{layer_name}] (fid INTEGER PRIMARY KEY AUTOINCREMENT"
    if col_defs:
        create_sql += ", " + ", ".join(col_defs)
    create_sql += ")"

    con.execute(f"DROP TABLE IF EXISTS [{layer_name}]")
    con.execute(create_sql)

    # Insert features
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry")

        if not geom:
            continue

        cols = []
        vals = []
        placeholders = []
        for col in all_props:
            cols.append(f"[{col}]")
            vals.append(props.get(col))
            placeholders.append("?")

        # Use GeomFromGeoJSON() + SetSRID() so the blob SRID matches the
        # registered SRID (GeomFromGeoJSON alone can leave SRID unset)
        cols.append(f"[{geom_col}]")
        placeholders.append(f"SetSRID(GeomFromGeoJSON(?), {int(srid)})")
        vals.append(json.dumps(geom))

        sql = f"INSERT INTO [{layer_name}] ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        try:
            con.execute(sql, vals)
        except Exception:
            continue

    # Register layer
    _register_layer(con, layer_name, geom_col, srid, geom_type_name)
    con.commit()
    con.close()
    return layer_name


def _python_type_to_sqlite(val) -> str:
    """Map a Python value to a SQLite column type string."""
    if val is None:
        return "TEXT"
    if isinstance(val, bool):
        return "INTEGER"
    if isinstance(val, int):
        return "INTEGER"
    if isinstance(val, float):
        return "REAL"
    if isinstance(val, bytes):
        return "BLOB"
    return "TEXT"


# ---------------------------------------------------------------------------
# Import: Shapefile -> GeoPackage
# ---------------------------------------------------------------------------

def import_shapefile(
    gpkg_path: str | Path,
    shp_path: str | Path,
    layer_name: str,
    geom_col: str = "geom",
    srid: int = 4326,
) -> str:
    """Import a Shapefile into a new GeoPackage layer.

    Creates the GeoPackage if it does not exist.

    Requires the ``pyshp`` package (pip install geopackage-toolkit[convert]).

    Args:
        gpkg_path: Path to the output GeoPackage (created if missing).
        shp_path: Path to the input .shp file.
        layer_name: Name for the output layer.
        geom_col: Name for the geometry column (default: "geom").
        srid: Spatial reference ID (default: 4326).

    Returns:
        Name of the created layer.
    """
    try:
        import shapefile as shp
    except ImportError:
        raise ImportError(
            "pyshp is required for Shapefile import. "
            "Install it with: pip install geopackage-toolkit[convert]"
        )

    shp_path = Path(shp_path)
    if not shp_path.exists():
        raise FileNotFoundError(f"Shapefile not found: {shp_path}")

    sf = shp.Reader(str(shp_path.with_suffix("")))

    # Open (or create) GeoPackage
    gpkg_path = Path(gpkg_path)
    if gpkg_path.exists():
        con = connect(gpkg_path)
    else:
        sqlite3.connect(str(gpkg_path)).close()
        con = connect(gpkg_path)
    _ensure_gpkg_metadata(con)

    # Map pyshp field types to SQLite types
    _SHP_TO_SQL = {
        "C": "TEXT", "N": "REAL", "F": "REAL", "L": "INTEGER",
        "D": "TEXT", "T": "TEXT", "M": "TEXT", "B": "BLOB",
    }

    # Create the table
    fields = sf.fields[1:]  # Skip deletion flag field
    col_defs = []
    for name, field_type, size, decimal in fields:
        sql_type = _SHP_TO_SQL.get(field_type, "TEXT")
        col_defs.append(f"[{name}] {sql_type}")

    col_defs.append(f"[{geom_col}] GEOMETRY")
    create_sql = f"CREATE TABLE [{layer_name}] (fid INTEGER PRIMARY KEY AUTOINCREMENT"
    if col_defs:
        create_sql += ", " + ", ".join(col_defs)
    create_sql += ")"

    con.execute(f"DROP TABLE IF EXISTS [{layer_name}]")
    con.execute(create_sql)

    # Detect geometry type
    shp_type = sf.shapeTypeName
    _SHP_TO_GPKG = {
        "POINT": "POINT", "POINTZ": "POINT", "POINTM": "POINT",
        "POLYLINE": "LINESTRING", "POLYLINEZ": "LINESTRING", "POLYLINEM": "LINESTRING",
        "POLYGON": "POLYGON", "POLYGONZ": "POLYGON", "POLYGONM": "POLYGON",
        "MULTIPOINT": "MULTIPOINT", "MULTIPOINTZ": "MULTIPOINT", "MULTIPOINTM": "MULTIPOINT",
    }
    geom_type_name = _SHP_TO_GPKG.get(shp_type, "GEOMETRY")

    # Insert features
    field_names = [f[0] for f in fields]
    insert_cols = ", ".join(f"[{f}]" for f in field_names) + f", [{geom_col}]"

    count = 0
    for sr in sf.iterShapeRecords():
        shape = sr.shape
        record = sr.record

        geojson_geom = _shp_to_geojson(shape)
        if geojson_geom is None:
            continue

        vals = list(record)
        vals.append(json.dumps(geojson_geom))

        n_attr = len(field_names)
        attr_placeholders = ", ".join(["?"] * n_attr)
        geom_ph = f"SetSRID(GeomFromGeoJSON(?), {int(srid)})"
        if attr_placeholders:
            placeholders = f"{attr_placeholders}, {geom_ph}"
        else:
            placeholders = geom_ph

        sql = f"INSERT INTO [{layer_name}] ({insert_cols}) VALUES ({placeholders})"
        try:
            con.execute(sql, vals)
            count += 1
        except Exception:
            continue

    _register_layer(con, layer_name, geom_col, srid, geom_type_name)
    con.commit()
    con.close()
    return layer_name


def _shp_to_geojson(shape) -> Optional[dict]:
    """Convert a pyshp shape to a GeoJSON geometry dict."""
    shp_type = shape.shapeType
    parts = shape.parts
    points = shape.points

    if shp_type in (1, 11, 21):  # Point, PointZ, PointM
        if len(points) < 1:
            return None
        return {"type": "Point", "coordinates": list(points[0])}

    elif shp_type in (8, 18, 28):  # MultiPoint
        return {"type": "MultiPoint", "coordinates": [list(p) for p in points]}

    elif shp_type in (3, 13, 23):  # Polyline
        if parts and len(parts) > 1:
            lines = []
            for i in range(len(parts)):
                start = parts[i]
                end = parts[i + 1] if i + 1 < len(parts) else len(points)
                lines.append([list(p) for p in points[start:end]])
            if len(lines) == 1:
                return {"type": "LineString", "coordinates": lines[0]}
            return {"type": "MultiLineString", "coordinates": lines}
        else:
            return {"type": "LineString", "coordinates": [list(p) for p in points]}

    elif shp_type in (5, 15, 25):  # Polygon
        if parts and len(parts) > 1:
            rings = []
            for i in range(len(parts)):
                start = parts[i]
                end = parts[i + 1] if i + 1 < len(parts) else len(points)
                ring = [list(p) for p in points[start:end]]
                rings.append(ring)
            if len(rings) == 1:
                return {"type": "Polygon", "coordinates": rings}
            return {"type": "MultiPolygon", "coordinates": [rings]}
        else:
            return {"type": "Polygon", "coordinates": [[list(p) for p in points]]}

    return None
