# geopackage-toolkit

Python toolkit for GeoPackage spatial data. Validate, query, and explore spatial data without PostGIS or ArcGIS.

**Zero compiled dependencies.** Uses SpatiaLite (embedded in SQLite) for all spatial operations. One file format (`.gpkg`), one dependency chain, clean Python API.

```python
from geopkgtoolkit import connect, validate_layers, count_in_zones

# Validate geometry health
report = validate_layers("data.gpkg", expected_srid=4326)
print(report.summary())

# Count buildings per administrative zone
con = connect("data.gpkg")
counts = count_in_zones(con, "buildings", "admin3")
for zone_id, count in counts[:5]:
    print(f"Zone {zone_id}: {count} buildings")
```

## Why

GeoPackage is the [OGC standard](https://www.ogc.org/standard/geopackage/) that replaces Shapefile. It's SQLite-based, supports vector + raster + tiles, and works everywhere. But the tooling around it is fractured:

- `ogr2ogr` works but isn't Pythonic
- `GeoPandas` adds heavy compiled dependencies
- `SpatiaLite` has Windows quirks nobody documents
- No single package covers validate-query-convert-publish

This toolkit fills that gap. Local-first, no server required.

## Installation

```bash
pip install geopackage-toolkit
```

### Prerequisites

**SpatiaLite** must be installed on your system:

| OS | Install |
|----|---------|
| Windows | Download from [gaia-gis.it](https://www.gaia-gis.it/gaia-sins/windows-bin-amd64/) and set `SPATIALITE_DIR` env var |
| Ubuntu/Debian | `sudo apt install libspatialite-dev` |
| macOS | `brew install libspatialite` |
| Conda | `conda install -c conda-forge libspatialite` |

## CLI

```bash
# Validate geometry health
geopkg validate data.gpkg --srid 4326

# Count features per zone
geopkg count data.gpkg --features buildings --zones admin3

# Show layer info
geopkg info data.gpkg
```

## Python API

### Validate

```python
from geopkgtoolkit import validate_layers, validate_layer

# Validate all layers
report = validate_layers("data.gpkg", expected_srid=4326)
print(report.summary())
# GeoPackage: data.gpkg
# 9 layers, 685,968 features, 0 warnings
#   OSM_Buildings: 515,013 features, SRID=4326, OK
#   lbn_adm3: 1,627 features, SRID=4326, OK
#   ...

assert report.is_valid  # True if no warnings

# Validate a single layer
con = validate_layer(con, "buildings", expected_srid=4326)
```

Checks: null geometries, empty geometries, invalid geometries (self-intersections), SRID mismatches, bounding box sanity.

### Query

```python
from geopkgtoolkit import connect, count_in_zones, bbox_filter

con = connect("data.gpkg")

# Count features per zone (rtree-accelerated)
counts = count_in_zones(con, "buildings", "admin3")
# Returns: [(zone_fid, count), ...]

# Bounding box filter (rtree-accelerated)
fids = bbox_filter(con, "buildings", (35.4, 33.8, 35.6, 33.9))
# Returns: [fid, ...]

# Point-in-polygon classification
from geopkgtoolkit import points_in_polygons
result = points_in_polygons(con, "pois", "districts")
# Returns: [(point_fid, polygon_fid_or_None), ...]
```

### Connect

```python
from geopkgtoolkit import connect

con = connect("data.gpkg")  # Auto-loads SpatiaLite
layers = con.execute("SELECT table_name FROM gpkg_geometry_columns").fetchall()
con.close()
```

## How It Works

All spatial operations use **SpatiaLite** (embedded spatial SQL extension for SQLite) with **GeoPackage's native rtree tables** for spatial indexing. This means:

- No server process (unlike PostGIS)
- No compiled Python bindings (unlike GeoPandas/GDAL wheels)
- Single `.gpkg` file per dataset
- Works on Windows, Linux, macOS

### Performance

| Operation | Method | 500k features x 1k zones |
|-----------|--------|--------------------------|
| `count_in_zones` | rtree bbox + ST_Contains | ~30 seconds |
| `count_in_zones` (no index) | ST_Contains only | >10 minutes |
| `bbox_filter` | rtree lookup | <1 second |

The toolkit auto-creates rtree indexes when missing. First run builds the index, subsequent runs use it.

## Roadmap

- [x] v0.1.0: Validate + Query modules
- [ ] v0.2.0: Format conversion (Shapefile, GeoJSON, FlatGeobuf to/from GeoPackage)
- [ ] v0.3.0: QGIS Processing headless access (buffer, clip, dissolve, spatial join)
- [ ] v0.4.0: Config-driven batch pipeline
- [ ] v0.5.0: Vector tile generation for web publishing
- [ ] v1.0.0: Full toolkit with visualization and schema extraction

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

## License

MIT

## Acknowledgments

Built on top of [SpatiaLite](https://www.gaia-gis.it/fossil/spatialite) by Alessandro Furieri and the [GeoPackage](https://www.ogc.org/standard/geopackage/) OGC standard.
