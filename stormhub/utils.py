"""Utility functions for stormhub."""

from __future__ import annotations

import json
import logging
import math
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List
import os
from pathlib import Path

from affine import Affine
import numpy as np
from pystac import Asset, Collection, Item, Link
from rasterio.crs import CRS
import rasterio.enums
import rasterio.warp
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
import xarray as xr

from stormhub.kerchunker import KerchunkConfig
from stormhub.met.consts import (
    DSS_TIME_DIMENSION,
    KM_TO_M_CONVERSION_FACTOR,
    NETCDF_ASSET_DESCRIPTION,
    NETCDF_ASSET_MEDIA_TYPE,
    NETCDF_ASSET_ROLES,
    NETCDF_TIME_BOUNDS,
    NETCDF_TIME_BOUNDS_SUFFIX,
    SHG_WKT,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stormhub.met.zarr_to_dss import NOAADataVariable


STORMHUB_REF_LINK = Link(
    rel="Processing",
    target="https://github.com/Dewberry/stormhub",
    title="Source Code",
    media_type="text/html",
    extra_fields={"Description": "Source code used to generate STAC objects"},
)


@dataclass(frozen=True)
class NetCDFConfig:
    """Configure NetCDF export and optional associated Kerchunk behavior."""

    write_netcdf: bool = False
    kerchunk_config: KerchunkConfig = field(default_factory=KerchunkConfig)

    def __post_init__(self) -> None:
        """Validate compatible NetCDF and Kerchunk settings."""
        if not self.write_netcdf and (
            self.kerchunk_config.make_individual_refs is not None
            or self.kerchunk_config.make_collection_ref is not None
        ):
            raise ValueError("Cannot request Kerchunking when write_netcdf is False.")


def add_storm_netcdf_asset(item: Item, netcdf_path: Path, netcdf_href: str) -> None:
    """Attach the storm NetCDF file as an asset on its STAC item."""
    item.add_asset(
        netcdf_path.name,
        Asset(
            netcdf_href,
            netcdf_path.name,
            description=NETCDF_ASSET_DESCRIPTION,
            media_type=NETCDF_ASSET_MEDIA_TYPE,
            roles=NETCDF_ASSET_ROLES,
        ),
    )


def is_port_in_use(port: int = 8080, host: str = "http://localhost") -> bool:
    """Check if a given port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except socket.error:
            return True


def load_config(config_file: str) -> dict:
    """Load a json config file."""
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: dict) -> dict:
    """Validate a config dictionary against required keys."""
    required_keys = {
        "watershed": ["id", "geometry_file", "description"],
        "transposition_region": ["id", "geometry_file", "description"],
    }

    for key, sub_keys in required_keys.items():
        if key not in config:
            raise ValueError(f"Missing required section: {key}")
        for sub_key in sub_keys:
            if sub_key not in config[key] or not config[key][sub_key]:
                raise ValueError(f"Missing value for {sub_key} in section {key}")
    return config


def generate_date_range(
    start_date: str, end_date: str, every_n_hours: int = 6, date_format: str = "%Y-%m-%d", months: List[int] = None
) -> List[datetime]:
    """Generate a list of datetime objects at a given interval between start and end dates."""
    if months is None:
        months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    start = datetime.strptime(start_date, date_format)
    end = datetime.strptime(end_date, date_format)

    date_range = []
    current_date = start
    while current_date <= end:
        if current_date.month in months:
            date_range.append(current_date)
            current_date += timedelta(hours=every_n_hours)

    return date_range


def create_feature_collection_from_items(
    collection: Collection, output_geojson: str, select_properties: str = "aorc:statistics"
):
    """Generate a geojson feature collection from a collection of STAC items."""
    features = []
    for item in collection.get_all_items():
        geom = shape(item.geometry)
        if geom.is_empty:
            continue

        feature = {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "id": item.id,
                select_properties: item.properties.get(select_properties),
                # **item.properties,
            },
        }
        features.append(feature)

    feature_collection = {"type": "FeatureCollection", "features": features}

    with open(output_geojson, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, indent=4)

    logging.info("FeatureCollection saved to %s", output_geojson)


class StacPathManager:
    """Build consistent paths for STAC items and collections assuming a top-level local catalog."""

    def __init__(self, local_catalog_dir: str):
        self._catalog_dir = os.path.abspath(local_catalog_dir)

    @property
    def catalog_dir(self):
        """Build Catalog directory path."""
        return self._catalog_dir

    @property
    def catalog_file(self):
        """Build Catalog file path."""
        return os.path.join(self._catalog_dir, "catalog.json")

    def storm_collection_id(self, duration: int) -> str:
        """Build storm collection id."""
        return f"{duration}hr-events"

    def catalog_item(self, item_id: str) -> str:
        """Build Catalog item path."""
        return os.path.join(self.catalog_dir, item_id, f"{item_id}.json")

    def catalog_asset(self, item_id: str, asset_dir: str = "hydro_domains") -> str:
        """Build Catalog asset path."""
        return os.path.join(self.catalog_dir, asset_dir, f"{item_id}.json")

    def collection_file(self, collection_id: str) -> str:
        """Build Collection file path."""
        return os.path.join(self.catalog_dir, collection_id, "collection.json")

    def collection_dir(self, collection_id: str) -> str:
        """Build Collection directory path."""
        return os.path.join(self.catalog_dir, collection_id)

    def collection_asset(self, collection_id: str, filename: str) -> str:
        """Build Collection asset path."""
        return os.path.join(self.catalog_dir, collection_id, filename)

    def collection_item_dir(self, collection_id: str, item_id: str) -> str:
        """Build Collection item directory path."""
        return os.path.join(self.catalog_dir, collection_id, item_id)

    def collection_item(self, collection_id: str, item_id: str) -> str:
        """Build Collection item path."""
        return os.path.join(self.catalog_dir, collection_id, item_id, f"{item_id}.json")

    def collection_item_asset(self, collection_id: str, item_id: str, filename: str) -> str:
        """Build Collection item asset path."""
        return os.path.join(self.catalog_dir, collection_id, item_id, filename)


def file_table(data: dict, col1: str, col2: str):
    """Convert a dictionary into a list of dictionaries, suitable for creating a table."""
    table = []
    for k, v in data.items():
        table.append({col1: k, col2: v})
    return table


def reproject_to_shg(
    data: xr.Dataset | xr.DataArray, output_resolution_km: int
) -> tuple[xr.Dataset | xr.DataArray, int, int]:
    """Reproject the xr object to SHG and return it with its snapped LLC indices.

    Lifted from: https://github.com/Dewberry/stormhub/blob/a654a87e94800e7d89c8248e946fac1dac594acc/stormhub/met/zarr_to_dss.py#L333-L352
    Then modified to use shared ``get_shg_reprojection_kwargs`` for proper snapping.
    """
    output_resolution_m = output_resolution_km * KM_TO_M_CONVERSION_FACTOR

    logging.info(f"reprojecting dataset")
    times = data.time.values
    reproject_kwargs, lower_x, lower_y = get_shg_reprojection_kwargs(data, output_resolution_m)

    if len(times) <= 144:
        data = data.rio.reproject(**reproject_kwargs)
    else:
        logging.info("Chunking dataset for reprojection")
        time_chunk_size = 144
        reprojected_chunks = []

        for i in range(0, len(times), time_chunk_size):
            chunk_times = times[i : i + time_chunk_size]
            chunk = data.sel(time=chunk_times)
            chunk = chunk.rio.reproject(**reproject_kwargs)
            reprojected_chunks.append(chunk)

        data = xr.concat(reprojected_chunks, dim="time")

    validate_shg(data)
    return data, lower_x, lower_y


def validate_shg(data: xr.Dataset | xr.DataArray) -> tuple[int, int]:
    """Validate that the xr object is SHG and return its LLC indices."""
    if data.rio.crs != CRS.from_wkt(SHG_WKT):
        raise ValueError(f"Expected SHG CRS {SHG_WKT}, got {data.rio.crs}.")

    resolution_x, resolution_y = data.rio.resolution()
    output_resolution_m = abs(resolution_x)
    if output_resolution_m <= 0 or not math.isclose(abs(resolution_y), output_resolution_m):
        raise ValueError(f"Expected square SHG pixels with positive resolution; got {data.rio.resolution()}.")

    shg_res_choices = (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000)
    for res in (resolution_x, resolution_y):
        if abs(res) not in shg_res_choices:
            raise ValueError(f"Resolution {abs(res)} is not allowed for SHG. Expected one of: {shg_res_choices}")

    _, lower_x, lower_y = get_shg_reprojection_kwargs(data, output_resolution_m)
    left, bottom, _, _ = data.rio.bounds()
    expected_left = lower_x * output_resolution_m
    expected_bottom = lower_y * output_resolution_m
    if not (
        math.isclose(left, expected_left, rel_tol=0, abs_tol=1e-6)
        and math.isclose(bottom, expected_bottom, rel_tol=0, abs_tol=1e-6)
    ):
        raise ValueError(
            f"Expected LLC to align to integer multiples of {output_resolution_m}. Expected ({expected_left}, {expected_bottom}) but got ({left}, {bottom})."
        )
    return lower_x, lower_y


def convert_xr_dataset_for_hec_hms_shg_nc(data: xr.Dataset, variables: List[NOAADataVariable]) -> xr.Dataset:
    """
    Transform an AORC xarray Dataset into a CF-1.9 compliant NetCDF compatible with HEC-HMS.

    Handles CRS promotion, grid_mapping attributes, variable renaming, CF standard attributes,
    and time bounds creation.

    Lifted (with some mods) from: https://github.com/Dewberry/stormhub/blob/fb040218c457165e2d9c321cb4f3d722bae0ce9f/stormhub/met/storm_catalog.py#L1317-L1374

    For PRECIPITATION, units "mm" is used instead of "kg m-2", for HMS/Vortex. According to the CF Standard Name Table,
    The "standard_name" should be "lwe_thickness_of_precipitation_amount", rather than "precipitation_amount", when a
    length unit is used for precipitation instead of a mass unit.  See: https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html

    For TEMPERATURE, HMS rejects "degrees_Celsius" when reading NetCDF directly.
    HMS accepts "degC", an equivalent UDUNITS alias. See: https://github.com/Unidata/UDUNITS-2/blob/main/lib/udunits2-common.xml#L78-L99

    Args:
        data (xr.Dataset): Dataset with spatial_ref coordinate (from rioxarray reproject).
        variables (List[NOAADataVariable]): The NOAA data variables present in the dataset.

    Returns
    -------
        xr.Dataset: CF-compliant dataset ready for NetCDF export.
    """
    # Rename spatial_ref to CF-compliant grid mapping name and move to data var
    data = data.rename({"spatial_ref": "crs"})
    data = data.reset_coords("crs")
    data["crs"].attrs["crs_wkt"] = SHG_WKT
    data["crs"].attrs["spatial_ref"] = SHG_WKT

    # Add grid_mapping to data variables
    for var in data.data_vars:
        data[var].attrs["grid_mapping"] = "crs"

    # Rename variables to standard names
    data = data.rename({v.value: v.dss_variable_title for v in variables})

    # Add CF attributes for precipitation
    if "PRECIPITATION" in data.data_vars:
        precip_units = data["PRECIPITATION"].attrs.get("units")
        if precip_units not in ("kg m-2", "kg/m^2", "mm"):
            raise ValueError(f"Expected precipitation in ('kg m-2', 'kg/m^2', 'mm') but got {precip_units!r}.")
        data["PRECIPITATION"].attrs.update(
            {"standard_name": "lwe_thickness_of_precipitation_amount", "cell_methods": "time: sum", "units": "mm"}
        )

    # Add CF attributes for temperature
    if "TEMPERATURE" in data.data_vars:
        temp_units = data["TEMPERATURE"].attrs.get("units")
        if temp_units != "degrees_Celsius":
            raise ValueError(f"Expected temperature in 'degrees_Celsius', got {temp_units!r}.")
        data["TEMPERATURE"].attrs.update({"standard_name": "air_temperature", "units": "degC"})

    # Time attributes
    data["time"].attrs = {
        "standard_name": "time",
        "long_name": "time",
        "axis": "T",
        "bounds": "time_bnds",
    }

    # Time bounds
    time_bnds = np.array([[t - np.timedelta64(1, "h"), t] for t in data["time"].values])

    data["time_bnds"] = xr.DataArray(
        time_bnds,
        dims=["time", "nv"],
        attrs={"long_name": "time bounds"},
    )

    data.attrs.update({"Conventions": "CF-1.9"})

    return data


def write_hec_hms_shg_nc(
    var_data_by_var: dict[NOAADataVariable, xr.DataArray],
    output_path: str | Path,
    output_resolution_km: int,
) -> None:
    """Write a HMS-complicant NetCDF with each variable's DSS-matched time range. Output data type: float32. Output chunking: 72x64x64 (72-hour x 64km x 64km when timestep is 1 hour and resolution is 1km).

    Lifted (with significant mods) from: https://github.com/Dewberry/stormhub/blob/fb040218c457165e2d9c321cb4f3d722bae0ce9f/stormhub/met/storm_catalog.py#L1429-L1441

    NOTE: The separate per-variable time coordinates handling here is to resolve the following :
        The source variables for PRECIPITATION and TEMPERATURE are both hourly, but their slice durations come from
        ``variable_duration_map``. Callers can request different lengths of each variable's time slice, also known as the duration of the slice.

        Example:
            noaa_zarr_to_dss(
                ...,
                variable_duration_map={
                    NOAADataVariable.TMP: 864,
                    NOAADataVariable.APCP: 72,
                }
            )

        A shared time coordinate pads the final precipitation timestamps with NaNs.
        **NOTE: then HMS/Vortex, when reading the NetCDF, may import those padded timestamps as extra precipitation DSS records.**

        Separate per-variable time coordinates and bounds prevent that padding and retain each slice's native
        duration. For example consider:
            Precipitation slice duration 1 hour, Temperature slice duration 3 hours.
            If both arrays instead share one ``time`` coordinate, xarray aligns them to the union of those timestamps
            and pads the shorter precipitation array at the trailing end:

            These padded NaNs may become extra DSS records when HMS/Vortex converts a NetCDF with that structure to a DSS.
            === BEFORE HANDLING ===
                time                 PRECIPITATION    TEMPERATURE
                2018-09-06 17:00      p1               c1
                2018-09-06 18:00      NaN              c2
                2018-09-06 19:00      NaN              c3

            After handling the variables' time axes separately, there are no padded NaN records:
            === AFTER HANDLING ===
                time                 PRECIPITATION    TEMPERATURE
                2018-09-06 17:00      p1               c1
                2018-09-06 18:00      --               c2
                2018-09-06 19:00      --               c3

            When no NaN is stored, HMS/Vortex has no extra precipitation timestamps to import.
    """
    output_data_type = "float32"

    if output_resolution_km <= 0:
        raise ValueError(f"Expected a positive output resolution, got {output_resolution_km}.")

    variables = list(var_data_by_var)
    # Build the per-variable time axes required to preserve DSS record ranges.
    data = xr.Dataset(
        {
            var.value: variable_data.rename({DSS_TIME_DIMENSION: var.netcdf_time_dimension})
            for var, variable_data in var_data_by_var.items()
        }
    )
    nc_datasets = []
    # lifted logic for float32, reprojection to SHG, and HMS/Vortex formatting (modded slightly to use true SHG WKT (SHG_WKT) instead of EPSG:5070).
    # Modded logic for time dimension name (using separate time axes for each variable).
    for var in variables:
        time_dimension = var.netcdf_time_dimension
        variable_data = data[var.value].rename({time_dimension: DSS_TIME_DIMENSION})
        variable_data, _, _ = reproject_to_shg(variable_data.astype(output_data_type), output_resolution_km)
        nc_dataset = convert_xr_dataset_for_hec_hms_shg_nc(xr.Dataset({var.value: variable_data}), [var])
        time_bounds = f"{time_dimension}{NETCDF_TIME_BOUNDS_SUFFIX}"
        nc_dataset = nc_dataset.rename({DSS_TIME_DIMENSION: time_dimension, NETCDF_TIME_BOUNDS: time_bounds})
        nc_dataset[time_dimension].attrs["bounds"] = time_bounds
        nc_datasets.append(nc_dataset)

    data = xr.merge(nc_datasets, compat="no_conflicts")
    # Lifted logic for compression, time units, and file-writing.
    # Modded logic for per-variable time axes.
    encoding = {}
    spatial_chunk_cells = max(1, 64 // output_resolution_km)
    for var in variables:
        variable_name = var.dss_variable_title
        variable_data = data[variable_name]
        encoding[variable_name] = {
            "zlib": True,
            "complevel": 6,
            "chunksizes": tuple(
                min(
                    variable_data.sizes[dimension],
                    72 if dimension == var.netcdf_time_dimension else spatial_chunk_cells,
                )
                for dimension in variable_data.dims
            ),
        }
    time_encoding = {"units": "hours since 1970-01-01"}
    for var in variables:
        time_dimension = var.netcdf_time_dimension
        encoding[time_dimension] = time_encoding
        encoding[f"{time_dimension}{NETCDF_TIME_BOUNDS_SUFFIX}"] = time_encoding
    logging.info("Writing: %s", output_path)
    data.to_netcdf(output_path, engine="h5netcdf", encoding=encoding)


def repair_polygon_fill_holes(geom: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    """Repair a Polygon or MultiPolygon by filling self-intersection holes (e.g. bowties) and true holes (inner rings). Return a Polygon or MultiPolygon.

    Shapely make_valid() fixes self-intersection / bowtie "holes" in the exterior ring,
    and must be called *before* discarding the true (inner ring) holes.

    Shapely make_valid() can return a Polygon, MultiPolygon, or GeometryCollection
    depending on the issues it encountered, so we need to inspect its returned object
    and discard non-polygon components of its returned object, and reconstruct either a
    single Polygon or a single MultiPolygon.

    During this loop, we keep only the ``part.exterior`` of each part to ensure
    that we discard inner rings, which are true holes.
    """
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise TypeError(f"Expected input AOI to be Polygon or MultiPolygon, but got: {geom.geom_type}")

    geom = make_valid(geom)

    polys = []
    parts_to_check = [geom]
    while parts_to_check:
        part = parts_to_check.pop()
        if part.geom_type == "Polygon":
            polys.append(Polygon(part.exterior))
        elif part.geom_type in ("MultiPolygon", "GeometryCollection"):
            parts_to_check.extend(part.geoms)
        else:
            logging.warning(
                f"in repair_polygon_fill_holes, discarding geometry of type {part.geom_type} after shapely make_valid()"
            )

    if not polys:
        raise TypeError(f"Expected polygonal area after make_valid, got: {geom.geom_type}.")

    geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)

    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise TypeError(f"Unexpected final geometry type after repairing: {geom.geom_type}.")
    if not geom.is_valid:
        raise ValueError(f"Final geometry is not valid after repairing: {geom.geom_type}")
    return geom


def get_shg_reprojection_kwargs(data: xr.Dataset | xr.DataArray, output_resolution_m: float) -> tuple[dict, int, int]:
    """Build a kwargs dict for rasterio reproject() to SHG. Handles validation, CRS transformation, and snapping to SHG grid.

    SHG coordinates must be snapped to an integer multiple.
    Also explicitly returns lower_x and lower_y for later SHG writing.
    Uses nearest resampling. Other forms of resampling would require coordination with users.
    For more details on resampling requirement, see docstring for ``write_to_dss``.
    """
    resamp_method = rasterio.enums.Resampling.nearest
    if resamp_method != rasterio.enums.Resampling.nearest:
        raise ValueError(
            f"Only nearest neighbor resampling is supported (Resampling.nearest), but got {resamp_method}."
        )

    if round(output_resolution_m) != output_resolution_m:
        raise ValueError(
            f"output_resolution_m must be an integer or a float that represents an integer, but got: {output_resolution_m}"
        )

    # Raw bounds in SHG CRS (not yet snapped to SHG grid).
    dst_xmin, dst_ymin, dst_xmax, dst_ymax = rasterio.warp.transform_bounds(data.rio.crs, SHG_WKT, *data.rio.bounds())

    # Finding the closest integer index, growing in each direction as needed.
    lower_x = int(math.floor(dst_xmin / output_resolution_m))
    lower_y = int(math.floor(dst_ymin / output_resolution_m))
    upper_x = int(math.ceil(dst_xmax / output_resolution_m))
    upper_y = int(math.ceil(dst_ymax / output_resolution_m))

    # Converting those integer indexes to global coordinates on SHG grid system.
    snapped_xmin = lower_x * output_resolution_m
    snapped_ymin = lower_y * output_resolution_m
    snapped_xmax = upper_x * output_resolution_m
    snapped_ymax = upper_y * output_resolution_m

    # array width = dx divided by resolution
    dst_width = int(round((snapped_xmax - snapped_xmin) / output_resolution_m))
    # array height = dy divided by resolution
    dst_height = int(round((snapped_ymax - snapped_ymin) / output_resolution_m))

    dst_transform = Affine(output_resolution_m, 0.0, snapped_xmin, 0.0, -output_resolution_m, snapped_ymax)
    reproject_kwargs = {
        "dst_crs": SHG_WKT,
        "shape": (dst_height, dst_width),
        "transform": dst_transform,
        "resampling": resamp_method,
    }
    return reproject_kwargs, lower_x, lower_y
