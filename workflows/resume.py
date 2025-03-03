import os
import json
from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import resume_collection
from stormhub.utils import StacPathManager


def load_config(config_path):
    """Load configuration from a JSON file."""
    with open(config_path, "r") as file:
        return json.load(file)


if __name__ == "__main__":
    initialize_logger()

    config_path = "params-config.json"
    config = load_config(config_path)

    # Extract config values
    start_date = config["start_date"]
    end_date = config["end_date"]
    top_n_events = config["top_n_events"]
    storm_duration_hours = config["storm_duration_hours"]
    min_precip_threshold = config["min_precip_threshold"]
    root_dir = config["root_dir"]
    catalog_id = config["catalog_id"]
    local_directory = config["local_directory"]

    # Set up storm catalog file
    spm = StacPathManager(os.path.join(local_directory, catalog_id))
    storm_catalog_file = spm.catalog_file

    # Resume collection with loaded parameters
    storm_collection = resume_collection(
        catalog=storm_catalog_file,
        start_date=start_date,
        end_date=end_date,
        storm_duration=storm_duration_hours,
        min_precip_threshold=min_precip_threshold,
        top_n_events=top_n_events,
        check_every_n_hours=24,
        with_tb=False,
        create_items=True,
    )
