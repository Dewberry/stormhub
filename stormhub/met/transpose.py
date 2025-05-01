"""Class to handle transpoition functionality."""

from typing import Any, Callable

import numpy as np
import xarray as xr
from affine import Affine
from rasterio.features import shapes
from rasterio.mask import geometry_mask
from rasterio.windows import Window, get_data_window
from shapely import Polygon
from shapely.affinity import translate
from shapely.geometry import shape


class Transpose:
    """
    A class to handle the transposition of a watershed mask over a data array.

    Attributes
    ----------
        data_array (xr.DataArray): The data array to be transposed.
        watershed (Polygon): The watershed polygon.
        x_var (str): The x variable name in the data array.
        y_var (str): The y variable name in the data array.
    """

    def __init__(self, data_array: xr.DataArray, watershed: Polygon, x_var: str, y_var: str) -> None:
        """
        Initialize the Transpose class.

        Args:
            data_array (xr.DataArray): The data array to be transposed.
            watershed (Polygon): The watershed polygon.
            x_var (str): The x variable name in the data array.
            y_var (str): The y variable name in the data array.
        """
        self.data_array = data_array
        self.watershed = watershed
        self.x_var = x_var
        self.y_var = y_var
        self.x_cellsize, self.y_cellsize = self.data_array.rio.resolution()
        self.transform = self.data_array.rio.transform()
        self.width = self.data_array.rio.width
        self.height = self.data_array.rio.height
        self._np_data_array = None
        self._watershed_window = None
        self._watershed_mask = None
        self._watershed_mask_clipped = None
        self._valid_shifts = None
        self._valid_spaces = None
        self._valid_spaces_polygon = None
        self._data_array_x_coords = None
        self._data_array_y_coords = None

    def _calculate_watershed_mask_and_window(self) -> None:
        """
        Calculate the watershed mask and window.

        This method creates a mask array and determines the window of the watershed
        within the data array.
        """
        mask_array = geometry_mask(
            [self.watershed],
            out_shape=(int(self.data_array.rio.height), int(self.data_array.rio.width)),
            transform=self.data_array.rio.transform(recalc=True),
            all_touched=True,
            invert=True,
        )
        self._watershed_mask = mask_array
        window = get_data_window(np.ma.masked_array(mask_array, ~mask_array))
        self._watershed_window = window
        (row_start, row_stop), (col_start, col_stop) = window.toranges()
        self._watershed_mask_clipped = mask_array[row_start:row_stop, col_start:col_stop]

    @property
    def data_array_x_coords(self) -> np.ndarray:
        """
        Get the x coordinates of the data array.

        Returns
        -------
            np.ndarray: The x coordinates of the data array.
        """
        if not isinstance(self._data_array_x_coords, np.ndarray):
            self._data_array_x_coords = self.data_array[self.x_var].to_numpy()
        return self._data_array_x_coords

    @property
    def data_array_y_coords(self) -> np.ndarray:
        """
        Get the y coordinates of the data array.

        Returns
        -------
            np.ndarray: The y coordinates of the data array.
        """
        if not isinstance(self._data_array_y_coords, np.ndarray):
            self._data_array_y_coords = self.data_array[self.y_var].to_numpy()
        return self._data_array_y_coords

    @property
    def np_data_array(self) -> np.ndarray:
        """
        Get the data array as a numpy array.

        Returns
        -------
            np.ndarray: The data array as a numpy array.
        """
        if not isinstance(self._np_data_array, np.ndarray):
            self._np_data_array = self.data_array.to_numpy()
        return self._np_data_array

    @property
    def watershed_window(self) -> Window:
        """
        Get the window of the watershed in the data array.

        Returns
        -------
            Window: The window of the watershed in the data array.
        """
        if self._watershed_window is None:
            self._calculate_watershed_mask_and_window()
        return self._watershed_window

    @property
    def watershed_mask(self) -> np.ndarray:
        """
        Get the watershed mask as a 2D boolean numpy array.

        Returns
        -------
            np.ndarray: The watershed mask as a 2D boolean numpy array.
        """
        if not isinstance(self._watershed_mask, np.ndarray):
            self._calculate_watershed_mask_and_window()
        return self._watershed_mask

    @property
    def watershed_mask_clipped(self) -> np.ndarray:
        """
        Get the clipped watershed mask.

        Returns
        -------
            np.ndarray: The clipped watershed mask.
        """
        if not isinstance(self._watershed_mask_clipped, np.ndarray):
            self._calculate_watershed_mask_and_window()
        return self._watershed_mask_clipped

    @property
    def valid_shifts(self) -> list[tuple[int, int]]:
        """
        Calculate and return a list of valid shift values for the watershed mask.

        This method determines the valid shifts that can be applied to the watershed mask
        within the bounds of the data array. It iterates over possible shifts and checks
        if the shifted mask is still within the valid data region.

        Returns
        -------
            list[tuple[int, int]]: A list of tuples representing the valid (x, y) shifts.
        """
        if self._valid_shifts is None:
            original_window_row_slice, original_window_col_slice = self.watershed_window.toslices()
            shifts: list[tuple[int, int]] = []
            min_x_delta = 0 - self.watershed_window.col_off
            min_y_delta = 0 - self.watershed_window.row_off
            max_x_delta = self.width - (self.watershed_window.col_off + self.watershed_window.width)
            max_y_delta = self.height - (self.watershed_window.row_off + self.watershed_window.height)
            x_delta = min_x_delta
            y_delta = min_y_delta
            while x_delta <= max_x_delta:
                while y_delta <= max_y_delta:
                    adjusted_row_start = original_window_row_slice.start + y_delta
                    adjusted_row_stop = original_window_row_slice.stop + y_delta
                    adjusted_col_start = original_window_col_slice.start + x_delta
                    adjusted_col_stop = original_window_col_slice.stop + x_delta
                    data_clipped = self.np_data_array[
                        adjusted_row_start:adjusted_row_stop, adjusted_col_start:adjusted_col_stop
                    ]
                    data_mask = np.isfinite(data_clipped)
                    combined_mask = np.logical_and(self.watershed_mask_clipped, data_mask)
                    if np.array_equal(combined_mask, self.watershed_mask_clipped):
                        shifts.append((x_delta, y_delta))
                    y_delta += 1
                x_delta += 1
                y_delta = min_y_delta
            self._valid_shifts = shifts

        return self._valid_shifts

    @property
    def valid_spaces(self) -> np.ndarray:
        """
        Calculate and return the valid spaces mask.

        This method initializes the valid mask as the watershed mask value, iterates over
        the list of shift values, applies the shifts to the watershed mask, and performs
        a logical OR with the valid mask and the rolled watershed mask.

        Returns
        -------
            np.ndarray: The valid spaces mask as a boolean numpy array.
        """
        if not isinstance(self._valid_spaces, np.ndarray):
            valid_spaces = np.full(self.watershed_mask.shape, False, dtype=bool)
            for shift in self.valid_shifts:
                rolled = np.roll(self.watershed_mask, shift, axis=(1, 0))
                valid_spaces = np.logical_or(valid_spaces, rolled)
            self._valid_spaces = valid_spaces
        return self._valid_spaces

    def _array_to_polygon(self, arr: np.ndarray) -> Polygon:
        """
        Convert a boolean array to a geometry using the coordinates of the dataset.

        Args:
            arr (np.ndarray): The boolean array to convert.

        Returns
        -------
            Polygon: The resulting polygon.
        """
        shapely_shapes = [
            shape(converted_shape) for converted_shape, _ in shapes(arr.astype(np.ubyte), arr, transform=self.transform)
        ]
        if len(shapely_shapes) != 1:
            raise ValueError(f"Expected single geometry feature, got {len(shapely_shapes)}")
        valid_spaces_geom = shapely_shapes[0]
        if valid_spaces_geom.geom_type != "Polygon":
            raise TypeError(f"Expected geometry type 'Polygon', got {valid_spaces_geom.geom_type}")
        return valid_spaces_geom

    @property
    def valid_spaces_polygon(self) -> Polygon:
        """
        Convert the valid spaces boolean array to a polygon.

        Returns
        -------
            Polygon: The valid spaces polygon.
        """
        if self._valid_spaces_polygon is None:
            self._valid_spaces_polygon = self._array_to_polygon(self.valid_spaces)
        return self._valid_spaces_polygon

    def max_transpose(self, func: Callable[[np.ndarray], Any] | None = None) -> tuple[Polygon, Affine, Any | None]:
        """
        Calculate the maximum transpose of the watershed mask over the data array.

        This method initializes the max transpose array, max shift, and stats collection as None.
        It iterates over the list of shift values, applies the shifts to the watershed mask,
        calculates the stats, and if the stats collection has a greater mean than the max stats,
        it overwrites the max stats, max shift, and max transpose array.

        Args:
            func (Callable[[np.ndarray], Any] | None): A callable to apply to the data array.

        Returns
        -------
            tuple[Polygon, Affine, Any | None]: The resulting polygon, affine transformation, and results.
        """
        original_window_row_slice, original_window_col_slice = self.watershed_window.toslices()
        max_mean = None
        max_shift = None
        results = None
        for x_delta, y_delta in self.valid_shifts:
            adjusted_row_start = original_window_row_slice.start + y_delta
            adjusted_row_stop = original_window_row_slice.stop + y_delta
            adjusted_col_start = original_window_col_slice.start + x_delta
            adjusted_col_stop = original_window_col_slice.stop + x_delta
            data_clipped = self.np_data_array[
                adjusted_row_start:adjusted_row_stop, adjusted_col_start:adjusted_col_stop
            ]
            data_clipped_masked = np.ma.masked_array(data_clipped, ~self.watershed_mask_clipped)
            mean = np.nanmean(data_clipped_masked)
            if max_mean is None or mean > max_mean:
                max_mean = mean
                max_shift = (float(x_delta * self.x_cellsize), float(y_delta * self.y_cellsize))
                if func:
                    results = func(data_clipped_masked)
        poly = self._array_to_polygon(self.watershed_mask)
        poly = translate(poly, *max_shift)
        aff = Affine.translation(*max_shift)
        return poly, aff, results
