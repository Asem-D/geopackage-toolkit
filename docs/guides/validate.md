# Validation Guide

Geometry validation is the first line of defense against wasted time. Bad geometries cause cryptic errors in spatial queries, broken visualizations, and silent data corruption. This guide covers how to use geopackage-toolkit's validation to catch problems early.

## Why Validate?

Geometry problems are common in real-world GIS data:

- **NULL geometries**: Features with no spatial data
- **Empty geometries**: Geometry objects that contain no coordinates
- **Invalid geometries**: Self-intersecting polygons, wrong ring orientation, degenerate coordinates
- **SRID mismatches**: Data in the wrong coordinate reference system
- **Corrupt data**: Truncated geometries, NaN coordinates

These problems often go unnoticed until they cause failures downstream. Validation catches them early.

## Basic Validation

### Validate All Layers

```python
from geopkgtoolkit import validate_layers

report = validate_layers("data.gpkg", expected_srid=4326)
print(report.summary())
```

This checks every layer in the GeoPackage and produces a report with:

- Feature counts per layer
- NULL geometry counts
- Empty geometry counts
- Invalid geometry counts
- SRID verification
- Bounding box information
- Warnings for any issues found

### Validate Specific Layers

Only check certain layers:

```python
report = validate_layers(
    "data.gpkg",
    expected_srid=4326,
    layers=["buildings", "roads"],
)
```

### Validate a Single Layer

```python
from geopkgtoolkit import validate_layer
from geopkgtoolkit._spatialite import connect

con = connect("data.gpkg")
report = validate_layer(con, "buildings", expected_srid=4326)

print(f"Features: {report.feature_count:,}")
print(f"Invalid: {report.invalid_count}")
print(f"Warnings: {report.warnings}")
```

## Understanding the Report

### LayerReport Fields

| Field | Type | Description |
|-------|------|-------------|
| `table_name` | str | Layer name |
| `geometry_column` | str | Geometry column name (usually `geom`) |
| `geometry_type` | str | MULTIPOLYGON, LINESTRING, POINT, etc. |
| `feature_count` | int | Total number of features |
| `srid` | int | Spatial Reference System ID |
| `null_count` | int | Features with NULL geometry |
| `empty_count` | int | Features with empty geometry |
| `invalid_count` | int | Features with invalid geometry |
| `bbox` | tuple | (minx, miny, maxx, maxy) of first feature |
| `warnings` | list | Human-readable warning messages |

### GpkgReport Fields

| Field | Type | Description |
|-------|------|-------------|
| `path` | str | GeoPackage file path |
| `layers` | list | List of LayerReport objects |
| `is_valid` | bool | True if no warnings across all layers |
| `total_features` | int | Sum of all feature counts |
| `total_warnings` | int | Sum of all warnings |

### Checking Validity

```python
report = validate_layers("data.gpkg", expected_srid=4326)

if report.is_valid:
    print("All layers passed validation")
else:
    print(f"Found {report.total_warnings} warnings")
    for layer in report.layers:
        if not layer.is_valid:
            print(f"  {layer.table_name}:")
            for warning in layer.warnings:
                print(f"    - {warning}")
```

## Common Issues and Fixes

### NULL Geometries

**Symptom**: `null_count > 0`

**Cause**: Features imported without spatial data, or failed geometry operations.

**Fix**:

```sql
-- Find features with NULL geometry
SELECT fid FROM buildings WHERE geom IS NULL;

-- Remove them
DELETE FROM buildings WHERE geom IS NULL;
```

### Invalid Geometries (Self-Intersections)

**Symptom**: `invalid_count > 0`

**Cause**: Polygon boundaries that cross themselves. Common in data converted from other formats.

**Fix**:

```sql
-- Fix self-intersecting polygons
UPDATE buildings SET geom = ST_MakeValid(geom)
WHERE NOT ST_IsValid(geom);
```

!!! warning
    `ST_MakeValid` may change the geometry significantly. Review the results.

### SRID Mismatch

**Symptom**: `SRID mismatch: got 4326, expected 3857`

**Cause**: Data in the wrong coordinate reference system.

**Fix**: This is usually a configuration error, not a data error. Verify which SRID your data actually uses and pass the correct `expected_srid`.

### Empty Geometries

**Symptom**: `empty_count > 0`

**Cause**: Geometry objects with no coordinates. Often caused by failed clipping or intersection operations.

**Fix**:

```sql
DELETE FROM buildings WHERE ST_IsEmpty(geom);
```

## Integrating Validation into Workflows

### Pre-Processing Validation

Always validate before expensive operations:

```python
from geopkgtoolkit import validate_layers, count_in_zones

# Validate first
report = validate_layers("data.gpkg", expected_srid=4326)
if not report.is_valid:
    print("Fix geometry issues before running spatial queries")
    # Show details
    print(report.summary())
    exit(1)

# Safe to proceed
con = connect("data.gpkg")
counts = count_in_zones(con, "buildings", "admin3")
```

### CI/CD Validation

Add validation to your data pipeline:

```python
import sys
from geopkgtoolkit import validate_layers

def validate_data(gpkg_path):
    report = validate_layers(gpkg_path, expected_srid=4326)
    if not report.is_valid:
        print(f"Validation failed: {report.total_warnings} warnings")
        print(report.summary())
        sys.exit(1)
    print(f"Validation passed: {report.total_features:,} features")
    return report

if __name__ == "__main__":
    validate_data("output.gpkg")
```

### Batch Validation

Validate multiple files:

```python
from pathlib import Path
from geopkgtoolkit import validate_layers

for gpkg in Path("data/").glob("*.gpkg"):
    print(f"\nValidating {gpkg.name}...")
    report = validate_layers(str(gpkg), expected_srid=4326)
    status = "PASS" if report.is_valid else "FAIL"
    print(f"  {status}: {report.total_features:,} features, {report.total_warnings} warnings")
```

## Performance Notes

Validation is fast because it uses SQL aggregation, not Python loops:

- **500k features**: ~2 seconds
- **1M features**: ~4 seconds
- **Multiple layers**: Parallel-safe (each layer is independent)

The bottleneck is usually `ST_IsValid()` for complex geometries. Simple geometries (points, lines) validate almost instantly.

## Next Steps

- [Query Guide](query.md) - Spatial joins and bbox filtering
- [API Reference](../api/validate.md) - Complete function documentation
- [Cookbook](../cookbook.md) - Real-world recipes
