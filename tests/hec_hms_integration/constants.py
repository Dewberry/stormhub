"""Paths and settings for testing the HEC-HMS tutorial model "Punxsutawney".

Zipped model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/files/206326720/365468118/1/1784565111811/Punx_Gridded_Param_final_4.14-beta.3.zip
Found on 10/2/2026 from: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/gis-tools-and-terrain-data/applying-hec-hms-gis-parameter-estimation-tools/parameterizing-gridded-basin-methods
"""

import datetime
import os
from pathlib import Path

try:
    HMS_VERSION = os.environ["HMS_VERSION"]
    if not HMS_VERSION.strip():
        raise KeyError
except KeyError:
    raise KeyError("HMS_VERSION environment variable is not set")
HMS_HOME = Path.home() / ".local/share/hec-hms" / HMS_VERSION


# Test Settings:
# For comparing the HMS results of the original Punxsutawney forcing versus the ``stormhub`` forcing.
HMS_PARAMETERS_TO_COMPARE = ["FLOW", "PRECIP-INC"]
# Choose a list of np.nan* methods, for example "mean", "min", "max", "sum", etc. E.g. providing "mean" will cause it to use np.nanmean.
NP_STATS_METHODS_TO_COMPARE = ["mean"]
# Output resolution for stormhub meteorological forcing data.
# Original Punxsutawney HMS model used coarser grid, we use 1km for ``stormhub`` AORC test.
PIXEL_RESOLUTION_M = 1000
PIXEL_RESOLUTION_KM = PIXEL_RESOLUTION_M / 1000

# Aspects of original Punxsutawney model:
ORIG_MODEL_ZIP = HMS_HOME / "punx.zip"
ORIG_MODEL_SUBDIR = "Punx_Gridded_Param_final"
PROJECT_NAME = "Punx"
PROJECT_FILENAME = f"{PROJECT_NAME}.hms"
CONFIG_GRID_FILENAME = f"{PROJECT_NAME}.grid"
CONFIG_CONTROL_FILENAME = "Sep_2018.control"
CONFIG_MET_FILENAME = "Sep_2018.met"
DATA_RESULTS_FILENAME = "Sep_2018.dss"
DATA_LOG_FILENAME = "Sep_2018.log"
DATA_PRECIP_FILENAME_ORIG = "data/precip.dss"  # Filename from original model
DATA_TEMP_FILENAME_ORIG = "data/temp.dss"  # Filename from original model
DATA_SQLITE_FILENAME = "punxsutawney.sqlite"
RUN_NAME = "Sep-2018"
# From Sep_2018.control
START_DATE = datetime.date(day=1, month=9, year=2018)
START_TIME = datetime.time(hour=0, minute=0)
END_DATE = datetime.date(day=29, month=9, year=2018)
END_TIME = datetime.time(hour=0, minute=0)

# Stormhub:
# Munge
START_DATETIME = datetime.datetime.combine(START_DATE, START_TIME)
END_DATETIME = datetime.datetime.combine(END_DATE, END_TIME)
# Time logic
STORMHUB_START_DATETIME = START_DATETIME - datetime.timedelta(hours=1)
STORMHUB_DURATION_HOURS = int((END_DATETIME - START_DATETIME).total_seconds() / 3600) + 1
DATA_MET_FORCING_STORMHUB = "data/met_forcing_stormhub.dss"  # Filename for edited model

# Misc:
CONFIG_MET_MISSING_DATA_TOLERANT_YES = "Set Missing Data to Default: Yes"
CONFIG_MET_MISSING_DATA_TOLERANT_NO = "Set Missing Data to Default: No"
