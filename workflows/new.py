from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import new_catalog, new_collection
import json
import logging
import shutil
import pystac
import os


def save_config(config_file="params-config.json", **kwargs):
    """Automatically saves configuration parameters to a JSON file."""
    with open(config_file, "w") as file:
        json.dump(kwargs, file, indent=4)


def add_config_to_collection(storm_collection, config_filename="params-config.json"):
    """Add config file to collection assets."""
    collection_path = storm_collection.self_href
    collection_dir = os.path.dirname(collection_path)
    os.makedirs(collection_dir, exist_ok=True)

    config_dest_path = os.path.join(collection_dir, config_filename)
    shutil.copy(config_filename, config_dest_path)

    collection = pystac.Collection.from_file(collection_path)

    collection.add_asset(
        "params-config",
        pystac.Asset(
            href=config_filename,
            media_type=pystac.MediaType.JSON,
            description="Contains the configuration parameters used to generate the storm items.",
            roles=["metadata"],
            title="Configuration Parameters",
        ),
    )
    collection.save_object()


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

    save_config(
        start_date=start_date,
        end_date=end_date,
        top_n_events=top_n_events,
        storm_duration_hours=storm_duration_hours,
        min_precip_threshold=min_precip_threshold,
        root_dir=root_dir,
        catalog_id=catalog_id,
        local_directory=local_directory,
    )
    storm_collection = new_collection(
        storm_catalog,
        start_date,
        end_date,
        storm_duration_hours,
        min_precip_threshold,
        top_n_events,
        check_every_n_hours=24,
    )
    # Add config file as a STAC collection asset
    add_config_to_collection(storm_collection)
