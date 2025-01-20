import os

from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import resume_collection
from stormhub.utils import StacPathManager

if __name__ == "__main__":
    initialize_logger()

    # Catalog Args
    root_dir = "<local-dir>"
    config_file = f"{root_dir}/duwamish/config.json"
    catalog_id = "duwamish"
    local_directory = f"{root_dir}"

    spm = StacPathManager(os.path.join(local_directory, catalog_id))
    storm_catalog_file = spm.catalog_file

    # All Collection Args
    start_date = "1979-02-01"
    end_date = "2024-12-31"
    top_n_events = 440

    # Collection 1 Args
    storm_duration_hours = 96
    min_precip_threshold = 4

    storm_collection = resume_collection(
        catalog=storm_catalog_file,
        start_date=start_date,
        end_date=end_date,
        storm_duration=storm_duration_hours,
        min_precip_threshold=min_precip_threshold,
        top_n_events=top_n_events,
        check_every_n_hours=6,
        with_tb=False,
        create_items=True,
    )
