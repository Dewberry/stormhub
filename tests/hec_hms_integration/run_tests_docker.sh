#!/bin/bash

set -euo pipefail

# e.g. "4.14"
HMS_VERSION=$1

docker build -f "tests/hec_hms_integration/Dockerfile.hec-hms" --build-arg HMS_VERSION="${HMS_VERSION}" -t "stormhub-hec-hms:${HMS_VERSION}" .
docker run --rm "stormhub-hec-hms:${HMS_VERSION}" "./tests/hec_hms_integration/run_tests.sh" "${HMS_VERSION}"
