"""Tests for geopkgtoolkit.convert module (GeoJSON and Shapefile conversion)."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


def _init_gpkg(con):
    """Initialize GeoPackage metadata tables on a SpatiaLite connection."""
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


def _register_feature_layer(con, table_name, geom_type="POLYGON"):
    """Register a feature layer in GPKG metadata."""
    con.execute(
        "INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, srs_id) VALUES (?, 'features', 4326)",
        (table_name,),
    )
    con.execute(
        "INSERT OR IGNORE INTO gpkg_geometry_columns "
        "(table_name, column_name, geometry_type_name, srs_id, z, m) "
        "VALUES (?, 'geom', ?, 4326, 0, 0)",
        (table_name, geom_type),
    )
    con.commit()


def _create_test_gpkg(geom_type, insert_sql):
    """Create a temporary GeoPackage with the given geometry and data."""
    from geopkgtoolkit._spatialite import connect

    fd, path = tempfile.mkstemp(suffix=".gpkg")
    os.close(fd)

    # Use enable_gpkg_mode=False to avoid SpatiaLite 5.1.0 bug where
    # ST_AsText returns NULL on subsequent connections
    con = connect(path, enable_gpkg_mode=False)
    _init_gpkg(con)
    con.executescript(insert_sql)
    _register_feature_layer(con, "test_layer", geom_type)
    con.commit()
    con.close()
    return path


@pytest.fixture
def tmp_gpkg():
    """Create a temporary GeoPackage with test polygon data."""
    path = _create_test_gpkg("POLYGON", """
        CREATE TABLE test_layer (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            height REAL,
            geom GEOMETRY
        );
        INSERT INTO test_layer (name, height, geom) VALUES
        ('Building A', 10.5, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326)),
        ('Building B', 20.0, ST_GeomFromText('POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))', 4326)),
        ('Building C', 15.3, ST_GeomFromText('POLYGON((4 4, 6 4, 6 6, 4 6, 4 4))', 4326))
    """)
    yield path
    try:
        os.unlink(path)
    except PermissionError:
        pass


@pytest.fixture
def tmp_gpkg_points():
    """Create a temporary GeoPackage with test point data."""
    path = _create_test_gpkg("POINT", """
        CREATE TABLE test_layer (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            geom GEOMETRY
        );
        INSERT INTO test_layer (name, category, geom) VALUES
        ('Park', 'recreation', ST_GeomFromText('POINT(1 2)', 4326)),
        ('School', 'education', ST_GeomFromText('POINT(3 4)', 4326)),
        ('Hospital', 'health', ST_GeomFromText('POINT(5 6)', 4326))
    """)
    yield path
    try:
        os.unlink(path)
    except PermissionError:
        pass


@pytest.fixture
def tmp_gpkg_lines():
    """Create a temporary GeoPackage with test line data."""
    path = _create_test_gpkg("LINESTRING", """
        CREATE TABLE test_layer (
            fid INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            width REAL,
            geom GEOMETRY
        );
        INSERT INTO test_layer (name, width, geom) VALUES
        ('Main St', 12.0, ST_GeomFromText('LINESTRING(0 0, 1 1, 2 2)', 4326)),
        ('Side St', 8.0, ST_GeomFromText('LINESTRING(3 3, 4 4, 5 5)', 4326))
    """)
    yield path
    try:
        os.unlink(path)
    except PermissionError:
        pass


# ---------------------------------------------------------------------------
# GeoJSON Export Tests
# ---------------------------------------------------------------------------

class TestExportGeoJSON:
    """Tests for GeoPackage -> GeoJSON export."""

    def test_export_polygon_layer(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        out_path = tempfile.mktemp(suffix=".geojson")
        try:
            result = export_geojson(con, "test_layer", out_path)
            assert result.exists()

            fc = json.loads(result.read_text(encoding="utf-8"))
            assert fc["type"] == "FeatureCollection"
            assert len(fc["features"]) == 3

            f0 = fc["features"][0]
            assert f0["type"] == "Feature"
            assert f0["geometry"]["type"] == "Polygon"
            assert f0["properties"]["name"] == "Building A"
            assert f0["properties"]["height"] == 10.5
        finally:
            con.close()
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_export_point_layer(self, tmp_gpkg_points):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson

        con = connect(tmp_gpkg_points, enable_gpkg_mode=False)
        out_path = tempfile.mktemp(suffix=".geojson")
        try:
            result = export_geojson(con, "test_layer", out_path)
            fc = json.loads(result.read_text(encoding="utf-8"))
            assert len(fc["features"]) == 3
            assert fc["features"][0]["geometry"]["type"] == "Point"
            assert fc["features"][0]["geometry"]["coordinates"] == [1.0, 2.0]
        finally:
            con.close()
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_export_line_layer(self, tmp_gpkg_lines):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson

        con = connect(tmp_gpkg_lines, enable_gpkg_mode=False)
        out_path = tempfile.mktemp(suffix=".geojson")
        try:
            result = export_geojson(con, "test_layer", out_path)
            fc = json.loads(result.read_text(encoding="utf-8"))
            assert len(fc["features"]) == 2
            assert fc["features"][0]["geometry"]["type"] == "LineString"
        finally:
            con.close()
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_export_respects_geom_col(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        out_path = tempfile.mktemp(suffix=".geojson")
        try:
            result = export_geojson(con, "test_layer", out_path, geom_col="geom")
            assert result.exists()
            fc = json.loads(result.read_text(encoding="utf-8"))
            assert len(fc["features"]) == 3
        finally:
            con.close()
            if os.path.exists(out_path):
                os.unlink(out_path)


# ---------------------------------------------------------------------------
# GeoJSON Import Tests
# ---------------------------------------------------------------------------

class TestImportGeoJSON:
    """Tests for GeoJSON -> GeoPackage import."""

    def test_import_polygon_geojson(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import import_geojson

        fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                    "properties": {"name": "House", "area": 100.0}
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]]},
                    "properties": {"name": "Office", "area": 200.0}
                }
            ]
        }
        geojson_path = Path(tempfile.mktemp(suffix=".geojson"))
        geojson_path.write_text(json.dumps(fc), encoding="utf-8")

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            layer = import_geojson(tmp_gpkg, geojson_path, "test_buildings")
            assert layer == "test_buildings"

            count = con.execute("SELECT COUNT(*) FROM [test_buildings]").fetchone()[0]
            assert count == 2

            row = con.execute("SELECT name, area FROM [test_buildings] ORDER BY fid").fetchone()
            assert row[0] == "House"
            assert row[1] == 100.0

            geom = con.execute("SELECT geom FROM [test_buildings]").fetchone()[0]
            assert geom is not None
        finally:
            con.close()
            geojson_path.unlink(missing_ok=True)

    def test_import_point_geojson(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import import_geojson

        fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [10, 20]},
                    "properties": {"label": "A"}
                }
            ]
        }
        geojson_path = Path(tempfile.mktemp(suffix=".geojson"))
        geojson_path.write_text(json.dumps(fc), encoding="utf-8")

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            layer = import_geojson(tmp_gpkg, geojson_path, "points")
            assert layer == "points"
            count = con.execute("SELECT COUNT(*) FROM [points]").fetchone()[0]
            assert count == 1
        finally:
            con.close()
            geojson_path.unlink(missing_ok=True)

    def test_import_to_new_gpkg(self):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import import_geojson

        new_path = Path(tempfile.mktemp(suffix=".gpkg"))
        fc = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5, 10]},
                    "properties": {"id": 1}
                }
            ]
        }
        geojson_path = Path(tempfile.mktemp(suffix=".geojson"))
        geojson_path.write_text(json.dumps(fc), encoding="utf-8")

        con = None
        try:
            layer = import_geojson(new_path, geojson_path, "new_layer")
            assert new_path.exists()

            con = connect(new_path, enable_gpkg_mode=False)
            count = con.execute("SELECT COUNT(*) FROM [new_layer]").fetchone()[0]
            assert count == 1
        finally:
            if con:
                con.close()
            geojson_path.unlink(missing_ok=True)
            if new_path.exists():
                new_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GeoJSON Roundtrip Tests
# ---------------------------------------------------------------------------

class TestGeoJSONRoundtrip:
    """Tests that export -> import preserves data."""

    def test_polygon_roundtrip(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson, import_geojson

        geojson_path = Path(tempfile.mktemp(suffix=".geojson"))
        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            export_geojson(con, "test_layer", geojson_path)
        finally:
            con.close()

        layer = import_geojson(tmp_gpkg, geojson_path, "test_copy")
        assert layer == "test_copy"

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            orig_count = con.execute("SELECT COUNT(*) FROM [test_layer]").fetchone()[0]
            copy_count = con.execute("SELECT COUNT(*) FROM [test_copy]").fetchone()[0]
            assert orig_count == copy_count == 3

            orig_names = [r[0] for r in con.execute("SELECT name FROM [test_layer] ORDER BY fid").fetchall()]
            copy_names = [r[0] for r in con.execute("SELECT name FROM [test_copy] ORDER BY fid").fetchall()]
            assert orig_names == copy_names
        finally:
            con.close()
            geojson_path.unlink(missing_ok=True)

    def test_point_roundtrip(self, tmp_gpkg_points):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_geojson, import_geojson

        geojson_path = Path(tempfile.mktemp(suffix=".geojson"))
        con = connect(tmp_gpkg_points, enable_gpkg_mode=False)
        try:
            export_geojson(con, "test_layer", geojson_path)
        finally:
            con.close()

        layer = import_geojson(tmp_gpkg_points, geojson_path, "points_copy")
        con = connect(tmp_gpkg_points, enable_gpkg_mode=False)
        try:
            copy_count = con.execute("SELECT COUNT(*) FROM [points_copy]").fetchone()[0]
            assert copy_count == 3
        finally:
            con.close()
            geojson_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Shapefile Export Tests (require pyshp)
# ---------------------------------------------------------------------------

class TestExportShapefile:
    """Tests for GeoPackage -> Shapefile export."""

    def _cleanup_shp(self, base_path):
        """Remove shapefile sidecar files."""
        base = Path(base_path).with_suffix("")
        for ext in [".shp", ".shx", ".dbf", ".prj"]:
            p = base.with_suffix(ext)
            try:
                if p.exists():
                    os.unlink(p)
            except PermissionError:
                pass  # Windows: file may still be locked

    def test_export_polygon_shp(self, tmp_gpkg):
        try:
            import shapefile as shp
        except ImportError:
            pytest.skip("pyshp not installed")

        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_shapefile

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        out = tempfile.mktemp(suffix=".shp")
        try:
            result = export_shapefile(con, "test_layer", out)
            assert result.exists()

            sf = shp.Reader(str(Path(out).with_suffix("")))
            count = len(sf.shapes())
            sf.close()
            assert count == 3
        finally:
            con.close()
            self._cleanup_shp(out)

    def test_export_point_shp(self, tmp_gpkg_points):
        try:
            import shapefile as shp
        except ImportError:
            pytest.skip("pyshp not installed")

        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_shapefile

        con = connect(tmp_gpkg_points, enable_gpkg_mode=False)
        out = tempfile.mktemp(suffix=".shp")
        try:
            result = export_shapefile(con, "test_layer", out)
            assert result.exists()

            sf = shp.Reader(str(Path(out).with_suffix("")))
            count = len(sf.shapes())
            sf.close()
            assert count == 3
        finally:
            con.close()
            self._cleanup_shp(out)

    def test_export_line_shp(self, tmp_gpkg_lines):
        try:
            import shapefile as shp
        except ImportError:
            pytest.skip("pyshp not installed")

        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_shapefile

        con = connect(tmp_gpkg_lines, enable_gpkg_mode=False)
        out = tempfile.mktemp(suffix=".shp")
        try:
            result = export_shapefile(con, "test_layer", out)
            assert result.exists()

            sf = shp.Reader(str(Path(out).with_suffix("")))
            count = len(sf.shapes())
            sf.close()
            assert count == 2
        finally:
            con.close()
            self._cleanup_shp(out)

    def test_export_preserves_attributes(self, tmp_gpkg):
        try:
            import shapefile as shp
        except ImportError:
            pytest.skip("pyshp not installed")

        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import export_shapefile

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        out = tempfile.mktemp(suffix=".shp")
        try:
            export_shapefile(con, "test_layer", out)

            sf = shp.Reader(str(Path(out).with_suffix("")))
            records = [sr.record for sr in sf.iterShapeRecords()]
            names = [r[0] for r in records]
            sf.close()
            assert "Building A" in names
            assert "Building B" in names
        finally:
            con.close()
            self._cleanup_shp(out)


# ---------------------------------------------------------------------------
# Shapefile Import Tests (require pyshp)
# ---------------------------------------------------------------------------

class TestImportShapefile:
    """Tests for Shapefile -> GeoPackage import."""

    def test_import_polygon_shp(self, tmp_gpkg):
        try:
            import shapefile as shp
        except ImportError:
            pytest.skip("pyshp not installed")

        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import import_shapefile

        # Create a shapefile with pyshp
        shp_path = tempfile.mktemp(suffix=".shp")
        w = shp.Writer(shp_path, shapeType=shp.POLYGON)
        w.field("name", "C", size=50)
        w.field("height", "N", size=10, decimal=2)
        w.poly([[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]])
        w.record("Test Building", 15.5)
        w.poly([[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]])
        w.record("Test Office", 25.0)
        w.close()

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            layer = import_shapefile(tmp_gpkg, shp_path, "imported_buildings")
            assert layer == "imported_buildings"

            count = con.execute("SELECT COUNT(*) FROM [imported_buildings]").fetchone()[0]
            assert count == 2

            row = con.execute("SELECT name, height FROM [imported_buildings] ORDER BY fid").fetchone()
            assert row[0] == "Test Building"
            assert row[1] == 15.5
        finally:
            con.close()
            for ext in [".shp", ".shx", ".dbf"]:
                p = Path(shp_path).with_suffix(ext)
                try:
                    if p.exists():
                        os.unlink(p)
                except PermissionError:
                    pass


# ---------------------------------------------------------------------------
# WKT Conversion Tests
# ---------------------------------------------------------------------------

class TestWKTToGeoJSON:
    """Tests for WKT string to GeoJSON conversion."""

    def test_point_conversion(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import _wkt_to_geojson_geom

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            row = con.execute("SELECT ST_AsText(ST_GeomFromText('POINT(1 2)', 4326))").fetchone()
            result = _wkt_to_geojson_geom(row[0])
            assert result["type"] == "Point"
            assert result["coordinates"] == [1.0, 2.0]
        finally:
            con.close()

    def test_linestring_conversion(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import _wkt_to_geojson_geom

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            row = con.execute("SELECT ST_AsText(ST_GeomFromText('LINESTRING(0 0, 1 1, 2 2)', 4326))").fetchone()
            result = _wkt_to_geojson_geom(row[0])
            assert result["type"] == "LineString"
            assert len(result["coordinates"]) == 3
        finally:
            con.close()

    def test_polygon_conversion(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import _wkt_to_geojson_geom

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            row = con.execute("SELECT ST_AsText(ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326))").fetchone()
            result = _wkt_to_geojson_geom(row[0])
            assert result["type"] == "Polygon"
            assert len(result["coordinates"]) == 1
        finally:
            con.close()

    def test_multipolygon_conversion(self, tmp_gpkg):
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import _wkt_to_geojson_geom

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            wkt = "MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)), ((2 2, 3 2, 3 3, 2 3, 2 2)))"
            result = _wkt_to_geojson_geom(wkt)
            assert result["type"] == "MultiPolygon"
            assert len(result["coordinates"]) == 2
        finally:
            con.close()

    def test_wkt_roundtrip_via_spatialite(self, tmp_gpkg):
        """Test WKT roundtrip: insert via ST_GeomFromText, export via ST_AsText."""
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import _wkt_to_geojson_geom

        con = connect(tmp_gpkg, enable_gpkg_mode=False)
        try:
            row = con.execute(
                "SELECT ST_AsText(ST_GeomFromText('POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))', 4326))"
            ).fetchone()
            result = _wkt_to_geojson_geom(row[0])
            assert result["type"] == "Polygon"
            coords = result["coordinates"][0]
            assert len(coords) == 5
            assert coords[0] == [0.0, 0.0]
            assert coords[2] == [10.0, 10.0]
        finally:
            con.close()

class TestImportSRIDRegression:
    """Regression tests for geometry blob SRID handling on import.

    Blobs written without an explicit SRID made spatial functions such as
    ST_Intersects return -1 (an error code) on some code paths, which SQLite
    treats as truthy, so clip/intersect silently kept every feature.
    """

    POINTS = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 10.0]}, "properties": {"id": "inside"}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [30.0, 30.0]}, "properties": {"id": "outside_ne"}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-5.0, -5.0]}, "properties": {"id": "outside_sw"}},
        ],
    }

    BOUNDARY = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Polygon", "coordinates": [[[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0], [0.0, 0.0]]]},
             "properties": {"name": "boundary"}},
        ],
    }

    def test_import_sets_blob_srid_and_clip_filters(self, tmp_path):
        """Imported blobs carry SRID 4326, and clip keeps only inside features."""
        from geopkgtoolkit._spatialite import connect
        from geopkgtoolkit.convert import import_geojson
        from geopkgtoolkit.operations import clip

        points_path = tmp_path / "points.geojson"
        boundary_path = tmp_path / "boundary.geojson"
        points_path.write_text(json.dumps(self.POINTS))
        boundary_path.write_text(json.dumps(self.BOUNDARY))

        gpkg = tmp_path / "test.gpkg"
        import_geojson(gpkg, boundary_path, "project_boundary")
        import_geojson(gpkg, points_path, "surveys")

        # Fresh connection with GPKG mode on (the CLI default): the scenario
        # that used to produce silently wrong results
        con = connect(gpkg)
        try:
            blob = con.execute("SELECT HEX(geom) FROM surveys LIMIT 1").fetchone()[0]
            assert blob[:8] == "0001E610", f"expected SRID 4326 in blob header, got {blob[:8]}"

            n = con.execute(
                "SELECT COUNT(*) FROM surveys s, project_boundary b "
                "WHERE ST_Intersects(s.geom, b.geom) = 1"
            ).fetchone()[0]
            assert n == 1

            out = clip(con, "surveys", "project_boundary", output_table="clipped")
            count = con.execute(f"SELECT COUNT(*) FROM [{out}]").fetchone()[0]
            assert count == 1
        finally:
            con.close()
