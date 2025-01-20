from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import new_catalog, new_collection

if __name__ == "__main__":
    initialize_logger()

    # Catalog Args
    root_dir = "<local-path>"
    config_file = f"{root_dir}/duwamish/config.json"
    catalog_id = "duwamish"
    local_directory = f"{root_dir}"

    storm_catalog = new_catalog(
        catalog_id,
        config_file,
        local_directory=local_directory,
        catalog_description="Duwamish Catalog",
    )

    # All Collection Args
    start_date = "1979-02-01"
    end_date = "2024-12-31"
    top_n_events = 440

    # Collection Args
    storm_duration_hours = 48
    min_precip_threshold = 2.5
    storm_collection = new_collection(
        storm_catalog,
        start_date,
        end_date,
        storm_duration_hours,
        min_precip_threshold,
        top_n_events,
        check_every_n_hours=6,
    )
