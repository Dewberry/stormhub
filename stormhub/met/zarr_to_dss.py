"""Create dss from aorc zarr data."""

from datetime import datetime, timedelta
from enum import Enum
import math
from typing import List, Tuple, Literal
from affine import Affine
from hecdss import HecDss, gridded_data
import numpy as np
from pandas import Timestamp
import geopandas as gpd
from geopandas import GeoDataFrame
import s3fs
import xarray as xr
from stormhub.met.consts import NOAA_AORC_S3_BASE_URL, KM_TO_M_CONVERSION_FACTOR, SHG_WKT


class MeasurementType(Enum):
    """Type of measurements."""

    PERCUM = "per_cum"
    INSTVAL = "inst_val"


class DSSPath:
    """Class for defining DSS paths."""

    def __init__(self, a_part: str, b_part: str, c_part: str, d_part: str, e_part: str, f_part: str):
        """
        Parameter descriptions from: https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/introduction/general-concepts-for-hec-dss.

        Args:
            a_part (str): Refers to the grid reference system. At present, GageInterp supports only the HRAP and SHG grid systems
            b_part (str): Contains the name of the region covered by the grid
            c_part (str): Refers to the parameter represented by the grid
            d_part (str): Contains the start time
            e_part (str): Contains the end time
            f_part (str): Refers to the version of the data
        """
        self.a_part = a_part
        self.b_part = b_part
        self.c_part = c_part
        self.d_part = d_part
        self.e_part = e_part
        self.f_part = f_part

    def __str__(self) -> str:
        """Return the DSS path string."""
        return f"/{self.a_part}/{self.b_part}/{self.c_part}/{self.d_part}/{self.e_part}/{self.f_part}/"


class NOAADataVariable(Enum):
    """Class of potential NOAA data variables to extract zarr data for."""

    APCP = "APCP_surface"
    DLWRF = "DLWRF_surface"
    DSWRF = "DSWRF_surface"
    PRES = "PRES_surface"
    SPFH = "SPFH_2maboveground"
    TMP = "TMP_2maboveground"
    UGRD = "UGRD_10maboveground"
    VGRD = "VGRD_10maboveground"

    @property
    def dss_variable_title(self) -> str:
        """Return variable title."""
        if self == NOAADataVariable.APCP:
            return "PRECIPITATION"
        elif self == NOAADataVariable.TMP:
            return "TEMPERATURE"
        else:
            return self.value

    @property
    def measurement_type(self) -> MeasurementType:
        """Return measurement type."""
        if self == NOAADataVariable.APCP:
            return MeasurementType.PERCUM
        else:
            return MeasurementType.INSTVAL

    @property
    def measurement_unit(self) -> str:
        """Return measurement units."""
        if self == NOAADataVariable.APCP:
            return "MM"
        elif self == NOAADataVariable.TMP:
            return "DEG C"
        else:
            raise NotImplementedError(f"Unit unknown for data variable {self.__repr__}")


def get_aorc_paths(storm_start: datetime, storm_end: datetime) -> list[str]:
    """Construct s3 paths for AORC dataset given storm start and end time."""
    aorc_paths = []
    if storm_start.year == storm_end.year:
        aorc_paths.append(f"{NOAA_AORC_S3_BASE_URL}/{storm_start.year}.zarr")
    else:
        for year in range(storm_start.year, storm_end.year + 1):  # plus one since end range is exclusive
            aorc_paths.append(f"{NOAA_AORC_S3_BASE_URL}/{year}.zarr")
    return aorc_paths


def date_range_dss_path_format(date: datetime, measurement_type: MeasurementType) -> Tuple[str, str]:
    """Format start and end times for DSS path based on a date and measurement type."""
    if measurement_type == MeasurementType.PERCUM:
        end_dt = date
        start_dt = end_dt - timedelta(hours=1)
        start_dt_str = start_dt.strftime("%d%b%Y:%H%M").upper()

        if end_dt.hour == 0 and end_dt.minute == 0:
            end_dt_str = start_dt.strftime("%d%b%Y:2400").upper()
        else:
            end_dt_str = end_dt.strftime("%d%b%Y:%H%M").upper()
    elif measurement_type == MeasurementType.INSTVAL:
        start_dt = date
        if start_dt.hour == 0 and start_dt.minute == 0:
            start_dt -= timedelta(days=1)
            start_dt_str = start_dt.strftime("%d%b%Y:2400").upper()
        else:
            start_dt_str = start_dt.strftime("%d%b%Y:%H%M").upper()
        end_dt_str = ""
    else:
        raise NotImplementedError(
            f"Start and end time definition from a single datetime is not defined for {measurement_type}."
        )

    return start_dt_str, end_dt_str


