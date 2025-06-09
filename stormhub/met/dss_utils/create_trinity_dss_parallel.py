import os
import json
import logging
from datetime import datetime

from concurrent.futures import ProcessPoolExecutor, as_completed

from stormhub.met.zarr_to_dss import noaa_zarr_to_dss, NOAADataVariable

logging.basicConfig(
    filename="my_log_file.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logging.info("This is a test log message.")


def setup_logging():
    """Ensure each process sets up its own logging to file."""
    logger = logging.getLogger()
    if not logger.handlers:
        logging.basicConfig(
            filename="storm_processing.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )


def process_storm(date, attrs, dss_dir):
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
            aoi_geometry_gpkg_path="trinity-transpo-area-v01.geojson",
            aoi_name="TRINITY",
            storm_start=storm_start_datetime,
            variable_duration_map={
                NOAADataVariable.TMP: 72,
                NOAADataVariable.APCP: 72,
            },
        )

        logging.info(f"SUCCESS {date} - {output_name}")

    except Exception as e:
        logging.error(f"FAILED {date} - {output_name} - Error: {e}")


def main():
    with open("storm_events.json") as f:
        storms = json.load(f)

    dss_dir = "dss_outputs"
    os.makedirs(dss_dir, exist_ok=True)

    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process_storm, date, attrs, dss_dir) for date, attrs in storms.items()]

        for future in as_completed(futures):
            future.result()


if __name__ == "__main__":
    main()
