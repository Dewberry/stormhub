"""Testing functions."""

import unittest
from math import floor

import fiona
import numpy as np
import rioxarray
import xarray as xr
from affine import Affine
from shapely import Polygon

from stormhub.met.transpose import Transpose


def shapely_polygon_to_geojson(polygon: Polygon) -> dict:
    """
    Convert a Shapely Polygon to GeoJSON format.
    """
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(polygon.exterior.coords)],
        },
        "properties": {"id": 1},
    }


def save_polygon_to_geojson(polygon: Polygon, filename: str):
    """
    Save a Shapely Polygon to a GeoJSON file.
    """
    schema = {
        "geometry": "Polygon",
        "properties": {"id": "int"},
    }
    geojson = shapely_polygon_to_geojson(polygon)
    with fiona.open(filename, "w", driver="GeoJSON", crs="EPSG:4326", schema=schema) as dst:
        dst.write(geojson)


def save_xarray_to_raster(data_array: xr.DataArray, filename: str):
    """
    Save an xarray DataArray to a raster file.
    """
    data_array.rio.to_raster(filename, driver="GTiff", dtype="int16")


def create_test_transposition_domain_polygon() -> Polygon:
    """
    Create a test polygon for the transpose function.
    """
    # Define the coordinates of the polygon
    coords = [(3, 0), (5, 2), (4, 4), (0, 5)]

    # Create a Shapely Polygon object
    polygon = Polygon(coords)

    return polygon


def create_test_watershed_polygon() -> Polygon:
    """
    Create a test polygon for the transpose function.
    """
    # Define the coordinates of the polygon
    coords = [(3, 1), (3, 3), (1, 4), (2, 3), (2, 3)]

    # Create a Shapely Polygon object
    polygon = Polygon(coords)

    return polygon


def create_test_data_array(transposition_domain_polygon: Polygon, res: float) -> xr.DataArray:
    """
    Create a test DataArray for the transpose function.
    """
    # Create a 5x5 grid with values ranging from 0 to 24
    min_x, min_y, max_x, max_y = transposition_domain_polygon.bounds
    nx = floor((max_x - min_x) / res)
    ny = floor((max_y - min_y) / res)
    longitudes, latitudes = (
        np.linspace(min_x + res / 2, max_x - res / 2, nx),
        np.linspace(min_y + res / 2, max_y - res / 2, ny),
    )

    # Create sample data
    data = np.arange(nx * ny, dtype=np.float64)
    data = data.reshape((ny, nx))

    # Create the xarray DataArray
    da = xr.DataArray(
        data=data,
        dims=["latitude", "longitude"],
        coords={"latitude": latitudes, "longitude": longitudes},
    )

    rio_da = da.rio.set_spatial_dims(x_dim="longitude", y_dim="latitude")
    rio_da.rio.write_crs("EPSG:4326", inplace=True)
    rio_da = rio_da.rio.clip([transposition_domain_polygon], all_touched=True, drop=True)

    return rio_da


class TestTransposeFunction(unittest.TestCase):
    def setUp(self):
        self.watershed = create_test_watershed_polygon()
        self.transposition_domain = create_test_transposition_domain_polygon()
        self.data_array = create_test_data_array(self.transposition_domain, 1)
        self.transpose = Transpose(self.data_array, self.watershed, "longitude", "latitude")

    def test_valid_spaces_polygon(self):
        """
        Test the valid spaces polygon.
        """
        # Create a test polygon
        test_polygon = Polygon(
            [(0, 5), (4, 5), (4, 4), (5, 4), (5, 1), (4, 1), (4, 0), (2, 0), (2, 1), (1, 1), (1, 3), (0, 3)]
        )

        # Check if the valid spaces polygon is correct
        self.assertTrue(self.transpose.valid_spaces_polygon.equals(test_polygon))

    def test_max_transpose_polygon(self):
        """
        Test the max transpose function.
        """
        # Create a test polygon
        test_polygon = Polygon([(3, 5), (4, 5), (4, 4), (5, 4), (5, 1), (4, 1), (4, 3), (3, 3)])

        # Check if the max transpose polygon is correct
        max_polygon = self.transpose.max_transpose()[0]
        self.assertTrue(max_polygon.equals(test_polygon))

    def test_max_transpose_max_value(self):
        # Create a test max value
        test_max_value = 24

        # Check if the max value is correct
        max_value = self.transpose.max_transpose(np.max)[2]
        self.assertEqual(max_value, test_max_value)

    def test_max_transpose_affine(self):
        # Create a test affine transformation
        test_affine = Affine.translation(2, 0)

        # Check if the affine transformation is correct
        max_affine = self.transpose.max_transpose()[1]
        self.assertEqual(max_affine, test_affine)


if __name__ == "__main__":
    unittest.main()
