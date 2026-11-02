"""Read CONUS404 hourly data (HyTEST zarr on the OSN pod) and use it as a stormhub data source.

CONUS404 is on a 4 km Lambert Conformal Conic grid (dims `time`/`y`/`x`, meters). Variables are renamed to the
AORC names (`APCP_surface`, `TMP_2maboveground`) so the rest of stormhub (stats, DSS/NetCDF writers) is source
agnostic. Times are UTC; precip is the hour-ending accumulation, same convention as AORC.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterator

import geopandas as gpd
import pandas as pd
import rioxarray  # noqa: F401  (registers the `.rio` accessor)
import xarray as xr
from pyproj import CRS, Transformer
from pystac import Asset, MediaType
from shapely import Polygon
from shapely.ops import transform

from stormhub.met.aorc.aorc import AORCItem
from stormhub.met.consts import AORC_PRECIP_VARIABLE, AORC_TEMP_VARIABLE
from stormhub.met.transpose import Transpose
from stormhub.utils import repair_polygon_fill_holes

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class Conus404Source:
    """Location and variable names of a CONUS404 zarr store."""

    url: str
    endpoint_url: str
    precip_var: str
    temp_var: str
    precip_to_mm: float = 1.0  # e.g. 3600 for a precip rate in mm/s


CONUS404_HOURLY = Conus404Source(
    url="s3://hytest/conus404/conus404_hourly.zarr",
    endpoint_url="https://usgs.osn.mghpcc.org/",
    precip_var="PREC_ACC_NC",  # mm, accumulated over the prior 60 minutes
    temp_var="T2",  # K
)


def open_conus404(source: Conus404Source = CONUS404_HOURLY, max_connections: int = 64) -> xr.Dataset:
    """Lazily open CONUS404 precip and temperature, renamed to the AORC variable names, with the CRS set.

    Data is dask-backed with the store's chunking; nothing is downloaded until `load()`/`.compute()`.
    """
    ds = xr.open_zarr(
        source.url,
        zarr_format=2,
        consolidated=True,
        storage_options={
            "anon": True,
            "client_kwargs": {"endpoint_url": source.endpoint_url},
            # s3fs defaults to 10 HTTP connections, which caps dask's parallel chunk reads.
            "config_kwargs": {"max_pool_connections": max_connections},
        },
    )
    precip = ds[source.precip_var]
    if source.precip_to_mm != 1.0:
        precip = precip * source.precip_to_mm
    precip.attrs["units"] = "mm"

    out = xr.Dataset({AORC_PRECIP_VARIABLE: precip, AORC_TEMP_VARIABLE: ds[source.temp_var]})
    # Drop 2D lat/lon and the source `crs` grid-mapping variable; `rio.write_crs` adds a standard `spatial_ref`
    # that survives reductions like `.sum("time")`.
    out = out.drop_vars([c for c in ("lat", "lon", "crs") if c in out.coords])
    for var in out.data_vars:
        out[var].attrs.pop("grid_mapping", None)
        out[var].encoding.pop("grid_mapping", None)
    return out.rio.write_crs(ds["crs"].attrs["crs_wkt"])


def reproject_geometry(geom: Any, src_crs: Any, dst_crs: Any) -> Any:
    """Reproject a shapely geometry between any two CRS definitions (EPSG string, WKT, pyproj/rasterio CRS)."""
    transformer = Transformer.from_crs(CRS.from_user_input(src_crs), CRS.from_user_input(dst_crs), always_xy=True)
    return transform(transformer.transform, geom)


def subset_conus404(ds: xr.Dataset, geometry: Any, start: datetime, end: datetime) -> xr.Dataset:
    """Lazily subset to an EPSG:4326 geometry and the hour-ending steps in (start, end]."""
    geom = repair_polygon_fill_holes(reproject_geometry(geometry, WGS84, ds.rio.crs))
    cell = abs(float(ds.x[1] - ds.x[0]))  # pad by one cell so `all_touched` keeps edge cells
    minx, miny, maxx, maxy = geom.bounds
    subset = ds.sel(
        time=slice(start + timedelta(hours=1), end),
        x=slice(minx - cell, maxx + cell),
        y=slice(miny - cell, maxy + cell),
    )
    return subset.rio.clip([geom], drop=True, all_touched=True)


def group_by_month(dates: list[datetime]) -> list[list[datetime]]:
    """Group dates into one sorted list per calendar month."""
    groups: dict[tuple[int, int], list[datetime]] = {}
    for date in sorted(dates):
        groups.setdefault((date.year, date.month), []).append(date)
    return list(groups.values())


def iter_precip_sums(
    starts: list[datetime], duration_hours: int, geometry: Any, source: Conus404Source = CONUS404_HOURLY
) -> Iterator[tuple[datetime, xr.Dataset]]:
    """Yield `(start, precip summed over (start, start + duration])` for each start.

    Hourly data for each month of starts is downloaded once (dask parallel reads) and every window in that
    month is summed in memory, so storms that run into the next month are handled without re-reading.
    Peak memory is about one month (+ duration) of hourly data over the geometry's bbox.
    """
    ds = open_conus404(source)[[AORC_PRECIP_VARIABLE]]
    first_hour = pd.Timestamp(ds.time.values[0]).to_pydatetime()
    last_hour = pd.Timestamp(ds.time.values[-1]).to_pydatetime()
    duration = timedelta(hours=duration_hours)

    for month_starts in group_by_month(starts):
        valid = [s for s in month_starts if s + timedelta(hours=1) >= first_hour and s + duration <= last_hour]
        for s in set(month_starts) - set(valid):
            logging.warning("Skipping %s: outside CONUS404 period %s - %s", s, first_hour, last_hour)
        if not valid:
            continue

        hourly = subset_conus404(ds, geometry, valid[0], valid[-1] + duration).load()
        for start in valid:
            window = hourly.sel(time=slice(start + timedelta(hours=1), start + duration))
            yield start, window.sum(dim="time", skipna=True, min_count=1)
        del hourly


def valid_spaces_polygon(
    watershed: Polygon,
    transposition_region: Polygon,
    storm_duration: int = 72,
    source: Conus404Source = CONUS404_HOURLY,
) -> Polygon:
    """Return the EPSG:4326 area the watershed can be transposed within, on the CONUS404 grid.

    Same approach as `stormhub.met.aorc.aorc.valid_spaces_item`, using a sample window starting 1980-05-01.
    """
    start = datetime(1980, 5, 1)
    ds = open_conus404(source)[[AORC_PRECIP_VARIABLE]]
    subset = subset_conus404(ds, transposition_region, start, start + timedelta(hours=storm_duration))
    precip_sum = subset[AORC_PRECIP_VARIABLE].sum(dim="time", skipna=True, min_count=1).compute()
    transpose = Transpose(
        precip_sum,
        reproject_geometry(watershed, WGS84, ds.rio.crs),
        Conus404Item.X_VAR,
        Conus404Item.Y_VAR,
        step=Conus404Item.TRANSPOSE_STEP,
    )
    return reproject_geometry(transpose.valid_spaces_polygon, ds.rio.crs, WGS84)


def fetch_conus404_data(
    storm_start: datetime,
    variable_duration_map: dict,
    aoi_geometry_path: str,
    source: Conus404Source = CONUS404_HOURLY,
) -> xr.Dataset:
    """Lazily fetch CONUS404 data for a storm, clipped to the AOI. Drop-in for `zarr_to_dss.fetch_aorc_data`.

    Args:
        storm_start: The start datetime of the storm (exclusive; first step is start + 1 hour).
        variable_duration_map: Mapping of `NOAADataVariable` (APCP and/or TMP) to durations in hours.
        aoi_geometry_path: Path to a geojson/geopackage with a single AOI geometry.
        source: The CONUS404 store to read.
    """
    variables = [v.value for v in variable_duration_map]
    unsupported = set(variables) - {AORC_PRECIP_VARIABLE, AORC_TEMP_VARIABLE}
    if unsupported:
        raise ValueError(
            f"CONUS404 supports only {AORC_PRECIP_VARIABLE} and {AORC_TEMP_VARIABLE}, got {sorted(unsupported)}."
        )
    aoi_gdf = gpd.read_file(aoi_geometry_path)
    if len(aoi_gdf.geometry) != 1:
        raise ValueError(f"AOI geometry has {len(aoi_gdf.geometry)} parts, expected 1.")
    geometry = aoi_gdf.to_crs(WGS84).geometry.iloc[0]
    end = storm_start + timedelta(hours=max(variable_duration_map.values()))

    logging.info("Getting CONUS404 data")
    return subset_conus404(open_conus404(source)[variables], geometry, storm_start, end)


class Conus404Item(AORCItem):
    """Storm item backed by CONUS404. Transposition runs on the native 4 km grid; STAC geometry is EPSG:4326.

    A 1-cell (4 km) transposition step matches the ~4 km step AORC uses (4 cells at ~1 km).
    """

    DATA_SOURCE = "conus404"
    X_VAR = "x"
    Y_VAR = "y"
    TRANSPOSE_STEP = 1
    SOURCE = CONUS404_HOURLY

    def _load_source_data(self) -> xr.Dataset:
        """Lazily read CONUS404 precip over the transposition domain for the storm window and add a data asset."""
        ds = open_conus404(self.SOURCE)[[self.PRECIP_VAR]]
        data = subset_conus404(ds, self.transposition_domain_geometry, self.start_datetime, self.end_datetime)
        self.add_asset(
            "CONUS404",
            Asset(
                self.SOURCE.url,
                media_type=MediaType.ZARR,
                roles=["data"],
                extra_fields={
                    "xarray:storage_options": {"anon": True, "client_kwargs": {"endpoint_url": self.SOURCE.endpoint_url}}
                },
            ),
        )
        return data

    def _to_data_crs(self, geom: Any) -> Any:
        """Convert an EPSG:4326 geometry to the CONUS404 grid CRS."""
        return reproject_geometry(geom, WGS84, self.sum_aorc.rio.crs)

    def _to_wgs84(self, geom: Any) -> Any:
        """Convert a CONUS404 grid CRS geometry to EPSG:4326."""
        return reproject_geometry(geom, self.sum_aorc.rio.crs, WGS84)
