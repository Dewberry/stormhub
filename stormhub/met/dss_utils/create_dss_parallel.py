"""Creates dss files using multithreading for efficiency from a given watershed for each event in a metadata json formatted in the following way.

{
  "1988-09-13": {
    "event_id": "236",
    "st_number": "st5"
  },
  "1993-11-14": {
    "event_id": "190",
    "st_number": "st5"
  }
}.
"""

import os
import json
import logging
from datetime import datetime

from concurrent.futures import ProcessPoolExecutor, as_completed
from stormhub.met.zarr_to_dss import noaa_zarr_to_dss, NOAADataVariable


def setup_logging():
    """Ensure each process sets up its own logging to file."""
    logger = logging.getLogger()
    if not logger.handlers:
        logging.basicConfig(
            filename="storm_processing.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )


def process_storm(date, attrs, dss_dir, aoi_path, aoi_name):
    """Process each storm event and generate DSS files."""
    setup_logging()

    storm_start_datetime = datetime.strptime(date, "%Y-%m-%d")
    storm_start_str = datetime.strftime(storm_start_datetime, "%Y%m%d")
    output_name = f"{storm_start_str}_72h_{attrs['st_number']}_r{attrs['event_id']}.dss"
    output_dss_path = os.path.join(dss_dir, output_name)

    try:
        if os.path.exists(output_dss_path):
            logging.info(f"SKIPPED {date} - {output_name} already exists.")
            return

        noaa_zarr_to_dss(
            output_dss_path=output_dss_path,
            aoi_geometry_gpkg_path=aoi_path,
            aoi_name=aoi_name,
            storm_start=storm_start_datetime,
            # NOTE: Unequal slice durations require separate NetCDF time axes. A shared axis pads precipitation, which HMS/Vortex may import as extra DSS records.
            # See notes in function ``write_shg_netcdf_vortex_compliant_variable_durations`` for details.
            variable_duration_map={
                NOAADataVariable.TMP: 864,
                NOAADataVariable.APCP: 72,
            },
        )

        logging.info(f"SUCCESS {date} - {output_name}")

    except Exception as e:
        logging.error(f"FAILED {date} - {output_name} - Error: {e}")


def main(json_path, dss_dir, aoi_path, aoi_name):
    """Create dss files in parallel."""
    with open(json_path) as f:
        storms = json.load(f)

    os.makedirs(dss_dir, exist_ok=True)

    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(process_storm, date, attrs, dss_dir, aoi_path, aoi_name) for date, attrs in storms.items()
        ]

        for future in as_completed(futures):
            future.result()


if __name__ == "__main__":
    json_path = "storm_events.json"
    dss_dir = "dss_outputs"
    aoi_path = "trinity-transpo-area-v01.geojson"
    aoi_name = "TRINITY"
    main(json_path, dss_dir, aoi_path, aoi_name)
