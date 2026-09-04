# CLI Reference

geopackage-toolkit provides a command-line interface via the `geopkg` command.

## Usage

```bash
geopkg <command> [options] [arguments]
```

## Commands

### `geopkg info`

Show layer information for a GeoPackage file.

```bash
geopkg info <file.gpkg>
```

**Example:**

```bash
$ geopkg info data.gpkg

GeoPackage: data.gpkg
Layers: 9

  buildings: 80,000 features, geom=geom, type=MULTIPOLYGON, srs=4326
  roads: 44,000 features, geom=geom, type=LINESTRING, srs=4326
  admin3: 1,627 features, geom=geom, type=MULTIPOLYGON, srs=4326
```

**Output:**

- Total number of layers
- Per-layer: feature count, geometry column, geometry type, SRID

---

### `geopkg validate`

Validate geometry health in a GeoPackage.

```bash
geopkg validate <file.gpkg> [--srid SRID] [--layers LAYERS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--srid SRID` | Expected SRID to check against (e.g., 4326) |
| `--layers LAYERS` | Comma-separated list of layer names to validate |

**Examples:**

```bash
# Validate all layers
$ geopkg validate data.gpkg

# Validate with SRID check
$ geopkg validate data.gpkg --srid 4326

# Validate specific layers
$ geopkg validate data.gpkg --layers buildings,roads
```

**Output:**

```
GeoPackage: data.gpkg
3 layers, 125,000 features, 0 warnings
  buildings: 80,000 features, SRID=4326, OK  bbox=[35.4911,33.8229,35.4954,33.8263]
  roads: 44,000 features, SRID=4326, OK  bbox=[35.5088,33.8686,35.5117,33.8718]
  admin3: 1,627 features, SRID=4326, OK  bbox=[35.1035,33.0550,36.6229,34.6921]
```

**Exit codes:**

- `0`: All layers valid
- `1`: Warnings found (invalid geometries, SRID mismatches, etc.)

---

### `geopkg count`

Count features per zone using spatial joins.

```bash
geopkg count <file.gpkg> --features FEATURES --zones ZONES
```

**Options:**

| Option | Description |
|--------|-------------|
| `--features FEATURES` | Layer containing features to count (e.g., buildings) |
| `--zones ZONES` | Layer containing zone polygons (e.g., admin3) |

**Example:**

```bash
$ geopkg count data.gpkg --features buildings --zones admin3

     zone_id       count
------------  ----------
         853      15,458
         970       7,853
         885       6,709
          92       5,012
         923       4,940
         ...

Total: 499,787 features across 1,627 zones (7.7s)
```

**Output:**

- Sorted table of zone_id and feature count (descending by count)
- Total features and zones
- Execution time

**Notes:**

- Uses rtree spatial indexing for performance
- Automatically creates rtree index if missing (first run)
- Results are sorted by count (descending)

---

### `geopkg import`

Import a GeoJSON or Shapefile into a GeoPackage (creates the GeoPackage if missing).

```bash
geopkg import <input.geojson|.shp> --output <file.gpkg> --layer <name> [--geom-col COL] [--srid SRID]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--output` | Output GeoPackage path (created if it does not exist) |
| `--layer` | Layer name for the imported data |
| `--geom-col COL` | Geometry column name (default: `geom`) |
| `--srid SRID` | SRID assigned to the imported geometries (default: 4326) |

**Example:**

```bash
$ geopkg import inbox/latest_survey.geojson --output survey_data.gpkg --layer surveys

Imported 120 features into survey_data.gpkg -> surveys (0.0s)
```

**Notes:**

- GeoJSON input is always WGS84 (EPSG:4326 per RFC 7946)
- An existing layer with the same name is replaced
- Shapefile input requires the optional extra: `pip install geopackage-toolkit[convert]`

---

### `geopkg export`

Export a GeoPackage layer to GeoJSON or Shapefile.

```bash
geopkg export <file.gpkg> --layer LAYER --format {geojson,shapefile} --output PATH [--geom-col COL]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--layer LAYER` | Layer to export |
| `--format` | Output format: `geojson` (pure Python) or `shapefile` (requires `[convert]` extra) |
| `--output PATH` | Output file path (missing directories are created automatically) |
| `--geom-col COL` | Geometry column name (auto-detected if omitted) |

**Example:**

```bash
$ geopkg export survey_data.gpkg --layer clipped --format geojson --output out/clipped.geojson

Exported 54 features to out/clipped.geojson (0.0s)
```

---

### `geopkg buffer`

Buffer features by a distance and write the result to a new layer.

```bash
geopkg buffer <file.gpkg> --layer LAYER --distance N [--output NAME] [--no-attrs]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--layer LAYER` | Layer to buffer |
| `--distance N` | Buffer distance in CRS units (meters for projected CRS, degrees for EPSG:4326) |
| `--output NAME` | Output layer name (default: `buffered`) |
| `--no-attrs` | Exclude source attributes from the output layer |

