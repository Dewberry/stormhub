"""Test for confirming stormhub outputs can be ingested by HEC-HMS.

Requirements:
    1. Linux only. This test is not supported in Windows.
    2. Internet access (unless this has already been ran: ``./tests/hec_hms_integration/install_hms_4.14.sh``)

Usage:
    1. Run ``./tests/hec_hms_integration/install_hms_4.14.sh`` or equivalent for desired HMS version. This sets up the HMS software and downloads a public test model.
    2. Set / export env var ``HMS_VERSION``, e.g. '4.14'.
    3. Call this pytest routine with or without ``--keep-tmp-hms-model``. If provided, the temporary HMS model directories will not be deleted afterwards.

See ``tests/hec_hms_integration/run_tests.sh`` or ``tests/README.md`` for an example.
"""

import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from conftest import ComparisonError
from hec_hms_integration import constants as c
from hec_hms_integration import utils
from hecdss import HecDss

from stormhub.met.zarr_to_dss import NOAADataVariable, noaa_zarr_to_dss

pytestmark = pytest.mark.skipif(
    not c.HMS_VERSION or not (c.HMS_HOME / "hec-hms.sh").is_file(),
    reason="Set HMS_VERSION and run the matching tests/hec_hms_integration/install_hms_<version>.sh first",
)


def _mkdtemp(req: pytest.FixtureRequest) -> Path:
    """Make a temporary directory with some options and return its Path. Not automatically cleaned up."""
    tmp_dir_prefix = f"tmp-stormhub-{req.node.name}-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}-"
    if req.config.getoption("--keep-tmp-hms-model"):
        tmp_root = req.getfixturevalue("local_data_out_path")
        tmp_root.mkdir(parents=True, exist_ok=True)
    else:
        tmp_root = None
    tmp_dir = Path(tempfile.mkdtemp(prefix=tmp_dir_prefix, dir=tmp_root))
    return tmp_dir


def test_netcdf_dss_equivalence(tmp_path: Path) -> None:
    """Verify equivalence of two .dss files: stormhub forcing as direct DSS file vs stormhub forcing as NetCDF file later converted to DSS.

    tmp_path is a built-in pytest fixture that is automatically cleaned up.
    """
    model = utils.extract_model(target_dir=tmp_path / "model")
    aoi_path = utils._write_stormhub_input_aoi_polygon(model)
    direct_dss_path = tmp_path / "direct.dss"
    netcdf_path = direct_dss_path.with_suffix(".nc")

    assert not direct_dss_path.is_file()
    noaa_zarr_to_dss(
        output_dss_path=str(direct_dss_path),
        aoi_geometry_gpkg_path=str(aoi_path),
        aoi_name="PUNX",
        storm_start=datetime(2018, 9, 6, 16),
        variable_duration_map={NOAADataVariable.APCP: 1, NOAADataVariable.TMP: 3},
        output_resolution_km=1,
        add_nc=True,
    )
    assert direct_dss_path.is_file()

    converted_dss_path = tmp_path / "converted.dss"
    assert netcdf_path.is_file()
    assert not converted_dss_path.is_file()
    utils.stormhub_netcdf_to_stormhub_dss(netcdf_path, converted_dss_path, "PUNX", 1)
    assert converted_dss_path.is_file()

    with HecDss(str(direct_dss_path)) as direct, HecDss(str(converted_dss_path)) as converted:
        direct_paths = sorted(direct.get_catalog().uncondensed_paths)
        converted_paths = sorted(converted.get_catalog().uncondensed_paths)
        assert direct_paths == converted_paths

        for path in direct_paths:
            direct_grid = direct.get(path)
            converted_grid = converted.get(path)
            assert direct_grid.dataUnits == converted_grid.dataUnits
            assert direct_grid.data_type == converted_grid.data_type
            assert direct_grid.cellSize == converted_grid.cellSize
            assert direct_grid.numberOfCellsX == converted_grid.numberOfCellsX
            assert direct_grid.numberOfCellsY == converted_grid.numberOfCellsY
            assert direct_grid.lowerLeftCellX == converted_grid.lowerLeftCellX
            assert direct_grid.lowerLeftCellY == converted_grid.lowerLeftCellY
            assert direct_grid.nullValue == converted_grid.nullValue
            if "/PRECIPITATION/" in path:
                for label, grid in (("direct", direct_grid), ("NetCDF-converted", converted_grid)):
                    logging.info(
                        "Mean for %s DSS at %s: %.4f",
                        label,
                        path,
                        grid.data[(np.abs(grid.data) < 1e30) & (grid.data != grid.nullValue)].mean(),
                    )
            assert np.allclose(direct_grid.data, converted_grid.data, rtol=1e-6, atol=1e-5, equal_nan=True)


