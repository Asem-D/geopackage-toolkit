"""Tests for geopkgtoolkit.pipeline module (config-driven batch pipeline)."""

import json
import sys

import pytest

from geopkgtoolkit.cli import main
from geopkgtoolkit.pipeline import load_config, run_pipeline, summarize_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_geojson(path, name_prefix="a", count=3, with_null=False):
    """Write a small GeoJSON FeatureCollection of square polygons."""
    features = []
    for i in range(count):
        x = i * 10
        features.append({
            "type": "Feature",
            "properties": {"name": f"{name_prefix}{i}", "height": float(i + 1)},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]],
            },
        })
    if with_null:
        features.append({
            "type": "Feature",
            "properties": {"name": "nullgeom", "height": 0.0},
            "geometry": None,
        })
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


@pytest.fixture
def buildings_geojson(tmp_path):
    return _write_geojson(tmp_path / "buildings.geojson")


@pytest.fixture
def districts_geojson(tmp_path):
    return _write_geojson(tmp_path / "districts.geojson", name_prefix="d")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_json_config(self, tmp_path):
        cfg_file = tmp_path / "pipeline.json"
        cfg_file.write_text(json.dumps({
            "gpkg": "out.gpkg",
            "steps": [{"step": "validate"}],
        }), encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg["gpkg"] == "out.gpkg"
        assert cfg["steps"][0]["step"] == "validate"

    def test_load_yaml_config(self, tmp_path):
        import yaml

        cfg_file = tmp_path / "pipeline.yaml"
        cfg_file.write_text(
            "gpkg: out.gpkg\nsteps:\n  - step: validate\n",
            encoding="utf-8",
        )
        cfg = load_config(cfg_file)
        assert cfg["gpkg"] == "out.gpkg"

    def test_missing_config_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nope.yaml")

    def test_missing_gpkg_key(self, tmp_path):
        cfg_file = tmp_path / "pipeline.json"
        cfg_file.write_text(json.dumps({"steps": [{"step": "validate"}]}), encoding="utf-8")
        with pytest.raises(ValueError, match="gpkg"):
            load_config(cfg_file)

    def test_missing_steps_key(self, tmp_path):
        cfg_file = tmp_path / "pipeline.json"
        cfg_file.write_text(json.dumps({"gpkg": "out.gpkg"}), encoding="utf-8")
        with pytest.raises(ValueError, match="steps"):
            load_config(cfg_file)

    def test_unknown_step_type(self, tmp_path):
        cfg_file = tmp_path / "pipeline.json"
        cfg_file.write_text(json.dumps({
            "gpkg": "out.gpkg",
            "steps": [{"step": "transmogrify"}],
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown step type"):
            load_config(cfg_file)

    def test_dict_config_validated(self):
        with pytest.raises(ValueError):
            run_pipeline({"gpkg": "out.gpkg", "steps": [{"step": "bogus"}]})


# ---------------------------------------------------------------------------
# Pipeline runs (self-contained: import -> buffer -> export)
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_import_buffer_export_end_to_end(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "processed.gpkg"
        out_json = tmp_path / "out" / "buffered.geojson"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "buffer", "layer": "buildings", "distance": 0.01, "output": "buffered"},
                {"step": "export", "layer": "buffered", "format": "geojson", "output": str(out_json)},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is True
        assert [s["status"] for s in report["steps"]] == ["ok", "ok", "ok"]
        assert report["steps"][0]["features"] == 3
        assert report["steps"][1]["output"] == "buffered"
        assert report["steps"][1]["features"] == 3
        assert out_json.exists()
        fc = json.loads(out_json.read_text(encoding="utf-8"))
        assert len(fc["features"]) == 3

    def test_yaml_config_end_to_end(self, tmp_path, buildings_geojson):
        import yaml

        out_gpkg = tmp_path / "p.gpkg"
        out_json = tmp_path / "b.geojson"
        cfg_file = tmp_path / "pipe.yaml"
        cfg_file.write_text(yaml.safe_dump({
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "export", "layer": "buildings", "format": "geojson", "output": str(out_json)},
            ],
        }), encoding="utf-8")
        report = run_pipeline(cfg_file)
        assert report["ok"] is True
        assert out_json.exists()

    def test_glob_import_multiple_files(self, tmp_path, buildings_geojson, districts_geojson):
        out_gpkg = tmp_path / "merged.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [{"step": "import", "input": str(tmp_path / "*.geojson")}],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is True
        step = report["steps"][0]
        assert step["features"] == 6
        assert len(step["files"]) == 2
        # Layer names derived from file stems
        assert {f["layer"] for f in step["files"]} == {"buildings", "districts"}
        # Both layers importable into the same gpkg: clip one by the other
        report2 = run_pipeline({
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "clip", "source": "buildings", "clip": "districts", "output": "clipped"},
            ],
        })
        assert report2["ok"] is True
        assert report2["steps"][0]["features"] == 3

    def test_import_fixed_layer_name(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "single.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson), "layer": "parcels"},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is True
        assert report["steps"][0]["files"][0]["layer"] == "parcels"

    def test_import_unsupported_format_fails_step(self, tmp_path):
        bad = tmp_path / "data.txt"
        bad.write_text("not spatial data", encoding="utf-8")
        cfg = {
            "gpkg": str(tmp_path / "out.gpkg"),
            "steps": [{"step": "import", "input": str(bad)}],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is False
        assert report["steps"][0]["status"] == "failed"
        assert "Unsupported import format" in report["steps"][0]["error"]

    def test_import_no_matching_files_fails_step(self, tmp_path):
        cfg = {
            "gpkg": str(tmp_path / "out.gpkg"),
            "steps": [{"step": "import", "input": str(tmp_path / "*.shp")}],
        }
        report = run_pipeline(cfg)
        assert report["steps"][0]["status"] == "failed"
        assert "No files match" in report["steps"][0]["error"]

    def test_fail_fast_false_continues(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "p.gpkg"
        out_json = tmp_path / "b.geojson"
        cfg = {
            "gpkg": str(out_gpkg),
            "fail_fast": False,
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                # Fails: boundary layer does not exist
                {"step": "clip", "source": "buildings", "clip": "missing_layer"},
                {"step": "export", "layer": "buildings", "format": "geojson", "output": str(out_json)},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is False
        assert report["steps"][1]["status"] == "failed"
        # Third step still ran and succeeded
        assert report["steps"][2]["status"] == "ok"
        assert out_json.exists()

    def test_fail_fast_true_stops(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "p.gpkg"
        out_json = tmp_path / "b.geojson"
        cfg = {
            "gpkg": str(out_gpkg),
            "fail_fast": True,
            "steps": [
                # Fails: gpkg does not exist yet (no import first)
                {"step": "buffer", "layer": "buildings", "distance": 0.01},
                {"step": "export", "layer": "buildings", "format": "geojson", "output": str(out_json)},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is False
        assert report["steps"][0]["status"] == "failed"
        assert report["steps"][1]["status"] == "skipped"
        assert not out_json.exists()

    def test_validate_step_ok(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "v.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "validate", "srid": 4326},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is True
        assert report["steps"][1]["valid"] is True

    def test_validate_step_fails_on_srid_mismatch(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "v.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "validate", "srid": 3857},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is False
        assert report["steps"][1]["status"] == "failed"
        assert "warnings" in report["steps"][1]["error"]

    def test_clip_intersect_steps(self, tmp_path, buildings_geojson, districts_geojson):
        out_gpkg = tmp_path / "ops.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "import", "input": str(districts_geojson)},
                {"step": "clip", "source": "buildings", "clip": "districts", "output": "clipped"},
                {"step": "intersect", "layer_a": "buildings", "layer_b": "districts",
                 "output": "intersection"},
            ],
        }
        report = run_pipeline(cfg)
        assert report["ok"] is True
        assert report["steps"][2]["features"] == 3
        assert report["steps"][3]["features"] == 3

    def test_report_file_written(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "r.gpkg"
        report_file = tmp_path / "run.report.json"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [{"step": "import", "input": str(buildings_geojson)}],
        }
        report = run_pipeline(cfg, report_path=report_file)
        assert report["report_file"] == str(report_file)
        saved = json.loads(report_file.read_text(encoding="utf-8"))
        assert saved["ok"] is True
        assert len(saved["steps"]) == 1


# ---------------------------------------------------------------------------
# Summarize + CLI
# ---------------------------------------------------------------------------

class TestSummarizeAndCli:
    def test_summarize_report(self, tmp_path, buildings_geojson):
        out_gpkg = tmp_path / "s.gpkg"
        cfg = {
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "clip", "source": "buildings", "clip": "missing"},
            ],
        }
        report = run_pipeline(cfg)
        text = summarize_report(report)
        assert "1/2 steps ok" in text
        assert "FAILED" in text
        assert "import" in text

    def test_cli_pipeline_success(self, tmp_path, buildings_geojson, capsys, monkeypatch):
        import yaml

        out_gpkg = tmp_path / "cli.gpkg"
        out_json = tmp_path / "cli_out.geojson"
        cfg_file = tmp_path / "pipeline.yaml"
        cfg_file.write_text(yaml.safe_dump({
            "gpkg": str(out_gpkg),
            "steps": [
                {"step": "import", "input": str(buildings_geojson)},
                {"step": "export", "layer": "buildings", "format": "geojson", "output": str(out_json)},
            ],
        }), encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["geopkg", "pipeline", str(cfg_file)])
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "2/2 steps ok" in out
        # Default report file written next to the config
        assert (tmp_path / "pipeline.report.json").exists()

    def test_cli_pipeline_failure_exit_code(self, tmp_path, capsys, monkeypatch):
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps({
            "gpkg": str(tmp_path / "nope.gpkg"),
            "steps": [{"step": "buffer", "layer": "x", "distance": 1}],
        }), encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["geopkg", "pipeline", str(cfg_file)])
        rc = main()
        assert rc == 1
        assert "FAILED" in capsys.readouterr().out
