# Changelog

All notable changes to geopackage-toolkit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-08-15

### Added

- `connect()` function with Windows-aware SpatiaLite loading
- `list_layers()` function for GeoPackage layer discovery
- `validate_layer()` for single-layer geometry validation
- `validate_layers()` for full GeoPackage validation
- `LayerReport` dataclass with per-layer validation results
- `GpkgReport` dataclass with package-level validation summary
- `count_in_zones()` for rtree-accelerated spatial join counting
- `bbox_filter()` for rtree-accelerated bounding box queries
- `points_in_polygons()` for point-in-polygon classification
- CLI commands: `geopkg info`, `geopkg validate`, `geopkg count`
- Google-style docstrings for all public functions
- MkDocs documentation with Material theme
- API reference auto-generated from docstrings
- Cookbook with 10 real-world recipes
- GitHub Actions CI for Python 3.10-3.13 on Windows and Ubuntu

### Fixed

- `Envelope().bounds` returns `(0,0,0,0)` on GeoPackage blobs through SpatiaLite (use SQL `ST_MinX/ST_MaxX` instead)
- `gpkg_geometry_columns` uses column name `srs_id`, not `srid`

### Known Issues

- `count_in_zones` first run is slower (builds rtree index)
- Some GEOS warnings for degenerate geometry components in contour data
