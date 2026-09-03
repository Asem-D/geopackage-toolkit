# geopackage-toolkit

[![CI](https://github.com/Asem-D/geopackage-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Asem-D/geopackage-toolkit/actions)
[![Docs](https://readthedocs.org/projects/geopackage-toolkit/badge/?version=latest)](https://geopackage-toolkit.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python toolkit for GeoPackage spatial data. Validate, query, and operate on spatial data without PostGIS or ArcGIS.

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

## Real-World Use Cases

### Building density per district

You're an urban planner. A client sends `mashriq.gpkg` with 515,013 OSM buildings and 1,627 district boundaries. You need buildings per district for a density study. PostGIS means a server to maintain. ArcGIS means a license. This is one function call:

```python
from geopkgtoolkit import connect, count_in_zones

con = connect("mashriq.gpkg")
counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")
# [(zone_fid, count), ...] -- 499,787 buildings in 1,627 zones, ~8 seconds
```

### Flood-risk screening before a site visit

A new project sits next to a seasonal river. Which buildings fall inside the 100 m riparian zone and the flood plain? Buffer, clip, intersect, export for the web team:

```python
from geopkgtoolkit import connect, buffer, clip, intersect, export_geojson

con = connect("mashriq.gpkg")
buffer(con, "rivers", 100, "riparian_zone")          # distance in CRS units
clip(con, "OSM_Buildings", "study_area", "bldgs_in_area")
intersect(con, "bldgs_in_area", "flood_zones", "at_risk")
export_geojson(con, "at_risk", "at_risk.geojson")    # drop into MapLibre/Leaflet
```

Every result is a new layer in the same GeoPackage. Originals stay untouched.

### Client data intake QC

Someone emails you a 125,000-feature GeoPackage. Before it enters your workflow, run one command:

```bash
geopkg validate client_data.gpkg --srid 4326
```

```
GeoPackage: client_data.gpkg
3 layers, 125,000 features, 2 warnings
  parcels: 80,000 features, SRID=4326, OK
  roads: 44,000 features, SRID=4326, 1 warning
    WARNING: SRID mismatch (expected 4326, found 3857)
```

Null geometries, invalid polygons, and SRID mismatches surface in the first minute, not three days into analysis.

### A nightly batch job

Every night: pull the latest survey export, clip it to the project boundary, publish the result for the dashboard. One config file, one command, JSON report:

```yaml
gpkg: project.gpkg
steps:
  - step: import
    input: "inbox/latest_survey.geojson"
    layer: surveys
  - step: clip
    source: surveys
    clip: project_boundary
  - step: export
    layer: clipped
    format: geojson
    output: "out/surveys.geojson"
```

```bash
geopkg pipeline pipeline.yaml
# 3/3 steps ok (1.8s) -- exit 0 means the dashboard data is fresh
```

Failed steps are recorded in the report instead of silently producing stale output. Full config reference in the [Pipeline Guide](docs/guides/pipeline.md).

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

# Buffer features (output saved as new layer in same GeoPackage)
geopkg buffer data.gpkg --layer buildings --distance 100 --output buffered_buildings

# Clip a layer to a boundary
geopkg clip data.gpkg --source buildings --clip district_boundary --output clipped_buildings

# Spatial intersection of two layers
geopkg intersect data.gpkg --layer-a buildings --layer-b flood_zones --output buildings_in_flood

# Export a layer to GeoJSON (pure Python, no extra dependencies)
geopkg export data.gpkg --layer buildings --format geojson --output buildings.geojson

# Export a layer to Shapefile (requires: pip install geopackage-toolkit[convert])
geopkg export data.gpkg --layer buildings --format shapefile --output buildings.shp

# Import GeoJSON into a GeoPackage (creates the file if missing)
geopkg import buildings.geojson --output new_data.gpkg --layer buildings

# Import a Shapefile into a GeoPackage
geopkg import buildings.shp --output new_data.gpkg --layer buildings

# Run a config-driven batch pipeline (JSON or YAML)
geopkg pipeline pipeline.yaml
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

### Spatial Operations

```python
from geopkgtoolkit import connect, buffer, clip, intersect

con = connect("data.gpkg")

# Buffer features by a distance (CRS units)
buffered = buffer(con, "buildings", distance=100, output_table="buffered_buildings")
# Creates new layer with buffered polygons

# Clip features to a boundary
clipped = clip(con, "buildings", "district_boundary", output_table="clipped_buildings")
# Creates new layer with features clipped to polygon boundary

# Spatial intersection of two layers
result = intersect(con, "buildings", "flood_zones", output_table="buildings_in_flood")
# Creates new layer with the intersection of two layers
```

All operations write results back to the same GeoPackage file. Attributes from both layers are preserved in intersection.

### Format Conversion

```python
from geopkgtoolkit import connect, export_geojson, export_shapefile, import_geojson, import_shapefile

con = connect("data.gpkg")

# Export to GeoJSON (pure Python, zero extra dependencies)
export_geojson(con, "buildings", "buildings.geojson")

# Export to Shapefile (requires: pip install geopackage-toolkit[convert])
export_shapefile(con, "buildings", "buildings.shp")
con.close()

# Import GeoJSON (creates the GeoPackage if it doesn't exist)
import_geojson("new_data.gpkg", "input.geojson", "buildings")

# Import Shapefile
import_shapefile("new_data.gpkg", "input.shp", "buildings")
```

GeoJSON export/import is pure Python. Shapefile support requires the optional `pyshp` dependency: `pip install geopackage-toolkit[convert]`.

### Pipeline

```python
from geopkgtoolkit import run_pipeline

# Run a sequence of steps from a config file (JSON or YAML)
report = run_pipeline("pipeline.yaml")

# Or define the pipeline in code
report = run_pipeline({
    "gpkg": "processed.gpkg",
    "steps": [
        {"step": "import", "input": "data/*.geojson"},          # glob batch input
        {"step": "clip",   "source": "buildings", "clip": "districts"},
        {"step": "buffer", "layer": "clipped", "distance": 100},
        {"step": "export", "layer": "buffered", "format": "geojson",
         "output": "out/buffered.geojson"},
        {"step": "validate", "srid": 4326},
    ],
})

assert report["ok"]  # False if any step failed
for step in report["steps"]:
    print(step["step"], step["status"], step.get("features", ""))
```

See the [Pipeline Guide](docs/guides/pipeline.md) for the full config reference.

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
| `count_in_zones` | rtree bbox + ST_Contains | ~8 seconds |
| `count_in_zones` (no index) | ST_Contains only | >10 minutes |
| `bbox_filter` | rtree lookup | <1 second |

The toolkit auto-creates rtree indexes when missing. First run builds the index, subsequent runs use it.

## Roadmap

- [x] v0.1.0: Validate + Query modules
- [x] v0.2.0: Spatial operations (buffer, clip, intersect) with CLI commands
- [x] v0.3.0: Format conversion (GeoJSON + Shapefile import/export)
- [x] v0.4.0: Config-driven batch pipeline (JSON/YAML)
- [ ] v0.5.0: Vector tile generation for web publishing
- [ ] v1.0.0: Full toolkit with visualization and schema extraction

Backlog: FlatGeobuf support, reprojection (requires pyproj), QGIS Processing integration.

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

## License

MIT

## Acknowledgments

Built on top of [SpatiaLite](https://www.gaia-gis.it/fossil/spatialite) by Alessandro Furieri and the [GeoPackage](https://www.ogc.org/standard/geopackage/) OGC standard.
