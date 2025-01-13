import os

from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import resume_collection
from stormhub.utils import StacPathManager

if __name__ == "__main__":
    initialize_logger()

    # Catalog Args
    root_dir = "<local-path>"
    config_file = f"{root_dir}/stormhub/catalogs/example-input-data/config.json"
    catalog_id = "indian-creek"
    local_directory = f"{root_dir}/stormhub/catalogs"
    atlas_14_metadata = f"{root_dir}/stormhub/catalogs/example-input-data/indian-creek-atlas14.csv"

    spm = StacPathManager(os.path.join(local_directory, catalog_id))
    storm_catalog_file = spm.catalog_file

    # All Collection Args
    start_date = "1979-02-01"
    # end_date = "2024-12-31"
    end_date = "1979-03-29"
    top_n_events = 10

    # Collection 1 Args
    storm_duration_hours = 72
    # min_precip_threshold = 2.81
    min_precip_threshold = 0.05
    storm_collection = resume_collection(
        catalog=storm_catalog_file,
        start_date=start_date,
        end_date=end_date,
        storm_duration=storm_duration_hours,
        min_precip_threshold=min_precip_threshold,
        top_n_events=top_n_events,
        check_every_n_hours=6,
        with_tb=True,
    )
