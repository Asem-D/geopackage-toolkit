# Cookbook

Real-world recipes for common GIS operations using geopackage-toolkit.

## Recipe 1: Pre-Flight Check Before Publishing

Before sharing a GeoPackage with colleagues or clients, validate it:

```python
from geopkgtoolkit import validate_layers

def preflight_check(gpkg_path, expected_srid=4326):
    """Validate a GeoPackage before publishing."""
    report = validate_layers(gpkg_path, expected_srid=expected_srid)
    
    if report.is_valid:
        print(f"PASSED: {report.total_features:,} features across {len(report.layers)} layers")
        return True
    
    print(f"FAILED: {report.total_warnings} warnings found")
    for layer in report.layers:
        if not layer.is_valid:
            print(f"\n  {layer.table_name}:")
            for warning in layer.warnings:
                print(f"    - {warning}")
    return False

# Usage
preflight_check("mashriq.gpkg")
```

## Recipe 2: Building Density Heatmap

Calculate building density per administrative zone:

```python
from geopkgtoolkit import connect, count_in_zones

con = connect("mashriq.gpkg")

# Count buildings per zone
counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")

# Get zone names and areas
zones = con.execute("""
    SELECT fid, ADM3_EN, ST_Area(geom) AS area_km2
    FROM lbn_adm3
""").fetchall()

zone_data = {fid: (name, area) for fid, name, area in zones}

# Calculate density
densities = []
for zone_id, count in counts:
    if zone_id in zone_data and count > 0:
        name, area = zone_data[zone_id]
        density = count / area if area > 0 else 0
        densities.append((name, count, area, density))

# Sort by density (descending)
densities.sort(key=lambda x: x[3], reverse=True)

# Print results
print(f"{'District':<30} {'Buildings':>10} {'Area (km2)':>12} {'Density':>10}")
print("-" * 65)
for name, count, area, density in densities[:10]:
    print(f"{name:<30} {count:>10,} {area:>12.2f} {density:>10.1f}")
```

## Recipe 3: Spatial Join with Attribute Data

Combine spatial counting with attribute data for rich analysis:

```python
from geopkgtoolkit import connect, count_in_zones

con = connect("mashriq.gpkg")

# Spatial join: count buildings per district
counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")
count_dict = dict(counts)

# Get district attributes
districts = con.execute("""
    SELECT fid, ADM3_EN, ADM3_AR, ADM2_EN
    FROM lbn_adm3
""").fetchall()

# Combine results
print(f"{'District':<25} {'Governorate':<20} {'Buildings':>10}")
print("-" * 57)
for fid, name_en, name_ar, governorate in districts:
    count = count_dict.get(fid, 0)
    if count > 0:
        print(f"{name_en:<25} {governorate:<20} {count:>10,}")
```

## Recipe 4: Multi-Layer Analysis

Analyze multiple feature layers against the same zones:

```python
from geopkgtoolkit import connect, count_in_zones

con = connect("mashriq.gpkg")

# Define layers to analyze
layers = {
    "buildings": "OSM_Buildings",
    "roads": "OSM_roads",
    "places": "Populated Places",
}

# Count each layer per zone
results = {}
for layer_name, table_name in layers.items():
    counts = count_in_zones(con, table_name, "lbn_adm3")
    results[layer_name] = dict(counts)

# Get zone names
zones = con.execute("SELECT fid, ADM3_EN FROM lbn_adm3").fetchall()
zone_names = {fid: name for fid, name in zones}

# Print comparison table
print(f"{'District':<25} {'Buildings':>10} {'Roads':>10} {'Places':>10}")
print("-" * 57)
for fid, name in sorted(zone_names.items(), key=lambda x: x[1]):
    b = results["buildings"].get(fid, 0)
    r = results["roads"].get(fid, 0)
    p = results["places"].get(fid, 0)
    if b > 0 or r > 0 or p > 0:
        print(f"{name:<25} {b:>10,} {r:>10,} {p:>10,}")
```

## Recipe 5: Export Counts to CSV

Export spatial join results to CSV for use in Excel or other tools:

```python
import csv
from geopkgtoolkit import connect, count_in_zones

con = connect("mashriq.gpkg")

# Count buildings per zone
counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")
count_dict = dict(counts)

# Get zone data
zones = con.execute("""
    SELECT fid, ADM3_EN, ADM3_AR, ADM2_EN, ADM1_EN
    FROM lbn_adm3
""").fetchall()

# Write CSV
with open("building_counts.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["zone_id", "name_en", "name_ar", "governorate", "region", "building_count"])
    
    for fid, name_en, name_ar, governorate, region in zones:
        count = count_dict.get(fid, 0)
        writer.writerow([fid, name_en, name_ar, governorate, region, count])

print(f"Exported {len(zones)} zones to building_counts.csv")
```

