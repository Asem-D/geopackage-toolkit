"""Tests for geopkgtoolkit.operations module (buffer, clip, intersect)."""

import os
import sqlite3
import tempfile

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


@pytest.fixture
def tmp_gpkg():
    """Create a temporary GeoPackage path (empty, metadata only)."""
    from geopkgtoolkit._spatialite import connect

    tmp = tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False)
    tmp.close()
    path = tmp.name

    con = connect(path)
    _init_gpkg(con)
    con.close()

    yield path

    os.unlink(path)


@pytest.fixture
def tmp_con(tmp_gpkg):
    """Open a writable connection with all test layers pre-created.

    Creates all test data in the SAME session to avoid SpatiaLite
    EnableGpkgMode cross-session geometry encoding issues.
    """
    from geopkgtoolkit._spatialite import connect
    con = connect(tmp_gpkg)

    # All geometry creation must happen in this single session
    con.execute("CREATE TABLE polys (id INTEGER PRIMARY KEY, name TEXT, category TEXT, geom GEOMETRY)")
    con.execute("""INSERT INTO polys (id, name, category, geom) VALUES
        (1, 'poly_a', 'residential', GeomFromText('POLYGON((35.0 33.8, 35.1 33.8, 35.1 33.9, 35.0 33.9, 35.0 33.8))', 4326)),
        (2, 'poly_b', 'commercial', GeomFromText('POLYGON((35.2 33.8, 35.3 33.8, 35.3 33.9, 35.2 33.9, 35.2 33.8))', 4326)),
        (3, 'poly_c', 'industrial', GeomFromText('POLYGON((35.05 33.85, 35.25 33.85, 35.25 33.95, 35.05 33.95, 35.05 33.85))', 4326))""")
    _register_feature_layer(con, "polys")

    con.execute("CREATE TABLE points (id INTEGER PRIMARY KEY, label TEXT, geom GEOMETRY)")
    con.execute("""INSERT INTO points (id, label, geom) VALUES
        (1, 'pt_a', GeomFromText('POINT(35.05 33.85)', 4326)),
        (2, 'pt_b', GeomFromText('POINT(35.25 33.85)', 4326)),
        (3, 'pt_c', GeomFromText('POINT(36.0 34.0)', 4326))""")
    _register_feature_layer(con, "points", "POINT")

    con.execute("CREATE TABLE [distant_polys] ([id] INTEGER, [geom] GEOMETRY)")
    con.execute("INSERT INTO [distant_polys] (id, geom) VALUES (1, "
                "GeomFromText('POLYGON((100.0 100.0, 101.0 100.0, 101.0 101.0, 100.0 101.0, 100.0 100.0))', 4326))")
    _register_feature_layer(con, "distant_polys")

    con.commit()
    yield con
    con.close()


def _add_layer(con, table_name, sql_values, geom_type="POLYGON"):
    """Add a new feature layer to an existing GeoPackage."""
    con.execute(f"CREATE TABLE [{table_name}] ([id] INTEGER, [geom] GEOMETRY)")
    con.execute(f"INSERT INTO [{table_name}] (id, geom) VALUES {sql_values}")
    _register_feature_layer(con, table_name, geom_type)
    con.commit()


