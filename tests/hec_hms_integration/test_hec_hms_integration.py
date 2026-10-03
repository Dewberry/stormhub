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

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hec_hms_integration import constants as c
from hec_hms_integration import utils

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


def test_hec_hms_integration_stormhub_dss(request) -> None:
    """Unzip the HMS model, run it for a health check, replace its met data with stormhub outputs, run it again, and compare the results from the two runs."""
    tmp_dir = _mkdtemp(request)
    try:
        # Unzip the model and confirm that it will run as-is.
        model = utils.extract_model(target_dir=tmp_dir)
        utils.run_model_assert_success(model)
        hms_results_orig = utils.check_hms_results(model, comp_label="original")
        # Delete met data and confirm that the model will not run
        utils.deprecate_model_met_forcing_data_files(model)
        utils.run_model_assert_failure(model)
        # Write new met data with stormhub and run the model with that.
        utils.write_stormhub_dss(model)
        utils.configure_model_to_use_stormhub_met_forcing(model, c.PIXEL_RESOLUTION_KM)
        utils.run_model_assert_success(model)
        hms_results_stormhub = utils.check_hms_results(model, comp_label="stormhub")
        # Confirm that the results from the original model are comparable to running the model with stormhub outputs.
        hms_results_orig.compare_with_tolerance(
            hms_results_stormhub,
            tol_rel=c.TOLERANCE_REL,
            tol_abs=c.TOLERANCE_ABS,
        )

    finally:
        if not request.config.getoption("--keep-tmp-hms-model"):
            shutil.rmtree(tmp_dir)
