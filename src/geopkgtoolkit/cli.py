"""
CLI entry point for geopkgtoolkit.

Usage:
    geopkg validate <file.gpkg> [--srid 4326] [--layers buildings,roads]
    geopkg count <file.gpkg> --features buildings --zones admin3
    geopkg info <file.gpkg>
    geopkg buffer <file.gpkg> --layer buildings --distance 100 --output buffered
    geopkg clip <file.gpkg> --source buildings --clip districts --output clipped
    geopkg intersect <file.gpkg> --layer-a buildings --layer-b flood_zones --output result
    geopkg export <file.gpkg> --layer buildings --format geojson --output buildings.geojson
    geopkg import <input.geojson> --output data.gpkg --layer buildings
    geopkg pipeline <config.yaml>
"""

import argparse
import sys
import time
from pathlib import Path


def cmd_validate(args):
    """Validate geometry health in a GeoPackage."""
    from geopkgtoolkit.validate import validate_layers

    layers = args.layers.split(",") if args.layers else None
    report = validate_layers(args.file, expected_srid=args.srid, layers=layers)
    print(report.summary())
    return 0 if report.is_valid else 1


def cmd_count(args):
    """Count features per zone."""
    from geopkgtoolkit._spatialite import connect
    from geopkgtoolkit.query import count_in_zones

    con = connect(args.file)
    try:
        t0 = time.time()
        counts = count_in_zones(con, args.features, args.zones)
        elapsed = time.time() - t0

        # Sort by count descending
        counts.sort(key=lambda x: x[1], reverse=True)

        # Print table
        id_col = args.zones
        print(f"{'zone_id':>12}  {'count':>10}")
        print(f"{'-'*12}  {'-'*10}")
        for zid, count in counts:
            print(f"{zid!s:>12}  {count:>10,}")

        total = sum(c for _, c in counts)
        print(f"\nTotal: {total:,} features across {len(counts)} zones ({elapsed:.1f}s)")
        return 0
    finally:
        con.close()


def cmd_info(args):
    """Show GeoPackage metadata and layer info."""
    from geopkgtoolkit._spatialite import connect, list_layers

    con = connect(args.file)
    try:
        layers = list_layers(con)
        print(f"GeoPackage: {args.file}")
        print(f"Layers: {len(layers)}\n")

        for li in layers:
            count = con.execute(
                f"SELECT COUNT(*) FROM [{li['table_name']}]"
            ).fetchone()[0]
            print(
                f"  {li['table_name']}: "
                f"{count:,} features, "
                f"geom={li['column_name']}, "
                f"type={li['geometry_type']}, "
                f"srs={li['srs_id']}"
            )
        return 0
    finally:
        con.close()


