#!/bin/bash

set -euo pipefail

# Download HMS
hms_url="https://github.com/HydrologicEngineeringCenter/hec-downloads/releases/download/1.0.47/HEC-HMS-4.14-linux64.tar.gz"
hms_dir="$HOME/.local/share/hec-hms/4.14"
mkdir -p "${hms_dir}"
curl -fL "${hms_url}" | tar -xz --strip-components=1 -C "${hms_dir}"
chmod +x "${hms_dir}/hec-hms.sh" "${hms_dir}/jre/bin/java"
${hms_dir}/hec-hms.sh -s /dev/null

# Download the Punxsutawney sample model which uses SHG.
# Found on 10/2/2026 from: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/gis-tools-and-terrain-data/applying-hec-hms-gis-parameter-estimation-tools/parameterizing-gridded-basin-methods
test_model_url="https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/files/206326720/365468118/1/1784565111811/Punx_Gridded_Param_final_4.14-beta.3.zip"
curl -fL "${test_model_url}" -o "${hms_dir}/punx.zip"