def test_hec_hms_integration_stormhub_dss(request) -> None:
    """Unzip the HMS model, run it for a health check, replace its met data with stormhub outputs, run it again, and compare the hydrologic results from the two runs."""
    tmp_dir = _mkdtemp(request)
    comparison_failures = []

    try:
        # Unzip the model and confirm that it will run as-is.
        model = utils.extract_model(target_dir=tmp_dir)
        utils.run_model_assert_success(model)
        hms_results_from_stormhub_forcing_direct_dss = utils.check_hms_results(model, comp_label="original")
        # Delete met data and confirm that the model will not run
        utils.deprecate_model_met_forcing_data_files(model)
        utils.run_model_assert_failure(model)

        # Run the model using the stormhub direct DSS file.
        # Write new met data with stormhub and run the model with that.
        # Compare the HMS result with that of the original Punxsutawney model run.
        utils.write_stormhub_dss(model)
        utils.configure_model_to_use_stormhub_met_forcing(model, c.PIXEL_RESOLUTION_KM)
        utils.run_model_assert_success(model)
        hms_results_from_stormhub_direct_dss_forcing = utils.check_hms_results(model, comp_label="stormhub-direct-dss")
        # Confirm that the results from the original model are comparable to running the model with stormhub outputs.
        try:
            hms_results_from_stormhub_forcing_direct_dss.compare_with_tolerance(
                hms_results_from_stormhub_direct_dss_forcing, tol_rel=0.30, tol_abs=500
            )
        except ComparisonError as error:
            comparison_failures.append(
                f"Failed when comparing model results of Original vs Stormhub Direct-DSS:\n{error}"
            )

        # Run the model using the stormhub NetCDF file (after converting the NetCDF to DSS first).
        # Compare the HMS result with that of the model ran with stormhub's direct DSS output.
        stormhub_forcing_dss = model / c.DATA_MET_FORCING_STORMHUB
        stormhub_forcing_dss.unlink(missing_ok=True)
        assert not stormhub_forcing_dss.exists()
        stormhub_netcdf = stormhub_forcing_dss.with_suffix(".nc")
        if not stormhub_netcdf.is_file():
            raise FileNotFoundError(f"Expected Vortex-compatible NetCDF output: {stormhub_netcdf}")
        utils.stormhub_netcdf_to_stormhub_dss(
            stormhub_netcdf, stormhub_forcing_dss, c.PROJECT_NAME, c.PIXEL_RESOLUTION_KM
        )
        assert stormhub_forcing_dss.is_file() and stormhub_forcing_dss.stat().st_size > 0
        utils.run_model_assert_success(model)
        hms_results_from_stormhub_forcing_netcdf_converted_to_dss = utils.check_hms_results(
            model, comp_label="stormhub-netcdf-to-dss"
        )
        try:
            hms_results_from_stormhub_direct_dss_forcing.compare_with_tolerance(
                hms_results_from_stormhub_forcing_netcdf_converted_to_dss, tol_rel=0.01, tol_abs=1
            )
        except ComparisonError as error:
            comparison_failures.append(f"Failed when comparing Stormhub Direct-DSS vs NetCDF-to-DSS:\n{error}")

        # Fail if any of the comparisons failed.
        if comparison_failures:
            pytest.fail("HMS comparison failure(s):\n\n" + "\n\n".join(comparison_failures))

    finally:
        if not request.config.getoption("--keep-tmp-hms-model"):
            shutil.rmtree(tmp_dir)
