# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-09-03

### Added
- `export_geojson()` and CLI `geopkg export --format geojson` for GeoJSON export (pure Python, zero new dependencies)
- `export_shapefile()` and CLI `geopkg export --format shapefile` for Shapefile export (requires optional `pyshp`)
- `import_geojson()` and CLI `geopkg import` for GeoJSON import (creates the GeoPackage if missing)
- `import_shapefile()` for Shapefile import
- Optional dependency extra: `pip install geopackage-toolkit[convert]`
- Custom WKT-to-GeoJSON parser handling all OGC geometry types (Point, LineString, Polygon, Multi*)
- 19 new tests (59 total)

### Fixed
- `connect()` now accepts `enable_gpkg_mode=False` to work around a SpatiaLite 5.1.0 bug where `ST_AsText()` returns NULL after close/reopen when GPKG mode was active

## [0.2.0] - 2026-08-17

### Added
- `buffer()` function and CLI command for buffering features by a distance
- `clip()` function and CLI command for clipping features to a polygon boundary
- `intersect()` function and CLI command for spatial intersection of two layers
- All spatial operations write results back to the same GeoPackage file
- 40 tests across Windows + Ubuntu, Python 3.10-3.13

## [0.1.0] - 2026-08-15

### Added
- `validate_layers()` and `validate_layer()` for geometry health checks (null, empty, invalid, SRID, bbox)
- `count_in_zones()` for rtree-accelerated feature counting per zone
- `bbox_filter()` for rtree-accelerated bounding box queries
- `points_in_polygons()` for point-in-polygon classification
- `connect()` helper for SpatiaLite-aware GeoPackage connections
- CLI commands: `validate`, `count`, `info`
- MkDocs documentation with Material theme
