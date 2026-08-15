# Quick Start

This guide walks you through validating and querying a GeoPackage file in under 5 minutes.

## Step 1: Connect to a GeoPackage

```python
from geopkgtoolkit import connect

con = connect("data.gpkg")
```

This opens the GeoPackage with SpatiaLite loaded and ready for spatial queries.

## Step 2: List Available Layers

```python
from geopkgtoolkit._spatialite import list_layers

layers = list_layers(con)
for layer in layers:
    print(f"{layer['table_name']}: {layer['geometry_type']}")
```

Example output:

```
buildings: MULTIPOLYGON
roads: LINESTRING
admin3: MULTIPOLYGON
```

## Step 3: Validate Geometry Health

Check for problems before they waste your time:

```python
from geopkgtoolkit import validate_layers

report = validate_layers("data.gpkg", expected_srid=4326)
print(report.summary())
```

Example output:

```
GeoPackage: data.gpkg
3 layers, 125,000 features, 0 warnings
  buildings: 80,000 features, SRID=4326, OK  bbox=[35.4911,33.8229,35.4954,33.8263]
  roads: 44,000 features, SRID=4326, OK  bbox=[35.5088,33.8686,35.5117,33.8718]
  admin3: 1,627 features, SRID=4326, OK  bbox=[35.1035,33.0550,36.6229,34.6921]
```

## Step 4: Count Features Per Zone

The most common GIS operation: how many features fall inside each administrative zone?

```python
from geopkgtoolkit import count_in_zones

counts = count_in_zones(con, "buildings", "admin3")

# Sort by count (descending)
counts.sort(key=lambda x: x[1], reverse=True)

# Print top 5
for zone_id, count in counts[:5]:
    print(f"Zone {zone_id}: {count} buildings")
```

Output:

```
Zone 853: 15,458 buildings
Zone 970: 7,853 buildings
Zone 885: 6,709 buildings
Zone 92: 5,012 buildings
Zone 923: 4,940 buildings
```

## Step 5: Filter by Bounding Box

Find features within a geographic extent:

```python
from geopkgtoolkit import bbox_filter

# Beirut city center (approximate)
bbox = (35.48, 33.87, 35.52, 33.90)
fids = bbox_filter(con, "buildings", bbox)
print(f"{len(fids)} buildings in Beirut center")
```

## Step 6: Point-in-Polygon Classification

Classify points into containing polygons:

```python
from geopkgtoolkit import points_in_polygons

result = points_in_polygons(con, "populated_places", "admin3")

# result is [(point_fid, polygon_fid_or_None), ...]
for point_fid, polygon_id in result[:5]:
    print(f"Place {point_fid} is in admin3 zone {polygon_id}")
```

## Using the CLI

For quick operations without writing Python:

```bash
# Show layer info
geopkg info data.gpkg

# Validate with SRID check
geopkg validate data.gpkg --srid 4326

# Count buildings per zone
geopkg count data.gpkg --features buildings --zones admin3
```

## What's Next?

- [Validation Guide](guides/validate.md) - Deep dive into geometry validation
- [Query Guide](guides/query.md) - Spatial joins, bbox filters, and more
- [Cookbook](cookbook.md) - Real-world recipes and patterns
- [API Reference](api/connect.md) - Complete function documentation
