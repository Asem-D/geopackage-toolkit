# geopackage-toolkit

**The missing Python toolkit for GeoPackage spatial data.**

Validate, query, convert, and publish spatial data without PostGIS or ArcGIS. Zero compiled dependencies. One file format. Clean Python API.

---

## Quick Example

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

## Why This Exists

GeoPackage is the [OGC standard](https://www.ogc.org/standard/geopackage/) that replaces Shapefile. It is SQLite-based, supports vector, raster, and tiles, and works everywhere. But the tooling around it is fractured:

- **ogr2ogr** works but is not Pythonic
- **GeoPandas** adds heavy compiled dependencies (GDAL, GEOS, PROJ)
- **SpatiaLite** has Windows quirks nobody documents
- No single package covers validate, query, convert, and publish

This toolkit fills that gap.

## Key Features

### Geometry Validation

Catch problems before they waste your time:

```python
from geopkgtoolkit import validate_layers

report = validate_layers("buildings.gpkg", expected_srid=4326)
print(report.summary())
# GeoPackage: buildings.gpkg
# 3 layers, 125,000 features, 0 warnings
#   buildings: 80,000 features, SRID=4326, OK
#   roads: 44,000 features, SRID=4326, OK
#   admin3: 1,627 features, SRID=4326, OK
```

Checks for:

- NULL geometries
- Empty geometries
- Invalid geometries (self-intersections, ring orientation)
- SRID mismatches
- Bounding box anomalies

### Spatial Queries

Rtree-accelerated spatial operations that run in seconds, not minutes:

```python
from geopkgtoolkit import connect, count_in_zones, bbox_filter

con = connect("data.gpkg")

# Count features per zone (rtree-accelerated)
counts = count_in_zones(con, "buildings", "admin3")
# Returns: [(zone_fid, count), ...]

# Bounding box filter
fids = bbox_filter(con, "buildings", (35.4, 33.8, 35.6, 33.9))

# Point-in-polygon classification
from geopkgtoolkit import points_in_polygons
result = points_in_polygons(con, "pois", "districts")
```

### CLI Interface

Three commands for quick operations:

```bash
geopkg validate data.gpkg --srid 4326
geopkg count data.gpkg --features buildings --zones admin3
geopkg info data.gpkg
```

## Architecture

```
geopkgtoolkit/
  _spatialite.py    # Windows-aware SpatiaLite connection helper
  validate.py       # Geometry health checks
  query.py          # Rtree-accelerated spatial queries
  cli.py            # Command-line interface
```

All spatial operations use **SpatiaLite** (embedded spatial SQL extension for SQLite) with **GeoPackage's native rtree tables** for spatial indexing. This means:

- No server process (unlike PostGIS)
- No compiled Python bindings (unlike GeoPandas/GDAL)
- Single `.gpkg` file per dataset
- Works on Windows, Linux, macOS

## Performance

| Operation | Method | 500k features x 1k zones |
|-----------|--------|--------------------------|
| `count_in_zones` | rtree bbox + ST_Contains | ~8 seconds |
| `count_in_zones` (no index) | ST_Contains only | >10 minutes |
| `bbox_filter` | rtree lookup | <1 second |

The toolkit auto-creates rtree indexes when missing. First run builds the index, subsequent runs use it.

## Roadmap

- [x] v0.1.0: Validate + Query modules, CLI
- [ ] v0.2.0: Format conversion (Shapefile, GeoJSON, FlatGeobuf)
- [ ] v0.3.0: QGIS Processing headless access
- [ ] v0.4.0: Config-driven batch pipeline
- [ ] v0.5.0: Vector tile generation
- [ ] v1.0.0: Full toolkit with visualization and schema extraction

## License

MIT

---

**Links**: [GitHub](https://github.com/Asem-D/geopackage-toolkit) | [PyPI](https://pypi.org/project/geopackage-toolkit/) | [Changelog](changelog.md)
