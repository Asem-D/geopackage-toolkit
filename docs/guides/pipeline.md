# Pipeline Guide

The pipeline module runs a sequence of processing steps defined in a single config file. One pipeline operates on one working GeoPackage: import data in, run spatial operations, export results out.

## Quick Start

Create a config file (`pipeline.yaml`):

```yaml
gpkg: processed.gpkg
fail_fast: false
steps:
  - step: import
    input: "data/*.geojson"       # glob or single path
  - step: clip
    source: buildings
    clip: districts
    output: clipped
  - step: buffer
    layer: clipped
    distance: 100                 # CRS units
    output: buffered
  - step: export
    layer: buffered
    format: geojson
    output: out/buffered.geojson
  - step: validate
    srid: 4326
```

Run it:

```bash
geopkg pipeline pipeline.yaml
```

Output:

```
Pipeline: pipeline.yaml -> processed.gpkg
  1. import     ok      6 features (2 file(s))
  2. clip       ok      6 features -> clipped
  3. buffer     ok      6 features -> buffered
  4. export     ok      6 features -> out/buffered.geojson
  5. validate   ok      valid
5/5 steps ok (1.8s)
Report: pipeline.report.json
```

A JSON run report is written next to the config file (`pipeline.report.json`), or override with a `report:` key in the config.

## Config Format

JSON works out of the box (stdlib). YAML requires the optional extra:

```bash
pip install geopackage-toolkit[pipeline]
```

| Key | Required | Description |
|---|---|---|
| `gpkg` | yes | Working GeoPackage path (created by the first `import` step if missing) |
| `steps` | yes | Ordered list of steps |
| `fail_fast` | no | Stop at first failed step (default `false`) |
| `report` | no | Run report path (default `<config>.report.json`) |

## Step Reference

### `import`

Import GeoJSON or Shapefile files into the working GeoPackage.

```yaml
- step: import
  input: "data/*.geojson"   # single path or glob
  layer: buildings          # optional: fixed layer name (single file)
  geom_col: geom            # optional (default: geom)
  srid: 4326                # optional (default: 4326)
```

Without `layer`, the layer name is derived from each file's stem (`parcels.geojson` -> layer `parcels`), so globs import one layer per file.

### `buffer`

```yaml
- step: buffer
  layer: buildings
  distance: 100             # CRS units; negative = inward on polygons
  output: buffered          # output layer name (default: buffered)
```

### `clip`

```yaml
- step: clip
  source: buildings
  clip: districts
  output: clipped           # default: clipped
```

### `intersect`

```yaml
- step: intersect
  layer_a: buildings
  layer_b: flood_zones
  output: intersection      # default: intersection
```

### `export`

```yaml
- step: export
  layer: buffered
  format: geojson           # geojson (pure Python) or shapefile ([convert] extra)
  output: out/buffered.geojson
```

Missing output directories are created automatically.

### `validate`

```yaml
- step: validate
  srid: 4326                # optional expected SRID
```

Runs full geometry validation on the working GeoPackage. A failed validation marks the step as failed.

## Error Handling

With the default `fail_fast: false`, every step runs regardless of earlier failures. Each failure is recorded in the report and printed with its error:

```
  2. clip       FAILED  Clip table 'missing_layer' has no features
3/4 steps ok (0.9s)
```

The command exits with code `1` if any step failed, `0` if all succeeded, so pipelines work in CI scripts and shell chains.

!!! tip
    Use `fail_fast: true` when later steps depend on earlier outputs and running them would produce confusing cascading errors. Failed steps are marked `skipped` in the report.

## Python API

```python
from geopkgtoolkit import run_pipeline, load_config

# From a config file
report = run_pipeline("pipeline.yaml")

# Or from a dict
report = run_pipeline({
    "gpkg": "processed.gpkg",
    "steps": [
        {"step": "import", "input": "data/*.geojson"},
        {"step": "export", "layer": "parcels", "format": "geojson", "output": "out.geojson"},
    ],
})

assert report["ok"]
for step in report["steps"]:
    print(step["step"], step["status"], step.get("features", ""))
```
