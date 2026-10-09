"""Minimal utilities to edit an existing HMS model to use stormhub forcing files and run it.

Symbols are organized roughly in the order in which they care called by the test routines.
Common argument ``model: Path`` refers to the directory of a HMS project.
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import xarray as xr
from conftest import Scalar, ScalarComp
from hec_hms_integration import constants as c
from hecdss import HecDss

from stormhub.met.consts import DSS_TIME_DIMENSION
from stormhub.met.zarr_to_dss import (
    NOAADataVariable,
    noaa_zarr_to_dss,
    write_to_dss,
)


def extract_model(target_dir: Path) -> Path:
    """Extract the model zip to the provided target dir, validate that the .hms file exists, and return the path to the model dir."""
    logging.info(f"Unzipping: {c.ORIG_MODEL_ZIP} -> {target_dir}")
    with ZipFile(c.ORIG_MODEL_ZIP) as archive:
        archive.extractall(target_dir)
    project_file = target_dir / c.ORIG_MODEL_SUBDIR / c.PROJECT_NAME / c.PROJECT_FILENAME
    if not project_file.is_file():
        raise FileNotFoundError(project_file)
    model = project_file.parent
    return model


def run_model_assert_success(model: Path) -> None:
    """Run the HMS model and assert that it succeeds."""
    success, diagnostics = _run_model(model)
    assert success, diagnostics


def run_model_assert_failure(model: Path) -> None:
    """Run the HMS model and assert that it fails."""
    success, diagnostics = _run_model(model)
    assert not success, diagnostics
    assert "ERROR" in diagnostics and "precip" in diagnostics.lower(), diagnostics


def deprecate_model_met_forcing_data_files(model: Path) -> None:
    """Rename both of the meteorological forcing data files files (precip.dss and temp.dss) and disallow missing data in the .met file."""
    met_file = model / c.CONFIG_MET_FILENAME
    for basename in (c.DATA_PRECIP_FILENAME_ORIG, c.DATA_TEMP_FILENAME_ORIG):
        path = model / basename
        new_path = path.with_stem(f"{path.stem}_deprecated")
        logging.info(f"Renaming: {path} -> {new_path}")
        path.rename(new_path)

    logging.info(f"Reading: {met_file}")
    content_orig = met_file.read_text()

    logging.info(f"Writing with {c.CONFIG_MET_MISSING_DATA_TOLERANT_NO!r}: {met_file}")
    met_file.write_text(
        content_orig.replace(c.CONFIG_MET_MISSING_DATA_TOLERANT_YES, c.CONFIG_MET_MISSING_DATA_TOLERANT_NO)
    )


def write_stormhub_dss(model: Path) -> None:
    """Use the stormhub library to fetch AORC data and write it to a dss file for HMS ingest."""
    aoi_file = _write_stormhub_input_aoi_polygon(model)
    noaa_zarr_to_dss(
        output_dss_path=str(model / c.DATA_MET_FORCING_STORMHUB),
        aoi_geometry_gpkg_path=str(aoi_file),
        aoi_name=c.PROJECT_NAME,
        storm_start=c.STORMHUB_START_DATETIME,
        output_resolution_km=c.PIXEL_RESOLUTION_KM,
        variable_duration_map={
            NOAADataVariable.APCP: c.STORMHUB_DURATION_HOURS,
            NOAADataVariable.TMP: c.STORMHUB_DURATION_HOURS,
        },
        add_nc=True,
    )


def stormhub_netcdf_to_stormhub_dss(
    netcdf_path: Path,
    output_dss_path: Path,
    aoi_name: str,
    output_resolution_km: int,
) -> None:
    """Write SHG NetCDF precipitation and temperature grids to DSS with hecdss."""
    with xr.open_dataset(netcdf_path, engine="h5netcdf") as source:
        data = source.load()

    crs_wkt = data["crs"].attrs["crs_wkt"]
    for var in (NOAADataVariable.APCP, NOAADataVariable.TMP):
        variable_data = data[var.dss_variable_title]
        nc_time_dimension = var.netcdf_time_dimension
        if nc_time_dimension in variable_data.dims:
            variable_data = variable_data.rename({nc_time_dimension: DSS_TIME_DIMENSION})
        variable_data = variable_data.rio.set_spatial_dims(x_dim="x", y_dim="y").rio.write_crs(crs_wkt)
        write_to_dss(
            output_dss_path=str(output_dss_path),
            data=variable_data,
            aoi_name=aoi_name,
            param_name=var.dss_variable_title,
            param_measurement_type=var.measurement_type,
            param_measurement_unit=var.measurement_unit,
            output_resolution_km=output_resolution_km,
            data_version="AORC",
            data_already_shg=True,
        )


def configure_model_to_use_stormhub_met_forcing(model: Path, resolution_km: float) -> None:
    """Alter the HMS .grid file and .met file to use a stormhub output file for meteorological forcing.

    First, replace strings like this in the .grid file:

        === BEFORE ===

        Grid: QPE
            Grid: QPE
            Grid Type: Precipitation
            Filename: data/precip.dss
            Pathname: ///PRECIPITATION/31AUG2018:2300/31AUG2018:2400//
        End:

        Grid: RTMA
            Grid: RTMA
            Grid Type: Temperature
            Filename: data/temp.dss
            Pathname: ///TEMPERATURE/31AUG2018:2400///
        End:

        === AFTER ===

        Grid: AORC-APCP_surface
            Grid: AORC-APCP_surface
            Grid Type: Precipitation
            Filename: data/met_forcing_stormhub.dss
            Pathname: /SHG2.0K/PUNX/PRECIPITATION///AORC/
        End:

        Grid: AORC-TMP_2maboveground
            Grid: AORC-TMP_2maboveground
            Grid Type: Temperature
            Filename: data/met_forcing_stormhub.dss
            Pathname: /SHG2.0K/PUNX/TEMPERATURE///AORC/
        End:

    Then, replace strings like this in the .met file:

        === BEFORE ===

        Precip Method Parameters: Gridded Precipitation
            Precip Grid Name: QPE
        End:

        Air Temperature Method Parameters: Grid
            Temperature Grid Name: RTMA
        End:

        === AFTER ===

        Precip Method Parameters: Gridded Precipitation
            Precip Grid Name: AORC-APCP_surface
        End:

        Air Temperature Method Parameters: Grid
            Temperature Grid Name: AORC-TMP_2maboveground
        End:

    """
    grid_file = model / c.CONFIG_GRID_FILENAME
    met_file = model / c.CONFIG_MET_FILENAME
    precip_grid_name = f"AORC-{NOAADataVariable.APCP.value}"
    temperature_grid_name = f"AORC-{NOAADataVariable.TMP.value}"
    logging.info(f"About to edit {grid_file} and {met_file} to use stormhub dss for Precipitation and Temperature")

    # Update .grid file
    grid_updates = [
        {
            "find_grid_type": "Precipitation",
            "new_gridname": precip_grid_name,
            "new_filename": c.DATA_MET_FORCING_STORMHUB,
            "new_pathname": f"/SHG{resolution_km}K/{c.PROJECT_NAME.upper()}/PRECIPITATION///AORC/",
        },
        {
            "find_grid_type": "Temperature",
            "new_gridname": temperature_grid_name,
            "new_filename": c.DATA_MET_FORCING_STORMHUB,
            "new_pathname": f"/SHG{resolution_km}K/{c.PROJECT_NAME.upper()}/TEMPERATURE///AORC/",
        },
    ]
    logging.info(f"Reading: {grid_file}")
    content = grid_file.read_text()
    for kwargs in grid_updates:
        content = _update_grid_file_block(content, **kwargs)
    logging.info(f"Writing: {grid_file}")
    grid_file.write_text(content)
    del content

    # Update the .met file
    logging.info(f"Reading: {met_file}")
    content = met_file.read_text()
    for prefix, grid_name in (
        ("Precip", precip_grid_name),
        ("Temperature", temperature_grid_name),
    ):
        content = re.sub(
            rf"^     {prefix} Grid Name: [^\r\n]*$",
            f"     {prefix} Grid Name: {grid_name}",
            content,
            flags=re.MULTILINE,
        )
    logging.info(f"Writing: {met_file}")
    met_file.write_text(content)
    del content


def check_hms_results(model: Path, comp_label: str) -> ScalarComp:
    """Validate HMS results and return their summary statistics as a ScalarComp instance for comparing model behavior before and after."""
    scalars: list[Scalar] = []
    for param in c.HMS_PARAMETERS_TO_COMPARE:
        values = np.asarray(_result_values(model, param))
        if not np.isfinite(values).all() and (values >= 0).all() and (values > 0).any():
            raise ValueError(f"Unexpected non-finite or negative values for param {param}: {values}")
        for np_method in c.NP_STATS_METHODS_TO_COMPARE:
            value = float(getattr(np, f"nan{np_method}")(values))
            logging.info("Parameter %s for %s: %s=%s for model %s", param, comp_label, np_method, value, model)
            scalars.append(Scalar(param, np_method, value))
    scalar_comp = ScalarComp(comp_label, scalars)
    return scalar_comp


def _run_model(model: Path) -> tuple[bool, str]:
    """Write a HMS .script JythonHms file, run it, and return info on status and diagnostics."""
    # Delete log file
    log_file = model / c.DATA_LOG_FILENAME
    logging.info(f"Deleting if exists: {log_file}")
    log_file.unlink(missing_ok=True)
    # Delete DSS results file
    logging.info(f"Deleting if exists: {model / c.DATA_RESULTS_FILENAME}")
    (model / c.DATA_RESULTS_FILENAME).unlink(missing_ok=True)

    # Write the run script
    jython_hms_script_file = model / "compute.script"
    jython_hms_script_content = f"""
