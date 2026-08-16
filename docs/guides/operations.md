# Spatial Operations Guide

This guide covers the spatial operations in geopackage-toolkit: buffer, clip, and intersect. All operations create new layers non-destructively.

## Buffer

Creates polygon buffers around all features at a specified distance. Works with points, lines, or polygons.

### Basic Usage

```python
from geopkgtoolkit import connect, buffer

con = connect("data.gpkg")
buffer(con, "buildings", 100, "buildings_100m")
```

!!! warning
    Buffer distance is in the layer's CRS units. Use a projected CRS (e.g., EPSG:3857) for metric buffers. WGS84 (EPSG:4326) uses degrees.

### Options

```python
# Buffer without copying source attributes
buffer(con, "buildings", 100, "buildings_buffer", keep_attrs=False)

# Negative buffer (inward shrink for polygons)
buffer(con, "polygons", -10, "shrunk_polygons")
```

### Use Cases

- **Proximity analysis**: Find features within N meters of a road
- **Safety zones**: Create exclusion zones around hazards
- **Simplification**: Expand small polygons for visibility on maps

## Clip

Clips source features to the boundary of a clip layer. Only the portions inside the clip boundary are kept.

### Basic Usage

```python
from geopkgtoolkit import clip

# Clip buildings to district boundaries
clip(con, "buildings", "districts", "buildings_in_districts")
```

### Attribute Control

```python
# Keep only source attributes (default)
clip(con, "buildings", "districts", "result", keep_attrs="a")

# Keep only clip layer attributes
clip(con, "buildings", "districts", "result", keep_attrs="b")

# Keep attributes from both layers (prefixed)
clip(con, "buildings", "districts", "result", keep_attrs="both")

# Geometry only, no attributes
clip(con, "buildings", "districts", "result", keep_attrs="none")
```

### Use Cases

- **Masking**: Show data only within an area of interest
- **Extraction**: Pull out features for a specific region
- **Data preparation**: Clip national datasets to a study area

## Intersect

Computes the geometric intersection of two layers. Produces new geometries from the overlapping portions.

### Basic Usage

```python
from geopkgtoolkit import intersect

# Find buildings in flood zones
intersect(con, "buildings", "flood_zones", "buildings_in_flood")
```

### Attribute Control

```python
# Keep attributes from both layers (prefixed: a_, b_)
intersect(con, "buildings", "flood_zones", "result", keep_attrs="both")

# Keep only first layer attributes
intersect(con, "buildings", "flood_zones", "result", keep_attrs="a")
```

### Use Cases

- **Risk assessment**: Buildings in flood zones, schools near highways
- **Land use analysis**: Intersection of zoning and ownership
- **Network analysis**: Road segments within administrative boundaries

## Performance Notes

All operations use SpatiaLite SQL with bounding box pre-filtering where possible. Performance characteristics:

| Operation | Time (100k features) | Notes |
|-----------|---------------------|-------|
| `buffer` | ~2-5 seconds | Depends on geometry complexity |
| `clip` | ~1-3 seconds | Spatial join with intersection |
| `intersect` | ~1-3 seconds | Spatial join with intersection |

Output layers are registered in GeoPackage metadata (`gpkg_contents`, `gpkg_geometry_columns`) and are immediately available for further operations.

## Non-Destructive Design

All operations create new layers. Original data is never modified:

```python
buffer(con, "buildings", 100, "buildings_100m")  # Creates new layer
clip(con, "buildings", "districts", "clipped")    # Creates new layer
intersect(con, "a", "b", "result")                # Creates new layer
```

You can safely run operations multiple times with different output names.