## Recipe 6: Batch Validation with Report

Validate multiple GeoPackage files and generate a summary report:

```python
from pathlib import Path
from geopkgtoolkit import validate_layers

def batch_validate(directory, expected_srid=4326):
    """Validate all GeoPackage files in a directory."""
    gpkg_files = list(Path(directory).glob("*.gpkg"))
    
    if not gpkg_files:
        print(f"No .gpkg files found in {directory}")
        return
    
    print(f"Validating {len(gpkg_files)} GeoPackage files...\n")
    
    results = []
    for gpkg in sorted(gpkg_files):
        report = validate_layers(str(gpkg), expected_srid=expected_srid)
        status = "PASS" if report.is_valid else "FAIL"
        results.append((gpkg.name, status, report))
        
        print(f"  {status}  {gpkg.name}")
        print(f"       {report.total_features:,} features, {report.total_warnings} warnings")
        
        if not report.is_valid:
            for layer in report.layers:
                if not layer.is_valid:
                    for warning in layer.warnings:
                        print(f"         {layer.table_name}: {warning}")
    
    # Summary
    passed = sum(1 for _, status, _ in results if status == "PASS")
    failed = len(results) - passed
    print(f"\nSummary: {passed} passed, {failed} failed out of {len(results)} files")
    
    return results

# Usage
batch_validate("E:/Data/GIS/Mashreq/")
```

## Recipe 7: Quick Map Data Prep

Prepare data for mapping by filtering and counting:

```python
from geopkgtoolkit import connect, count_in_zones, bbox_filter

con = connect("mashriq.gpkg")

# Beirut area bbox
beirut_bbox = (35.45, 33.85, 35.55, 33.92)

# Get buildings in Beirut
beirut_fids = bbox_filter(con, "OSM_Buildings", beirut_bbox)
print(f"Buildings in Beirut: {len(beirut_fids):,}")

# Count by district (only Beirut districts)
counts = count_in_zones(con, "OSM_Buildings", "lbn_adm3")
count_dict = dict(counts)

# Get Beirut districts
districts = con.execute("""
    SELECT fid, ADM3_EN 
    FROM lbn_adm3 
    WHERE fid IN (1, 2, 3, 4, 5)  -- Beirut districts
""").fetchall()

for fid, name in districts:
    count = count_dict.get(fid, 0)
    print(f"  {name}: {count:,} buildings")
```

## Recipe 8: Data Quality Dashboard

Create a comprehensive quality report:

```python
from geopkgtoolkit import validate_layers, connect
from geopkgtoolkit._spatialite import list_layers

def quality_dashboard(gpkg_path):
    """Generate a comprehensive data quality dashboard."""
    con = connect(gpkg_path)
    
    print(f"Data Quality Dashboard: {gpkg_path}")
    print("=" * 60)
    
    # Layer overview
    layers = list_layers(con)
    print(f"\nLayers: {len(layers)}")
    
    # Validation
    report = validate_layers(gpkg_path, expected_srid=4326)
    print(f"Validation: {'PASS' if report.is_valid else 'FAIL'}")
    print(f"Total Features: {report.total_features:,}")
    
    # Per-layer stats
    print("\nPer-Layer Statistics:")
    print("-" * 60)
    
    for layer in layers:
        table = layer["table_name"]
        
        # Basic stats
        count = con.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        geom_count = con.execute(
            f"SELECT COUNT(*) FROM [{table}] WHERE [{layer['column_name']}] IS NOT NULL"
        ).fetchone()[0]
        
        # Geometry type
        geom_type = layer["geometry_type"]
        srid = layer["srs_id"]
        
        print(f"\n  {table}:")
        print(f"    Features: {count:,}")
        print(f"    With Geometry: {geom_count:,}")
        print(f"    Type: {geom_type}")
        print(f"    SRID: {srid}")
        
        # Validation warnings
        for lr in report.layers:
            if lr.table_name == table and lr.warnings:
                for w in lr.warnings:
                    print(f"    WARNING: {w}")
    
    con.close()
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Summary: {report.total_features:,} features, {report.total_warnings} warnings")
    
    return report

# Usage
quality_dashboard("mashriq.gpkg")
```

## Recipe 9: Compare Two GeoPackages

Compare the same layers across two GeoPackage files:

