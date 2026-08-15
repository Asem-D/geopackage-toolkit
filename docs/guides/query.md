# Spatial Query Guide

This guide covers the spatial query operations in geopackage-toolkit: counting features per zone, bounding box filtering, and point-in-polygon classification.

## Overview

All query functions use **rtree spatial indexing** for performance. GeoPackage stores rtree indexes natively (unlike SpatiaLite's virtual table), and this toolkit leverages them directly.

When you call `count_in_zones` or `bbox_filter`, the toolkit:

1. Checks if an rtree index exists for the feature table
2. If not, creates one automatically (first run only)
3. Uses the rtree for fast bounding box pre-filtering
4. Applies the precise spatial predicate (ST_Contains, etc.) for accuracy

This two-step approach (rtree + predicate) is orders of magnitude faster than a naive full-table scan.

## Counting Features Per Zone

The most common GIS operation: how many features fall inside each administrative zone?

### Basic Usage

```python
from geopkgtoolkit import connect, count_in_zones

con = connect("data.gpkg")
counts = count_in_zones(con, "buildings", "admin3")
```

Returns a list of `(zone_fid, count)` tuples:

```python
[(1, 893), (2, 2575), (3, 3077), ...]
```

### How It Works

For each zone polygon, the function:

1. Gets the zone's bounding box via SQL (`ST_MinX`, `ST_MaxX`, etc.)
2. Queries the feature rtree for features whose bbox intersects the zone bbox
3. Applies `ST_Contains(zone_geom, feature_geom)` to the candidates
4. Counts the matches

This is why the first run may be slower (building the rtree index) but subsequent runs are fast.

### Explicit Geometry Column Names

If your geometry columns are not named `geom`:

```python
counts = count_in_zones(
    con,
    feature_table="osm_buildings",
    zone_table="admin_boundaries",
    feature_geom="geometry",
    zone_geom="geometry",
    zone_id="adm3_code",
)
```

### Disabling Index Creation

If you want to manage indexes yourself:

```python
counts = count_in_zones(
    con,
    "buildings",
    "admin3",
    ensure_index=False,
)
```

### Processing Results

```python
# Sort by count (descending)
counts.sort(key=lambda x: x[1], reverse=True)

# Print top 10
print(f"{'Zone':>8}  {'Count':>10}")
print(f"{'-'*8}  {'-'*10}")
for zone_id, count in counts[:10]:
    print(f"{zone_id:>8}  {count:>10,}")

# Calculate statistics
total = sum(c for _, c in counts)
zones_with_features = sum(1 for _, c in counts if c > 0)
print(f"\nTotal: {total:,} features in {zones_with_features} zones")
```

## Bounding Box Filtering

Find features within a geographic extent.

### Basic Usage

```python
from geopkgtoolkit import bbox_filter

# (minx, miny, maxx, maxy) in WGS84
bbox = (35.48, 33.87, 35.52, 33.90)
fids = bbox_filter(con, "buildings", bbox)
```

Returns a list of feature IDs (fid values):

```python
[1234, 5678, 9012, ...]
```

### Getting Full Feature Data

Combine with SQL to get feature attributes:

```python
fids = bbox_filter(con, "buildings", bbox)

if fids:
    placeholders = ",".join("?" * len(fids))
    features = con.execute(
        f"SELECT * FROM buildings WHERE fid IN ({placeholders})",
        fids,
    ).fetchall()
```

### Performance

Bbox filtering with rtree is extremely fast:

| Features | Time |
|----------|------|
| 10,000 | <0.1s |
| 100,000 | <0.5s |
| 500,000 | <1s |
| 1,000,000 | <2s |

The rtree index reduces the search space from millions to hundreds of candidates.

## Point-in-Polygon Classification

Classify points into containing polygons.

### Basic Usage

```python
from geopkgtoolkit import points_in_polygons

result = points_in_polygons(con, "pois", "districts")
```

Returns a list of `(point_fid, polygon_fid_or_None)` tuples:

```python
[(1, 42), (2, 17), (3, None), (4, 42), ...]
```

Points not inside any polygon have `None` as the polygon ID.

### Processing Results

```python
# Count points per polygon
from collections import Counter

polygon_counts = Counter(pid for _, pid in result if pid is not None)
for polygon_id, count in polygon_counts.most_common(5):
    print(f"District {polygon_id}: {count} POIs")

# Find unclassified points
unclassified = [fid for fid, pid in result if pid is None]
print(f"{len(unclassified)} points outside all districts")
```

## Performance Comparison

| Operation | Without rtree | With rtree | Speedup |
|-----------|---------------|------------|---------|
| count_in_zones (500k x 1.6k) | >10 minutes | ~8 seconds | 75x |
| bbox_filter (500k) | >30 seconds | <1 second | 30x |

The rtree index is the key performance optimization. Without it, every query requires a full table scan with O(n) spatial predicate evaluations.

## Auto-Indexing

All query functions automatically create rtree indexes when missing:

```python
# First call creates the index (slower)
counts = count_in_zones(con, "buildings", "admin3")  # ~30s

# Subsequent calls use the index (fast)
counts = count_in_zones(con, "buildings", "admin3")  # ~8s
```

The rtree index is stored in the GeoPackage as `rtree_{table}_{geom_column}` and persists across sessions.

## Common Patterns

### Spatial Join with Attributes

Combine rtree queries with SQL to get full attribute data:

```python
from geopkgtoolkit import count_in_zones

# Get counts
counts = count_in_zones(con, "buildings", "admin3")

# Get zone names
zones = con.execute("SELECT fid, name FROM admin3").fetchall()
zone_names = {fid: name for fid, name in zones}

# Print with names
for zone_id, count in sorted(counts, key=lambda x: x[1], reverse=True)[:10]:
    name = zone_names.get(zone_id, "Unknown")
    print(f"{name}: {count:,} buildings")
```

### Multi-Layer Analysis

Analyze multiple feature layers against the same zones:

```python
layers = ["buildings", "roads", "pois"]
for layer in layers:
    counts = count_in_zones(con, layer, "admin3")
    total = sum(c for _, c in counts)
    print(f"{layer}: {total:,} features")
```

### Custom Zone Queries

Use SQL to create custom zones on the fly:

```python
# Create a buffer around a point
con.execute("""
    CREATE TEMPORARY TABLE search_area AS
    SELECT ST_Buffer(ST_MakePoint(35.5, 33.9), 0.01) AS geom
""")

# Count buildings in the search area
counts = count_in_zones(con, "buildings", "search_area")
```

## Troubleshooting

### "No rtree index found"

The toolkit should auto-create indexes. If you see this error, check:

1. The table has a geometry column
2. The GeoPackage is writable (not read-only)
3. SpatiaLite is loaded correctly

### Slow Performance

If queries are slow:

1. Check if rtree indexes exist: `SELECT * FROM rtree_buildings_geom`
2. Create them manually: `SELECT CreateSpatialIndex('buildings', 'geom')`
3. Consider running `ANALYZE` on the database

### Memory Issues

For very large datasets (>10M features), consider:

1. Filtering to a bbox first
2. Using `WHERE` clauses to reduce the feature set
3. Processing in chunks

## Next Steps

- [Cookbook](../cookbook.md) - Real-world recipes
- [API Reference](../api/query.md) - Complete function documentation
