# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Imported geometry blobs now carry the registered SRID** (`SetSRID(GeomFromGeoJSON(...), srid)`). Previously the blob SRID could be left unset (0/-1), and mismatched blob SRIDs made `ST_Intersects` return `-1`, which SQLite treats as truthy — so `clip`/`intersect` could silently keep every feature instead of the matching ones
- Fresh GeoPackages created by `import_geojson()`/`import_shapefile()` now initialize SpatiaLite metadata (`InitSpatialMetaData`), so spatial functions behave consistently regardless of connection mode
- `clip()`/`intersect()` filters now require `ST_Intersects(...) = 1` explicitly, so SpatiaLite error codes can never pass as matches
- CLI `geopkg export` creates missing output directories (consistent with the pipeline export step)
- CLI `geopkg pipeline` header shows the config filename instead of `<dict>`
- CLI reference docs: documented `import`, `export`, `buffer`, `clip`, `intersect`; corrected an inaccurate tip
- 1 new regression test (82 total)

## [0.4.0] - 2026-09-04

### Added
- Config-driven batch pipeline: `run_pipeline()`, `load_config()`, and CLI `geopkg pipeline <config>`
- Pipeline config supports JSON (stdlib) and YAML (optional extra: `pip install geopackage-toolkit[pipeline]`)
- Step types: `import`, `buffer`, `clip`, `intersect`, `export`, `validate`
- Glob batch input for imports (`input: "data/*.geojson"`) with layer names derived from file stems
- `fail_fast` error policy (default `false`: all steps run, failures recorded per step)
- JSON run report written per execution (steps, feature counts, errors, timing)
- CLI exit code `1` when any step fails, `0` on full success (CI-friendly)
- 22 new tests (81 total)

### Fixed
- README roadmap: v0.3.0 shipped GeoJSON + Shapefile conversion; FlatGeobuf moved to backlog

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