```python
from geopkgtoolkit import validate_layers

def compare_gpkg(path1, path2, layers=None):
    """Compare two GeoPackage files."""
    report1 = validate_layers(path1, layers=layers)
    report2 = validate_layers(path2, layers=layers)
    
    print(f"Comparing:")
    print(f"  File 1: {path1}")
    print(f"  File 2: {path2}")
    print()
    
    # Build lookup dicts
    layers1 = {lr.table_name: lr for lr in report1.layers}
    layers2 = {lr.table_name: lr for lr in report2.layers}
    
    # Compare
    all_layers = sorted(set(list(layers1.keys()) + list(layers2.keys())))
    
    print(f"{'Layer':<25} {'File 1':>10} {'File 2':>10} {'Diff':>10}")
    print("-" * 57)
    
    for layer in all_layers:
        count1 = layers1[layer].feature_count if layer in layers1 else 0
        count2 = layers2[layer].feature_count if layer in layers2 else 0
        diff = count2 - count1
        
        print(f"{layer:<25} {count1:>10,} {count2:>10,} {diff:>+10,}")

# Usage
compare_gpkg("mashriq_old.gpkg", "mashriq_new.gpkg")
```

## Recipe 10: Validate and Fix

Validate, identify issues, and apply fixes:

```python
from geopkgtoolkit import validate_layers, connect

def validate_and_fix(gpkg_path):
    """Validate and fix geometry issues."""
    # Validate
    report = validate_layers(gpkg_path)
    
    if report.is_valid:
        print("No issues found")
        return
    
    print(f"Found {report.total_warnings} warnings:")
    print(report.summary())
    
    # Connect for fixes
    con = connect(gpkg_path)
    
    for layer in report.layers:
        if layer.invalid_count > 0:
            print(f"\nFixing {layer.table_name}...")
            
            # Fix invalid geometries
            fixed = con.execute(f"""
                UPDATE [{layer.table_name}]
                SET [{layer.geometry_column}] = ST_MakeValid([{layer.geometry_column}])
                WHERE NOT ST_IsValid([{layer.geometry_column}])
            """).rowcount
            
            print(f"  Fixed {fixed} invalid geometries")
        
        if layer.null_count > 0:
            print(f"\nRemoving NULL geometries from {layer.table_name}...")
            
            removed = con.execute(f"""
                DELETE FROM [{layer.table_name}]
                WHERE [{layer.geometry_column}] IS NULL
            """).rowcount
            
            print(f"  Removed {removed} features with NULL geometry")
    
    con.commit()
    con.close()
    
    # Re-validate
    print("\nRe-validating...")
    report = validate_layers(gpkg_path)
    print(f"Result: {'PASS' if report.is_valid else 'FAIL'}")
    
    return report

# Usage
validate_and_fix("problematic_data.gpkg")
```

## Recipe 11: Flood-Risk Screening

Which buildings fall inside a riparian buffer and the flood plain? Chain the spatial operations and export the result for the web team:

```python
from geopkgtoolkit import connect, buffer, clip, intersect, export_geojson

con = connect("mashriq.gpkg")

# Buffer the river (distance in CRS units; use a projected CRS for meters)
buffer(con, "rivers", 100, "riparian_zone")

# Keep buildings inside the study area only
clip(con, "OSM_Buildings", "study_area", "bldgs_in_area")

# Buildings that are both inside the study area and in the flood zone
intersect(con, "bldgs_in_area", "flood_zones", "at_risk")

# Export for MapLibre/Leaflet (pure Python, no extra dependencies)
export_geojson(con, "at_risk", "at_risk.geojson")

con.close()
```

Each operation creates a new layer in the same GeoPackage, so the originals stay untouched. Preview the results with `geopkg info mashriq.gpkg`.

## Recipe 12: One-Command Data Intake QC

Before a client GeoPackage enters your workflow, check it from the terminal:

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

Exit code `1` on warnings, `0` when clean, so it drops straight into shell checks or CI:

```bash
geopkg validate client_data.gpkg --srid 4326 || echo "Fix data before loading"
```

## Recipe 13: Nightly Batch Pipeline

Pull the latest survey export, clip it to the project boundary, and publish the result for the dashboard. One config file, one command:

`pipeline.yaml`:

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
# 3/3 steps ok (1.8s)
```

Exit code `0` means the dashboard data is fresh. Failed steps are recorded in the JSON run report (`pipeline.report.json`) instead of silently producing stale output. Schedule it with cron, Task Scheduler, or GitHub Actions; see the [Pipeline Guide](guides/pipeline.md) for the full config reference.
