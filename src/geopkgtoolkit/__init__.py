"""
geopkgtoolkit - Python toolkit for GeoPackage spatial data.

Validate, query, convert, and publish spatial data without PostGIS or ArcGIS.

Example:
    >>> from geopkgtoolkit import connect, validate_layers, count_in_zones
    >>> con = connect("data.gpkg")
    >>> report = validate_layers("data.gpkg", expected_srid=4326)
    >>> counts = count_in_zones(con, "buildings", "admin3")
"""

from geopkgtoolkit._spatialite import connect
from geopkgtoolkit.validate import validate_layers, validate_layer
from geopkgtoolkit.query import count_in_zones, points_in_polygons, bbox_filter
from geopkgtoolkit.operations import buffer, clip, intersect
from geopkgtoolkit.convert import (
    export_geojson,
    export_shapefile,
    import_geojson,
    import_shapefile,
)

__version__ = "0.3.0"
__all__ = [
    "connect",
    "validate_layers",
    "validate_layer",
    "count_in_zones",
    "points_in_polygons",
    "bbox_filter",
    "buffer",
    "clip",
    "intersect",
    "export_geojson",
    "export_shapefile",
    "import_geojson",
    "import_shapefile",
]