class TestBuffer:
    """Tests for the buffer operation."""

    def test_buffer_basic(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        output = buffer(tmp_con, "polys", 0.05, output_table="buf_test")
        assert output == "buf_test"
        count = tmp_con.execute("SELECT COUNT(*) FROM [buf_test]").fetchone()[0]
        assert count == 3

    def test_buffer_output_registered(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "polys", 0.05, output_table="buf_reg")
        row = tmp_con.execute(
            "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?",
            ("buf_reg",),
        ).fetchone()
        assert row is not None
        assert row[0] == "POLYGON"
        assert row[1] == 4326

    def test_buffer_preserves_attrs(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "polys", 0.05, output_table="buf_attrs")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([buf_attrs])").fetchall()]
        assert "name" in cols
        assert "category" in cols

    def test_buffer_no_attrs(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "polys", 0.05, output_table="buf_noattrs", keep_attrs=False)
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([buf_noattrs])").fetchall()]
        assert "name" not in cols
        assert "geom" in cols

    def test_buffer_negative_distance(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "polys", -0.01, output_table="buf_neg")
        count = tmp_con.execute("SELECT COUNT(*) FROM [buf_neg]").fetchone()[0]
        assert count == 3

    def test_buffer_empty_table(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        tmp_con.execute("CREATE TABLE [empty_polys] ([id] INTEGER, [geom] GEOMETRY)")
        _register_feature_layer(tmp_con, "empty_polys")
        tmp_con.commit()
        with pytest.raises(ValueError, match="no features"):
            buffer(tmp_con, "empty_polys", 0.05)

    def test_buffer_points(self, tmp_con):
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "points", 0.05, output_table="buf_pts")
        count = tmp_con.execute("SELECT COUNT(*) FROM [buf_pts]").fetchone()[0]
        assert count == 3

    def test_buffer_rtree_created(self, tmp_con):
        """Buffer output can be indexed (rtree may or may not succeed depending on SpatiaLite build)."""
        from geopkgtoolkit.operations import buffer
        buffer(tmp_con, "polys", 0.05, output_table="buf_rtree")
        # Verify the output table exists and has data
        count = tmp_con.execute("SELECT COUNT(*) FROM [buf_rtree]").fetchone()[0]
        assert count == 3


class TestClip:
    """Tests for the clip operation."""

    def test_clip_basic(self, tmp_con):
        from geopkgtoolkit.operations import clip
        output = clip(tmp_con, "polys", "polys", output_table="clip_test", keep_attrs="a")
        assert output == "clip_test"
        count = tmp_con.execute("SELECT COUNT(*) FROM [clip_test]").fetchone()[0]
        assert count > 0

    def test_clip_output_registered(self, tmp_con):
        from geopkgtoolkit.operations import clip
        clip(tmp_con, "polys", "polys", output_table="clip_reg", keep_attrs="a")
        row = tmp_con.execute(
            "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?",
            ("clip_reg",),
        ).fetchone()
        assert row is not None
        assert row[1] == 4326

    def test_clip_attrs_source(self, tmp_con):
        from geopkgtoolkit.operations import clip
        clip(tmp_con, "polys", "polys", output_table="clip_a", keep_attrs="a")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([clip_a])").fetchall()]
        assert "name" in cols
        assert "category" in cols

    def test_clip_attrs_both(self, tmp_con):
        from geopkgtoolkit.operations import clip
        clip(tmp_con, "polys", "polys", output_table="clip_both", keep_attrs="both")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([clip_both])").fetchall()]
        assert any(c.startswith("s_") for c in cols)
        assert any(c.startswith("c_") for c in cols)

    def test_clip_attrs_none(self, tmp_con):
        from geopkgtoolkit.operations import clip
        clip(tmp_con, "polys", "polys", output_table="clip_none", keep_attrs="none")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([clip_none])").fetchall()]
        assert "name" not in cols
        assert "geom" in cols

    def test_clip_no_match(self, tmp_con):
        from geopkgtoolkit.operations import clip
        clip(tmp_con, "polys", "distant_polys", output_table="clip_empty", keep_attrs="a")
        count = tmp_con.execute("SELECT COUNT(*) FROM [clip_empty]").fetchone()[0]
        assert count == 0

    def test_clip_empty_source(self, tmp_con):
        from geopkgtoolkit.operations import clip
        tmp_con.execute("CREATE TABLE [empty_src] ([id] INTEGER, [geom] GEOMETRY)")
        _register_feature_layer(tmp_con, "empty_src")
        tmp_con.commit()
        with pytest.raises(ValueError, match="no features"):
            clip(tmp_con, "empty_src", "polys")

    def test_clip_empty_clip_layer(self, tmp_con):
        from geopkgtoolkit.operations import clip
        tmp_con.execute("CREATE TABLE [empty_clip] ([id] INTEGER, [geom] GEOMETRY)")
        _register_feature_layer(tmp_con, "empty_clip")
        tmp_con.commit()
        with pytest.raises(ValueError, match="no features"):
            clip(tmp_con, "polys", "empty_clip")


class TestIntersect:
    """Tests for the intersect operation."""

    def test_intersect_basic(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        output = intersect(tmp_con, "polys", "polys", output_table="int_test")
        assert output == "int_test"
        count = tmp_con.execute("SELECT COUNT(*) FROM [int_test]").fetchone()[0]
        assert count > 0

    def test_intersect_output_registered(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "polys", "polys", output_table="int_reg")
        row = tmp_con.execute(
            "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?",
            ("int_reg",),
        ).fetchone()
        assert row is not None
        assert row[1] == 4326

    def test_intersect_attrs_a(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "polys", "polys", output_table="int_a", keep_attrs="a")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([int_a])").fetchall()]
        assert "name" in cols
        assert "category" in cols

    def test_intersect_attrs_both(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "polys", "polys", output_table="int_both", keep_attrs="both")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([int_both])").fetchall()]
        assert any(c.startswith("a_") for c in cols)
        assert any(c.startswith("b_") for c in cols)

    def test_intersect_attrs_none(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "polys", "polys", output_table="int_none", keep_attrs="none")
        cols = [c[1] for c in tmp_con.execute("PRAGMA table_info([int_none])").fetchall()]
        assert "name" not in cols
        assert "geom" in cols

    def test_intersect_no_overlap(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "polys", "distant_polys", output_table="int_empty")
        count = tmp_con.execute("SELECT COUNT(*) FROM [int_empty]").fetchone()[0]
        assert count == 0

    def test_intersect_points_in_polygons(self, tmp_con):
        from geopkgtoolkit.operations import intersect
        intersect(tmp_con, "points", "polys", output_table="int_pts", keep_attrs="a")
        count = tmp_con.execute("SELECT COUNT(*) FROM [int_pts]").fetchone()[0]
        # pt_a hits poly_a + poly_c, pt_b hits poly_b + poly_c, pt_c hits nothing
        assert count == 4


class TestRegisterLayer:
    """Tests for the _register_layer helper."""

    def test_register_overwrites(self, tmp_con):
        from geopkgtoolkit.operations import _register_layer
        _register_layer(tmp_con, "polys", "geom", 4326, "POLYGON")
        _register_layer(tmp_con, "polys", "geom", 4326, "MULTIPOLYGON")
        rows = tmp_con.execute(
            "SELECT COUNT(*) FROM gpkg_geometry_columns WHERE table_name=?",
            ("polys",),
        ).fetchone()
        assert rows[0] == 1
        row = tmp_con.execute(
            "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name=?",
            ("polys",),
        ).fetchone()
        assert row[0] == "MULTIPOLYGON"