**Example:**

```bash
$ geopkg buffer survey_data.gpkg --layer clipped --distance 0.001 --output buffers

Buffered 54 features -> buffers (0.0s)
```

# 0.001 degrees ≈ 100 m at EPSG:4326; use meters when the layer is in a projected CRS

---

### `geopkg clip`

Clip a source layer by a polygon layer, keeping only what falls inside.

```bash
geopkg clip <file.gpkg> --source LAYER --clip LAYER [--output NAME]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--source` | Source layer to clip |
| `--clip` | Clip layer (polygon boundary) |
| `--output NAME` | Output layer name (default: `clipped`) |

**Example:**

```bash
$ geopkg clip survey_data.gpkg --source surveys --clip project_boundary --output clipped

Clipped 54 features -> clipped (0.0s)
```

**Notes:**

- Source attributes are preserved
- Clip layer features are treated as one combined boundary

---

### `geopkg intersect`

Spatial intersection of two layers: keeps the overlapping geometry and attributes from both.

```bash
geopkg intersect <file.gpkg> --layer-a LAYER --layer-b LAYER [--output NAME]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--layer-a` | First input layer |
| `--layer-b` | Second input layer |
| `--output NAME` | Output layer name (default: `intersection`) |

**Example:**

```bash
$ geopkg intersect survey_data.gpkg --layer-a surveys --layer-b project_boundary --output points_in_boundary

Intersected 54 features -> points_in_boundary (0.0s)
```

**Notes:**

- Attributes from both layers are kept, prefixed `a_` and `b_`
- Unlike `clip`, both inputs contribute attributes (useful for overlay questions, e.g., parcels x flood zones)

---

### `geopkg pipeline`

Run a config-driven batch pipeline (JSON or YAML).

```bash
geopkg pipeline <config.yaml|config.json>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `config` | Path to pipeline config file (`.json`, `.yaml`, `.yml`) |

**Example:**

```bash
$ geopkg pipeline pipeline.yaml

Pipeline: pipeline.yaml -> processed.gpkg
  1. import     ok      6 features (2 file(s))
  2. clip       ok      6 features -> clipped
  3. buffer     ok      6 features -> buffered
  4. export     ok      6 features -> out/buffered.geojson
  5. validate   ok      valid
5/5 steps ok (1.8s)
Report: pipeline.report.json
```

**Exit codes:**

- `0`: All steps succeeded
- `1`: One or more steps failed (or the config is invalid)

**Notes:**

- One pipeline operates on one working GeoPackage (`gpkg` key in the config)
- Supported steps: `import`, `buffer`, `clip`, `intersect`, `export`, `validate`
- With the default `fail_fast: false`, all steps run regardless of earlier failures
- A JSON run report is written next to the config file by default
- YAML configs require the optional extra: `pip install geopackage-toolkit[pipeline]`
- See the [Pipeline Guide](guides/pipeline.md) for the full config reference

---

## Common Workflows

### Data Quality Check

```bash
# 1. Check what layers exist
geopkg info data.gpkg

# 2. Validate all layers (read-only: reports issues, never edits the file)
geopkg validate data.gpkg --srid 4326

# 3. Fix flagged issues in your GIS tool, then re-run to confirm
geopkg validate data.gpkg --srid 4326
```

### Spatial Analysis

```bash
# 1. Count buildings per district
geopkg count data.gpkg --features buildings --zones districts

# 2. Count POIs per district
geopkg count data.gpkg --features pois --zones districts

# 3. Compare results in a spreadsheet
```

### Prepare Survey Data for Delivery

```bash
# 1. Import the latest survey export into the working GeoPackage
geopkg import inbox/latest_survey.geojson --output survey_data.gpkg --layer surveys

# 2. Clip to the project boundary
geopkg clip survey_data.gpkg --source surveys --clip project_boundary --output clipped

# 3. Export the result for the client
geopkg export survey_data.gpkg --layer clipped --format geojson --output out/surveys.geojson
```

### Batch Processing

```bash
# Validate multiple files
for file in *.gpkg; do
    echo "Validating $file..."
    geopkg validate "$file" --srid 4326
done
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPATIALITE_DIR` | Path to SpatiaLite DLL directory (Windows) | `C:\spatialite` |
| `GPKG_TEST_DATA` | Path to test data for tests | (none) |

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | Validation warnings or command error |

## Tips

1. **Use `info` first** to understand the GeoPackage structure before running queries
2. **Always validate with `--srid`** to catch CRS mismatches
3. **The first `count` command is slower** because it builds the rtree index
4. **For multi-step workflows, use `geopkg pipeline`** — one config file, one command, a JSON run report, and CI-friendly exit codes
