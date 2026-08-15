"""
CLI entry point for geopkgtoolkit.

Usage:
    geopkg validate <file.gpkg> [--srid 4326] [--layers buildings,roads]
    geopkg count <file.gpkg> --features buildings --zones admin3
    geopkg info <file.gpkg>
"""

import argparse
import sys
import time


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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
