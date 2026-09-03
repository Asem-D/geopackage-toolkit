"""
Config-driven batch pipeline for GeoPackage processing.

Run a sequence of steps (import, operations, export, validate) defined
in a JSON or YAML config file against a single working GeoPackage.

Example config (pipeline.yaml):

    gpkg: processed.gpkg
    fail_fast: false
    steps:
      - step: import
        input: "data/*.geojson"          # glob or single path
      - step: clip
        source: buildings
        clip: districts
        output: clipped
      - step: buffer
        layer: clipped
        distance: 100
        output: buffered
      - step: export
        layer: buffered
        format: geojson
        output: out/buffered.geojson
      - step: validate
        srid: 4326

Run it:

    geopkg pipeline pipeline.yaml

JSON configs need no extra dependency. YAML configs require PyYAML:
``pip install geopackage-toolkit[pipeline]``.
"""

import glob
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Union

from geopkgtoolkit._spatialite import connect
from geopkgtoolkit.convert import (
    export_geojson,
    export_shapefile,
    import_geojson,
    import_shapefile,
)
from geopkgtoolkit.operations import buffer, clip, intersect

SUPPORTED_STEPS = ("import", "export", "buffer", "clip", "intersect", "validate")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: Union[str, Path]) -> dict:
    """Load a pipeline config from a JSON or YAML file.

    Args:
        config_path: Path to the config file (.json, .yaml, or .yml).

    Returns:
        Parsed config dict.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is malformed.
        ImportError: If a YAML config is loaded without PyYAML installed.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML pipeline configs. "
                "Install with: pip install geopackage-toolkit[pipeline]"
            )
        config = yaml.safe_load(text)
    else:
        config = json.loads(text)

    _validate_config(config)
    return config


def _validate_config(config: dict) -> None:
    """Raise ValueError if the config is malformed."""
    if not isinstance(config, dict):
        raise ValueError("Config must be a mapping with 'gpkg' and 'steps' keys")
    if not config.get("gpkg"):
        raise ValueError("Config must define 'gpkg' (the working GeoPackage path)")
    steps = config.get("steps")
    if not steps or not isinstance(steps, list):
        raise ValueError("Config must define a non-empty 'steps' list")
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or "step" not in step:
            raise ValueError(f"steps[{i}] must be a mapping with a 'step' key")
        if step["step"] not in SUPPORTED_STEPS:
            raise ValueError(
                f"steps[{i}]: unknown step type '{step['step']}'. "
                f"Supported: {', '.join(SUPPORTED_STEPS)}"
            )


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def _expand_inputs(pattern: str) -> list:
    """Expand a path or glob pattern to a sorted list of files."""
    p = Path(pattern)
    if p.exists():
        return [p]
    matches = sorted(glob.glob(str(pattern)))
    if not matches:
        raise FileNotFoundError(f"No files match pattern: {pattern}")
    return [Path(m) for m in matches]


def _count_features(con: sqlite3.Connection, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]


def _run_step(step: dict, gpkg_path: Path) -> dict:
    """Execute one pipeline step. Returns a result dict (empty on error paths).

    Raises on failure; the caller records the error in the report.
    """
    stype = step["step"]

    if stype == "import":
        files = _expand_inputs(step["input"])
        srid = step.get("srid", 4326)
        geom_col = step.get("geom_col", "geom")
        fixed_layer = step.get("layer")
        results = []
        for f in files:
            layer = fixed_layer or f.stem
            suffix = f.suffix.lower()
            if suffix == ".geojson":
                import_geojson(gpkg_path, f, layer, geom_col=geom_col, srid=srid)
            elif suffix == ".shp":
                import_shapefile(gpkg_path, f, layer, geom_col=geom_col, srid=srid)
            else:
                raise ValueError(f"Unsupported import format '{suffix}': {f}")
            con = connect(gpkg_path, enable_gpkg_mode=False)
            try:
                results.append({
                    "file": str(f),
                    "layer": layer,
                    "features": _count_features(con, layer),
                })
            finally:
                con.close()
        return {"files": results, "features": sum(r["features"] for r in results)}

    # All remaining steps need an open connection to the working GeoPackage
    con = connect(gpkg_path, enable_gpkg_mode=False)
    try:
        if stype == "buffer":
            table = buffer(
                con, step["layer"], float(step["distance"]),
                output_table=step.get("output", "buffered"),
            )
            return {"output": table, "features": _count_features(con, table)}

        if stype == "clip":
            table = clip(
                con, step["source"], step["clip"],
                output_table=step.get("output", "clipped"),
            )
            return {"output": table, "features": _count_features(con, table)}

        if stype == "intersect":
            table = intersect(
                con, step["layer_a"], step["layer_b"],
                output_table=step.get("output", "intersection"),
            )
            return {"output": table, "features": _count_features(con, table)}

        if stype == "export":
            fmt = step.get("format", "geojson").lower()
            layer = step["layer"]
            out_path = Path(step["output"])
            if out_path.parent and not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "geojson":
                out = export_geojson(con, layer, step["output"])
            elif fmt == "shapefile":
                out = export_shapefile(con, layer, step["output"])
            else:
                raise ValueError(f"Unknown export format '{fmt}'. Use 'geojson' or 'shapefile'.")
            return {"output": str(out), "features": _count_features(con, layer)}

        if stype == "validate":
            from geopkgtoolkit.validate import validate_layers

            report = validate_layers(
                str(gpkg_path), expected_srid=step.get("srid"),
            )
            result = {"valid": report.is_valid, "summary": report.summary()}
            if not report.is_valid:
                raise ValueError(
                    f"Validation found {report.total_warnings} warnings:\n{report.summary()}"
                )
            return result

        raise ValueError(f"Unknown step type: {stype}")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    config: Union[str, Path, dict],
    report_path: Optional[Union[str, Path]] = None,
) -> dict:
    """Run a pipeline and return the run report.

    Args:
        config: Path to a JSON/YAML config file, or an already-parsed
            config dict.
        report_path: Optional path to write the run report as JSON.
            The CLI always writes a report (from the config 'report' key
            or a default next to the config file).

    Returns:
        Report dict with per-step status, feature counts, errors, timing::

            {
                "ok": True,
                "gpkg": "processed.gpkg",
                "steps": [
                    {"step": "import", "status": "ok", "features": 120, ...},
                    {"step": "clip", "status": "failed", "error": "..."},
                ],
                "elapsed_s": 1.23,
            }

    Notes:
        With ``fail_fast: true`` (default false), execution stops at the
        first failed step. With the default, all steps run regardless and
        each failure is recorded in the report.
    """
    if isinstance(config, (str, Path)):
        config_path = Path(config)
        cfg = load_config(config_path)
        default_report = config_path.with_suffix(".report.json")
    else:
        _validate_config(config)
        cfg = config
        config_path = None
        default_report = Path("pipeline.report.json")

    gpkg_path = Path(cfg["gpkg"])
    fail_fast = cfg.get("fail_fast", False)

    started = time.time()
    steps_report = []
    stopped = False

    for i, step in enumerate(cfg["steps"]):
        entry = {"index": i, "step": step["step"], "status": None}

        if stopped:
            entry["status"] = "skipped"
            steps_report.append(entry)
            continue

        t0 = time.time()
        try:
            result = _run_step(step, gpkg_path)
            entry.update(result)
            entry["status"] = "ok"
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            if fail_fast:
                stopped = True
        entry["elapsed_s"] = round(time.time() - t0, 3)
        steps_report.append(entry)

    report = {
        "config": str(config_path) if config_path else None,
        "gpkg": str(gpkg_path),
        "fail_fast": fail_fast,
        "ok": all(s["status"] == "ok" for s in steps_report),
        "steps": steps_report,
        "elapsed_s": round(time.time() - started, 3),
    }

    if report_path:
        report_path = Path(report_path)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        report["report_file"] = str(report_path)

    return report


def summarize_report(report: dict) -> str:
    """Format a run report as a short human-readable summary."""
    lines = [f"Pipeline: {report['config'] or '<dict>'} -> {report['gpkg']}"]
    for s in report["steps"]:
        if s["status"] == "ok":
            detail = s.get("features")
            if detail is not None and s.get("output"):
                detail = f"{detail:,} features -> {s['output']}"
            elif detail is not None and s.get("files"):
                detail = f"{detail:,} features ({len(s['files'])} file(s))"
            elif s["step"] == "validate":
                detail = "valid"
            lines.append(f"  {s['index'] + 1}. {s['step']:<10} ok      {detail or ''}")
        elif s["status"] == "failed":
            lines.append(f"  {s['index'] + 1}. {s['step']:<10} FAILED  {s.get('error', '')}")
        else:
            lines.append(f"  {s['index'] + 1}. {s['step']:<10} skipped")
    ok = sum(1 for s in report["steps"] if s["status"] == "ok")
    lines.append(
        f"{ok}/{len(report['steps'])} steps ok ({report['elapsed_s']}s)"
    )
    return "\n".join(lines)
