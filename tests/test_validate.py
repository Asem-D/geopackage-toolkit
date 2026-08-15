"""Tests for geopkgtoolkit.validate module."""

import pytest

from geopkgtoolkit.validate import validate_layer, validate_layers, LayerReport, GpkgReport


class TestValidateLayer:
    """Tests against real Mashriq.gpkg data."""

    def test_osm_buildings(self, mashriq_con):
        report = validate_layer(mashriq_con, "OSM_Buildings", expected_srid=4326)
        assert report.feature_count > 500000
        assert report.srid == 4326
        assert report.geometry_type == "MULTIPOLYGON"
        assert report.geometry_column == "geom"
        assert report.is_valid
        assert report.null_count == 0
        assert report.invalid_count == 0
        assert report.bbox is not None
        assert len(report.bbox) == 4

    def test_lbn_adm3(self, mashriq_con):
        report = validate_layer(mashriq_con, "lbn_adm3", expected_srid=4326)
        assert report.feature_count == 1627
        assert report.srid == 4326
        assert report.is_valid

    def test_srid_mismatch(self, mashriq_con):
        report = validate_layer(mashriq_con, "OSM_Buildings", expected_srid=3857)
        assert not report.is_valid
        assert any("SRID mismatch" in w for w in report.warnings)

    def test_nonexistent_table(self, mashriq_con):
        report = validate_layer(mashriq_con, "nonexistent_table")
        assert report.feature_count == 0
        assert len(report.warnings) == 1
        assert "not found" in report.warnings[0]

    def test_summary_format(self, mashriq_con):
        report = validate_layer(mashriq_con, "OSM_Buildings", expected_srid=4326)
        summary = report.summary()
        assert "OSM_Buildings" in summary
        assert "OK" in summary

    def test_populated_places(self, mashriq_con):
        """Test auto-detection of geometry column name."""
        report = validate_layer(mashriq_con, "Populated Places")
        assert report.feature_count > 1000
        # Point layers may trigger bbox warnings, that's expected
        assert report.null_count == 0
        assert report.invalid_count == 0


class TestValidateLayers:
    """Test full GeoPackage validation."""

    def test_all_layers(self, mashriq_path):
        report = validate_layers(mashriq_path, expected_srid=4326)
        assert isinstance(report, GpkgReport)
        assert len(report.layers) == 9
        assert report.total_features > 600000
        # contours_lebanon has 2 invalid geometries, point layers trigger bbox warnings
        # These are real findings, not bugs in the validation
        assert report.total_warnings <= 3  # 2 invalid contours + 1 bbox warning

    def test_specific_layers(self, mashriq_path):
        report = validate_layers(
            mashriq_path,
            expected_srid=4326,
            layers=["OSM_Buildings", "lbn_adm3"],
        )
        assert len(report.layers) == 2
        assert report.is_valid

    def test_summary(self, mashriq_path):
        report = validate_layers(mashriq_path, expected_srid=4326)
        summary = report.summary()
        assert "GeoPackage" in summary
        assert "9 layers" in summary