def cmd_buffer(args):
    """Buffer features by a distance."""
    from geopkgtoolkit._spatialite import connect
    from geopkgtoolkit.operations import buffer

    con = connect(args.file)
    try:
        t0 = time.time()
        output = buffer(
            con, args.layer, args.distance,
            output_table=args.output,
            keep_attrs=not args.no_attrs,
        )
        elapsed = time.time() - t0
        count = con.execute(f"SELECT COUNT(*) FROM [{output}]").fetchone()[0]
        print(f"Buffered {count:,} features -> {output} ({elapsed:.1f}s)")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_clip(args):
    """Clip source layer by clip layer."""
    from geopkgtoolkit._spatialite import connect
    from geopkgtoolkit.operations import clip

    con = connect(args.file)
    try:
        t0 = time.time()
        output = clip(
            con, args.source, args.clip_layer,
            output_table=args.output,
        )
        elapsed = time.time() - t0
        count = con.execute(f"SELECT COUNT(*) FROM [{output}]").fetchone()[0]
        print(f"Clipped {count:,} features -> {output} ({elapsed:.1f}s)")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_intersect(args):
    """Spatial intersection of two layers."""
    from geopkgtoolkit._spatialite import connect
    from geopkgtoolkit.operations import intersect

    con = connect(args.file)
    try:
        t0 = time.time()
        output = intersect(
            con, args.layer_a, args.layer_b,
            output_table=args.output,
        )
        elapsed = time.time() - t0
        count = con.execute(f"SELECT COUNT(*) FROM [{output}]").fetchone()[0]
        print(f"Intersected {count:,} features -> {output} ({elapsed:.1f}s)")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_export(args):
    """Export a GeoPackage layer to GeoJSON or Shapefile."""
    from geopkgtoolkit._spatialite import connect
    from geopkgtoolkit.convert import export_geojson, export_shapefile

    con = connect(args.file)
    try:
        t0 = time.time()
        fmt = args.format.lower()

        if fmt == "geojson":
            out = export_geojson(con, args.layer, args.output, args.geom_col)
            elapsed = time.time() - t0
            # Count features
            from geopkgtoolkit._spatialite import list_layers
            geom_col = args.geom_col
            if not geom_col:
                layers = list_layers(con)
                for li in layers:
                    if li["table_name"] == args.layer:
                        geom_col = li["column_name"]
                        break
                if not geom_col:
                    geom_col = "geom"
            count = con.execute(
                f"SELECT COUNT(*) FROM [{args.layer}] WHERE [{geom_col}] IS NOT NULL"
            ).fetchone()[0]
            print(f"Exported {count:,} features to {out} ({elapsed:.1f}s)")

        elif fmt == "shapefile":
            out = export_shapefile(con, args.layer, args.output, args.geom_col)
            elapsed = time.time() - t0
            from geopkgtoolkit._spatialite import list_layers
            geom_col = args.geom_col
            if not geom_col:
                layers = list_layers(con)
                for li in layers:
                    if li["table_name"] == args.layer:
                        geom_col = li["column_name"]
                        break
                if not geom_col:
                    geom_col = "geom"
            count = con.execute(
                f"SELECT COUNT(*) FROM [{args.layer}] WHERE [{geom_col}] IS NOT NULL"
            ).fetchone()[0]
            # List created files
            from pathlib import Path
            base = Path(args.output).with_suffix("")
            created = [str(base.with_suffix(ext)) for ext in [".shp", ".shx", ".dbf", ".prj"]
                        if base.with_suffix(ext).exists()]
            print(f"Exported {count:,} features to {', '.join(created)} ({elapsed:.1f}s)")

        else:
            print(f"Error: Unknown format '{fmt}'. Use 'geojson' or 'shapefile'.", file=sys.stderr)
            return 1

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_import(args):
    """Import a GeoJSON or Shapefile into a GeoPackage layer."""
    from pathlib import Path
    from geopkgtoolkit.convert import import_geojson, import_shapefile

    t0 = time.time()
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()

    try:
        if suffix == ".geojson":
            layer = import_geojson(
                args.output, args.input, args.layer,
                geom_col=args.geom_col, srid=args.srid,
            )
        elif suffix == ".shp":
            layer = import_shapefile(
                args.output, args.input, args.layer,
                geom_col=args.geom_col, srid=args.srid,
            )
        else:
            print(f"Error: Unsupported file type '{suffix}'. Use .geojson or .shp.", file=sys.stderr)
            return 1

        elapsed = time.time() - t0
        # Count features in the new layer
        from geopkgtoolkit._spatialite import connect
        con = connect(args.output)
        try:
            count = con.execute(f"SELECT COUNT(*) FROM [{layer}]").fetchone()[0]
            print(f"Imported {count:,} features into {args.output} -> {layer} ({elapsed:.1f}s)")
        finally:
            con.close()

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pipeline(args):
    """Run a config-driven batch pipeline."""
    from geopkgtoolkit.pipeline import load_config, run_pipeline, summarize_report

    try:
        cfg = load_config(args.config)
        default_report = Path(args.config).with_suffix(".report.json")
        report = run_pipeline(
            args.config,
            report_path=cfg.get("report") or default_report,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(summarize_report(report))
    if report.get("report_file"):
        print(f"Report: {report['report_file']}")
    return 0 if report["ok"] else 1


def main():
    parser = argparse.ArgumentParser(
        prog="geopkg",
        description="GeoPackage Toolkit: validate, query, and explore spatial data.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate geometry health in a GeoPackage")
    p_val.add_argument("file", help="Path to GeoPackage file")
    p_val.add_argument("--srid", type=int, default=None, help="Expected SRID (e.g., 4326)")
    p_val.add_argument("--layers", default=None, help="Comma-separated layer names to validate")
    p_val.set_defaults(func=cmd_validate)

    # count
    p_count = subparsers.add_parser("count", help="Count features per zone")
    p_count.add_argument("file", help="Path to GeoPackage file")
    p_count.add_argument("--features", required=True, help="Feature layer to count")
    p_count.add_argument("--zones", required=True, help="Zone layer for grouping")
    p_count.set_defaults(func=cmd_count)

    # info
    p_info = subparsers.add_parser("info", help="Show GeoPackage layer info")
    p_info.add_argument("file", help="Path to GeoPackage file")
    p_info.set_defaults(func=cmd_info)

    # buffer
    p_buf = subparsers.add_parser("buffer", help="Buffer features by a distance")
    p_buf.add_argument("file", help="Path to GeoPackage file")
    p_buf.add_argument("--layer", required=True, help="Layer to buffer")
    p_buf.add_argument("--distance", type=float, required=True, help="Buffer distance in CRS units")
    p_buf.add_argument("--output", default="buffered", help="Output layer name (default: buffered)")
    p_buf.add_argument("--no-attrs", action="store_true", help="Exclude source attributes from output")
    p_buf.set_defaults(func=cmd_buffer)

    # clip
    p_clip = subparsers.add_parser("clip", help="Clip source layer by clip layer")
    p_clip.add_argument("file", help="Path to GeoPackage file")
    p_clip.add_argument("--source", required=True, help="Source layer to clip")
    p_clip.add_argument("--clip", required=True, dest="clip_layer", help="Clip layer (polygon boundary)")
    p_clip.add_argument("--output", default="clipped", help="Output layer name (default: clipped)")
    p_clip.set_defaults(func=cmd_clip)

    # intersect
    p_int = subparsers.add_parser("intersect", help="Spatial intersection of two layers")
    p_int.add_argument("file", help="Path to GeoPackage file")
    p_int.add_argument("--layer-a", required=True, help="First input layer")
    p_int.add_argument("--layer-b", required=True, help="Second input layer")
    p_int.add_argument("--output", default="intersection", help="Output layer name (default: intersection)")
    p_int.set_defaults(func=cmd_intersect)

    # export
    p_exp = subparsers.add_parser("export", help="Export a GeoPackage layer to GeoJSON or Shapefile")
    p_exp.add_argument("file", help="Path to GeoPackage file")
    p_exp.add_argument("--layer", required=True, help="Layer to export")
    p_exp.add_argument("--format", required=True, choices=["geojson", "shapefile"], help="Output format")
    p_exp.add_argument("--output", required=True, help="Output file path")
    p_exp.add_argument("--geom-col", default=None, help="Geometry column name (auto-detected)")
    p_exp.set_defaults(func=cmd_export)

    # import
    p_imp = subparsers.add_parser("import", help="Import a GeoJSON or Shapefile into a GeoPackage")
    p_imp.add_argument("input", help="Input file path (.geojson or .shp)")
    p_imp.add_argument("--output", required=True, help="Output GeoPackage path")
    p_imp.add_argument("--layer", required=True, help="Layer name for the imported data")
    p_imp.add_argument("--geom-col", default="geom", help="Geometry column name (default: geom)")
    p_imp.add_argument("--srid", type=int, default=4326, help="SRID (default: 4326)")
    p_imp.set_defaults(func=cmd_import)

    # pipeline
    p_pipe = subparsers.add_parser(
        "pipeline", help="Run a config-driven batch pipeline (JSON or YAML)"
    )
    p_pipe.add_argument("config", help="Path to pipeline config file (.json, .yaml, .yml)")
    p_pipe.set_defaults(func=cmd_pipeline)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
