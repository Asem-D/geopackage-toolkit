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

## Common Workflows

### Data Quality Check

```bash
# 1. Check what layers exist
geopkg info data.gpkg

# 2. Validate all layers
geopkg validate data.gpkg --srid 4326

# 3. Fix any issues, then re-validate
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
4. **Combine with other tools** for complex workflows (e.g., pipe to CSV with `--output`)
