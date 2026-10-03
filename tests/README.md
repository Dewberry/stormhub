# Tests

## HEC-HMS Integration Tests

Below are commands to build and run `stormhub` tests to confirm that its outputs are ingestible by HEC-HMS.  This uses a public sample model provided by USACE.

Steps taken by the test:

1. Run the sample model to confirm it works as is.
2. Delete the model's precipitation data file.
3. Attempt to run the model and confirm it is broken.
4. Call `stormhub` to write a new precipitation data file.
5. Run the model again and confirm it can use the `stormhub` output.
6. (High level) Assert comparability, with tolerance, between results of original model versus results using `stormhub` meteorological forcing.

All commands should be run the repository root. Set `HMS_VERSION` first.

```sh
HMS_VERSION=4.14
```

### HMS in Docker

```sh
./tests/hec_hms_integration/run_tests_docker.sh ${HMS_VERSION}
```

### HMS in Linux without Docker

`numpy<2` is needed for now to avoid a geopandas error

```sh
[ -d .venv ] || python -m venv .venv
source .venv/bin/activate
python -m pip install "numpy<2" ".[dev]"

./tests/hec_hms_integration/install_hms_${HMS_VERSION}.sh
./tests/hec_hms_integration/run_tests.sh ${HMS_VERSION}
```

## Run All Tests

Activate the venv and install dependencies for the HEC-HMS Integration Tests, then run:

```sh
HMS_VERSION=4.14 python -m pytest
```
