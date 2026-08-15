"""Tests for geopkgtoolkit.query module."""

import pytest

from geopkgtoolkit.query import count_in_zones, bbox_filter, points_in_polygons


class TestCountInZones:
    """Test spatial join counting against real data."""

    def test_buildings_per_admin3(self, mashriq_con):
        counts = count_in_zones(
            mashriq_con,
            feature_table="OSM_Buildings",
            zone_table="lbn_adm3",
        )
        # Should have one count per admin3 zone
        assert len(counts) == 1627
        # All counts should be non-negative
        assert all(c >= 0 for _, c in counts)
        # Total should roughly match total building count (some at boundaries may be excluded)
        total = sum(c for _, c in counts)
        assert total > 490000
        # At least some zones should have buildings
        assert any(c > 0 for _, c in counts)

    def test_with_explicit_geom_columns(self, mashriq_con):
        counts = count_in_zones(
            mashriq_con,
            feature_table="OSM_Buildings",
            zone_table="lbn_adm3",
            feature_geom="geom",
            zone_geom="geom",
        )
        assert len(counts) == 1627
        assert sum(c for _, c in counts) > 490000

    def test_road_count_per_admin3(self, mashriq_con):
        counts = count_in_zones(
            mashriq_con,
            feature_table="OSM_roads",
            zone_table="lbn_adm3",
        )
        assert len(counts) == 1627
        total = sum(c for _, c in counts)
        assert total > 100000  # Should have many roads


class TestBboxFilter:
    """Test bounding box filtering."""

    def test_beirut_bbox(self, mashriq_con):
        # Beirut city center approximate bbox
        fids = bbox_filter(mashriq_con, "OSM_Buildings", (35.48, 33.87, 35.52, 33.90))
        assert len(fids) > 0

    def test_empty_bbox(self, mashriq_con):
        # Middle of the Mediterranean, no buildings
        fids = bbox_filter(mashriq_con, "OSM_Buildings", (30.0, 30.0, 30.1, 30.1))
        assert len(fids) == 0

    def test_full_extent_bbox(self, mashriq_con):
        # Full Lebanon extent
        fids = bbox_filter(mashriq_con, "OSM_Buildings", (35.0, 33.0, 37.0, 35.0))
        assert len(fids) > 500000


class TestPointsInPolygons:
    """Test point-in-polygon classification."""

    def test_points_in_admin3(self, mashriq_con):
        result = points_in_polygons(
            mashriq_con,
            points_table="Populated Places",
            polygon_table="lbn_adm3",
        )
        # Should have one result per point
        assert len(result) > 1000
        # Most points should be inside a polygon
        classified = sum(1 for _, pid in result if pid is not None)
        assert classified > 0