def get_lower_left_xy(
    data: xr.Dataset, resolution: int, x_coord_of_grid_cell_zero=0, y_coord_of_grid_cell_zero=0
) -> Tuple[int, int]:
    """Get lower left xy from gridded data."""
    y_coords = data.y.to_numpy()
    x_coords = data.x.to_numpy()

    y_coord = y_coords[-1] if y_coords[-1] < y_coords[0] else y_coords[0]
    x_coord = x_coords[-1] if x_coords[-1] < x_coords[0] else x_coords[0]

    affine_transform = Affine(resolution, 0.0, x_coord, 0.0, resolution, y_coord)

    cellsize = affine_transform[0]

    xmin = affine_transform[2] - x_coord_of_grid_cell_zero
    ymax = affine_transform[5] - y_coord_of_grid_cell_zero

    lower_left_x = int(math.floor(xmin / cellsize))
    lower_left_y = int(math.floor(ymax / cellsize))

    return (lower_left_x, lower_left_y)


def convert_temperature_dataset(data: xr.Dataset) -> xr.Dataset:
    """Convert temperature in Kelvin to the desired output_unit."""
    output_unit = NOAADataVariable.TMP.measurement_unit
    data_unit = data.units
    if data_unit != "K":
        raise ValueError(f"Expected temperature data in Kelvin, got measurement unit of {data_unit} instead")
    if output_unit != "K":
        data_shape = data.shape
        c_degrees_difference = np.full(data_shape, 273.15)
        if output_unit == "DEG C":
            data = np.subtract(data, c_degrees_difference)
        elif output_unit == "DEG F":
            c_data = np.subtract(data, c_degrees_difference)
            scale_difference = np.full(data_shape, 9 / 5)
            scale_data = np.multiply(c_data, scale_difference)
            f_difference = np.full(data_shape, 32)
            f_data = np.add(scale_data, f_difference)
            data = f_data
        else:
            raise ValueError(
                f"Temperature conversion only supported from Kelvin (K) to Celsius (DEG C) or Farenheit (DEG F); got output unit of {output_unit} instead"
            )
    return data


def create_gridded_data(
    path: DSSPath,
    data: np.ndarray,
    grid_type: Literal[
        "undefined_grid_with_time",
        "undefined_grid",
        "hrap_grid_with_time_ref",
        "hrap_grid",
        "albers_with_time_ref",
        "albers",
        "specified_grid_with_time_ref",
        "specified_grid",
    ],
    data_type: Literal["per_aver", "per_cum", "inst_val", "inst_cum", "freq", "invalid"],
    cell_size: float,
    data_units: str,
    srs_definition: str,
    lower_left_cell_x: int,
    lower_left_cell_y: int,
    x_coord_of_grid_cell_zero: float = 0,
    y_coord_of_grid_cell_zero: float = 0,
) -> gridded_data.GriddedData:
    """
    Create a gridded_data.GriddedData object from the HecDss library. Specifies default values for some parameters of GriddedData.

    Args:
        path: Path following the /part_a/part_b/part_c/part_d/part_e/part_f/ format
        data: A numpy array containing the gridded data values
        grid_type: The type of grid to use to display this data
        data_type: The measurement type of the data stored in the grid
        cell_size: The size of each grid cell
        data_units: The unit of measurement for the data
        srs_definition: The spatial reference system definition (either WKT or EPSG code)
        lower_left_cell_x: The x-coordinate index of the lower-left cell in the grid
        lower_left_cell_y: The y-coordinate index of the lower-left cell in the grid
    """
    number_of_ranges: int = 0
    time_zone_raw_offset: int = 0
    is_interval: int = 0
    is_time_stamped: int = 0
    data_source: str = ""
    srs_definition_type: int = 0
    srs_name: str = "WKT"
    time_zone_id: str = ""
    null_value: float = 0

    grid_type_map = {
        "undefined_grid_with_time": 400,
        "undefined_grid": 401,
        "hrap_grid_with_time_ref": 410,
        "hrap_grid": 411,
        "albers_with_time_ref": 420,
        "albers": 421,
        "specified_grid_with_time_ref": 430,
        "specified_grid": 431,
    }
    data_type_map = {"per_aver": 0, "per_cum": 1, "inst_val": 2, "inst_cum": 3, "freq": 4, "invalid": 5}

    gd = gridded_data.GriddedData.create(
        path=str(path),
        type=grid_type_map[grid_type],
        dataType=data_type_map[data_type],
        lowerLeftCellX=lower_left_cell_x,
        lowerLeftCellY=lower_left_cell_y,
        numberOfRanges=number_of_ranges,
        srsDefinitionType=srs_definition_type,
        timeZoneRawOffset=time_zone_raw_offset,
        isInterval=is_interval,
        isTimeStamped=is_time_stamped,
        dataUnits=data_units,
        dataSource=data_source,
        srsName=srs_name,
        srsDefinition=srs_definition,
        timeZoneID=time_zone_id,
        cellSize=cell_size,
        xCoordOfGridCellZero=x_coord_of_grid_cell_zero,
        yCoordOfGridCellZero=y_coord_of_grid_cell_zero,
        nullValue=null_value,
        data=data,
    )

    return gd


