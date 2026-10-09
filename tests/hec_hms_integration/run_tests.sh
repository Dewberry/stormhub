#!/bin/bash

set -euo pipefail

# e.g. "4.14"
export HMS_VERSION=$1

# python -m pytest tests/hec_hms_integration/test_hec_hms_integration.py --keep-tmp-hms-model
python -m pytest tests/hec_hms_integration/test_hec_hms_integration.py
