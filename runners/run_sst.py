"""Runner script to create a storm catalog and storm collection for SST."""

# standard imports
import os
import sys
import time

# mount the stormhub directory
cur_dir = os.path.dirname(__file__)
storm_dir = os.path.abspath(os.path.join(cur_dir, ".."))
sys.path.append(storm_dir)

# custom imports
from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import new_catalog, new_collection

# MAIN #####################################################################

if __name__ == "__main__":
    start_time = time.time()
    initialize_logger(json_logging=True)

    # Catalog Args
    root_dir = "/workspaces/stormhub"
    config_file = f"{root_dir}/configs/allegheny.json"
    catalog_id = "allegheny"

    local_directory = f"{root_dir}/catalogs"

    storm_catalog = new_catalog(
        catalog_id,
        config_file,
        local_directory=local_directory,
        catalog_description="Allegheny Catalog",
    )

    # All Collection Args
    start_date = "2000-04-01"
    end_date = "2000-04-10"
    top_n_events = 10

    # Collection Args
    storm_duration_hours = 72
    min_precip_threshold = 0.1
    storm_collection = new_collection(
        storm_catalog,
        start_date,
        end_date,
        storm_duration_hours,
        min_precip_threshold,
        top_n_events,
        check_every_n_hours=6,
        num_workers=10,
    )
    end_time = time.time()
    elapsed_minutes = round((end_time - start_time) / 60, 2)
    print(f"Total Time: {elapsed_minutes} minutes")