def get_s3_zarr_data(
    s3_paths: List[str], aoi_gdf: GeoDataFrame, start_dt: datetime, end_dt: datetime, variables_of_interest: List[str]
) -> xr.Dataset:
    """
    Read a multifile dataset from the specified S3 paths, filters it based on the area of interest (AOI) and the time range, extracts only the variables of interest and returns an xarray Dataset.

    Args:
        s3_paths: A list of S3 paths where the Zarr data is stored.
        aoi_gdf: A GeoDataFrame containing the area of interest. Only the first entry is used, and should be a polygon or multipolygon geometry.
        start_dt: The start datetime to filter the data.
        end_dt: The end datetime to filter the data.
        variables_of_interest: A list of variables to select from the dataset. If empty, all variables will be read.
    """
    s3 = s3fs.S3FileSystem(anon=True)
    fileset = [s3fs.S3Map(root=path, s3=s3, check=False) for path in s3_paths]
    ds = xr.open_mfdataset(fileset, engine="zarr", chunks="auto", consolidated=True)

    # subset data to only the variables
    if variables_of_interest:
        ds = ds[variables_of_interest]

    # reproject aoi to crs of dataset
    aoi_gdf = aoi_gdf.to_crs(ds.rio.crs)
    aoi_shape = aoi_gdf.geometry.iloc[0]

    # get a rough subsection of the dataset based on time and aoi in order to reduce it's size
    # this results in a speed improvement for rio.clip if the xarray.Dataset is sufficiently sized
    bounds = aoi_shape.bounds
    ds = ds.sel(
        time=slice(start_dt, end_dt), longitude=slice(bounds[0], bounds[2]), latitude=slice(bounds[1], bounds[3])
    )

    # clip ds to exact shape
    ds = ds.rio.clip([aoi_shape], drop=True, all_touched=True)

    return ds


def write_to_dss(
    output_dss_path: str,
    data: xr.Dataset,
    aoi_name: str,
    param_name: str,
    param_measurement_type: MeasurementType,
    param_measurement_unit: str,
    output_resolution_km: int,
    data_version: str,
):
    """
    Write geospatial data to a DSS file while transforming the data to fit DSS conventions.

    Args:
        output_dss_path: Path to the output DSS file
        zarr_data: An xarray dataset containing the geospatial data to be written to the DSS file
        aoi_name: The name of the area of interest (AOI)
        parameter_name: The name of the parameter being stored in the DSS file (e.g. "precipitation")
        parameter_measurement_type: The type of measurement type of the parameter
        output_resolution_km: The resolution for the data in km
        data_version: Represents where the data comes from (e.g. "AORC")
    """
    dss = HecDss(output_dss_path)
    output_resolution_m = output_resolution_km * KM_TO_M_CONVERSION_FACTOR
    data: xr.DataArray = data.rio.reproject(SHG_WKT, resolution=output_resolution_m)
    lower_x, lower_y = get_lower_left_xy(data, output_resolution_m)

    for time_step in data.time:
        time_step_data = data.sel(time=time_step)
        time_step_data = np.flipud(time_step_data.to_numpy())

        date = Timestamp(time_step.values).to_pydatetime()
        start_dt_str, end_dt_str = date_range_dss_path_format(date, param_measurement_type)

        path = DSSPath(
            f"SHG{output_resolution_km}K",
            aoi_name.upper(),
            param_name.upper(),
            start_dt_str,
            end_dt_str,
            data_version.upper(),
        )

        gd = create_gridded_data(
            path=path,
            data=time_step_data,
            grid_type="albers_with_time_ref",
            data_type=param_measurement_type.value,
            cell_size=output_resolution_m,
            data_units=param_measurement_unit,
            srs_definition=SHG_WKT,
            lower_left_cell_x=lower_x,
            lower_left_cell_y=lower_y,
        )

        dss.put(gd)

    dss.close()


def noaa_zarr_to_dss(
    output_dss_path: str,
    aoi_geometry_gpkg_path: str,
    aoi_name: str,
    storm_start: datetime,
    storm_duration: int,
    variables_of_interest: List[NOAADataVariable],
):
    """Given a geometry and datetime information about a storm, writes variables of interest from NOAA dataset to DSS."""
    # arrange parameters
    aoi_gdf = gpd.read_file(aoi_geometry_gpkg_path)
    storm_end = storm_start + timedelta(hours=storm_duration)
    storm_start += timedelta(hours=1)  # do this to make start time exclusive
    aorc_paths = get_aorc_paths(storm_start, storm_end)
    voi_keys = [voi.value for voi in variables_of_interest]

    # get aorc data
    aorc_data = get_s3_zarr_data(aorc_paths, aoi_gdf, storm_start, storm_end, voi_keys)

    # write to dss
    for data_variable in variables_of_interest:
        data = aorc_data[data_variable.value]
        if data_variable == NOAADataVariable.TMP:
            data = convert_temperature_dataset(data)
        write_to_dss(
            output_dss_path,
            data=aorc_data[data_variable.value],
            aoi_name=aoi_name,
            param_name=data_variable.dss_variable_title,
            param_measurement_type=data_variable.measurement_type,
            param_measurement_unit=data_variable.measurement_unit,
            output_resolution_km=1,
            data_version="AORC",
        )