from hms.model.JythonHms import OpenProject, Compute
OpenProject({c.PROJECT_NAME!r}, {str(model)!r})
Compute({c.RUN_NAME!r})
"""
    logging.info(f"Writing: {jython_hms_script_file}")
    jython_hms_script_file.write_text(jython_hms_script_content)

    # Run HMS via the run script
    run_args = ([str(c.HMS_HOME / "hec-hms.sh"), "-s", str(jython_hms_script_file)],)
    run_kwargs = {
        "cwd": c.HMS_HOME,
        "capture_output": True,
        "text": True,
        "timeout": 600,
    }
    logging.info(f"Running HMS model via args: {run_args}, kwargs: {run_kwargs}")
    execution = subprocess.run(*run_args, **run_kwargs)

    # Extract diagnostics and determine success / fail status
    if log_file.exists():
        logging.info(f"Reading: {log_file}")
        diagnostics = (
            execution.stdout + execution.stderr + (log_file.read_text(errors="replace") if log_file.exists() else "")
        )
    else:
        logging.info(f"Does not exist to read: {log_file}")
        diagnostics = ""

    success = (
        execution.returncode == 0
        and "ERROR" not in diagnostics
        and f'Finished computing simulation run "{c.RUN_NAME}"' in diagnostics
    )
    logging.info(f"success: {success}")
    return success, diagnostics


def _write_stormhub_input_aoi_polygon(model: Path) -> Path:
    """Write the stormhub input AOI polygon file and return a Path to it."""
    aoi_file = model / "stormhub_aoi.gpkg"
    logging.info(f"Reading: {model / c.DATA_SQLITE_FILENAME / 'subbasin2d'}")
    boundary = gpd.read_file(model / c.DATA_SQLITE_FILENAME, layer="subbasin2d").dissolve()
    boundary.geometry = boundary.geometry.envelope.buffer(c.PIXEL_RESOLUTION_M * 3)
    logging.info(f"Writing: {aoi_file}")
    boundary.to_file(aoi_file, driver="GPKG")
    return aoi_file


def _get_control_window() -> tuple[datetime, datetime]:
    """Return the start datetime and end datetimes for the .control file."""
    return c.START_DATETIME, c.END_DATETIME


def _update_grid_file_block(
    orig_content: str, find_grid_type: str, new_gridname: str, new_filename: str, new_pathname: str
) -> str:
    """From .grid text file content, find a "Grid:" block where "Grid Type:" is "Precipitation" or "Temperature". Update that block in a copy and return it.

    The Grid block is detected by finding a line that starts with "Grid:" and a later line that starts with "End:".
    Return an edited copy of the provided ``orig_content``.

    Parameters
    ----------
    orig_content : str
        The existing full content of the .grid file which will be scanned. An edited copy of this string will be returned.

    find_grid_type : str
        The value to find in the existing file for "Grid Type:", choose from: ["Precipitation", "Temperature"].

    new_gridname : str
        The new value to apply for "Grid:", e.g. "AORC-APCP_surface" or "AORC-TMP_2maboveground".

    new_filename : str
        The new value to apply for "Filename:", e.g. "data/stormhub-forcing.dss".

    new_pathname : str
        The new value to apply for DSS "Pathname:", e.g. f"/SHG{resolution_km}K/{c.PROJECT_NAME.upper()}/{variable}///AORC/".

    Returns
    -------
    str
        An edited copy of the provided ``orig_content``.
    """
    pattern = r"^Grid:.*?^End:[ \t]*\r?$"
    search_flags = re.MULTILINE | re.DOTALL
    line_replace_flags = re.MULTILINE

    logging.info(
        f"Finding 'Grid Type: {find_grid_type}' to replace with 'Grid: {new_gridname}', 'Filename: {new_filename}', 'Pathname: {new_pathname}'."
    )
    if find_grid_type not in ("Precipitation", "Temperature"):
        raise ValueError(f"Untested find_grid_type: {find_grid_type!r}")

    all_blocks = list(re.finditer(pattern, orig_content, flags=search_flags))
    matches = [match for match in all_blocks if f"Grid Type: {find_grid_type}" in match.group(0)]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly 1 "{find_grid_type}" block, found {len(matches)}')
    match = matches[0]

    block = match.group(0)
    block = re.sub(r"^Grid:.*$", f"Grid: {new_gridname}", block, flags=line_replace_flags)
    block = re.sub(r"^     Grid:.*$", f"     Grid: {new_gridname}", block, flags=line_replace_flags)
    block = re.sub(r"^     Filename:.*$", f"     Filename: {new_filename}", block, flags=line_replace_flags)
    block = re.sub(r"^     Pathname:.*$", f"     Pathname: {new_pathname}", block, flags=line_replace_flags)

    new_content = orig_content[: match.start()] + block + orig_content[match.end() :]
    return new_content


def _result_values(model: Path, param: str) -> np.ndarray:
    """Read the results from a HMS model that has already been ran (dss file), and return a timeseries array of the provided results param."""
    if not param.isupper():
        raise ValueError(f"Expected parameter to be uppercase, but got: {param!r}")
    results_dss_file = model / c.DATA_RESULTS_FILENAME
    logging.info(f"Reading results DSS file: {results_dss_file}")
    if not results_dss_file.exists():
        raise FileNotFoundError(results_dss_file)
    with HecDss(str(results_dss_file)) as results:
        path = next(path for path in results.get_catalog().uncondensed_paths if f"/{param}/" in path.upper())
        return results.get(path, *_get_control_window(), trim=True).values
