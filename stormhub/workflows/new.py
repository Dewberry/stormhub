import os
import shutil

from pystac import Link, MediaType

from stormhub.logger import initialize_logger
from stormhub.met.storm_catalog import new_catalog, new_collection

if __name__ == "__main__":
    initialize_logger()

    # Catalog Args
    root_dir = "<local-path>"
    config_file = f"{root_dir}/stormhub/catalogs/example-input-data/config.json"
    catalog_id = "indian-creek"
    local_directory = f"{root_dir}/stormhub/catalogs"
    atlas_14_metadata = f"{root_dir}/stormhub/catalogs/example-input-data/indian-creek-atlas14.csv"

    storm_catalog = new_catalog(
        catalog_id,
        config_file,
        local_directory=local_directory,
        catalog_description="Indian Creek Catalog",
    )

    storm_catalog.add_link(
        Link(
            "metadata",
            atlas_14_metadata,
            media_type=MediaType.TEXT,
            title="Atlas 14 Metadata",
            extra_fields={"description": "Metadata for Atlas 14"},
        ),
    )

    shutil.copy(atlas_14_metadata, os.path.join(storm_catalog.spm.catalog_dir, "atlas_14_metadata.csv"))

    # spm = StacPathManager(os.path.join(local_directory, catalog_id))
    # storm_catalog = StormCatalog.from_file(spm.catalog_file)

    # All Collection Args
    start_date = "1979-02-01"
    # end_date = "2024-12-31"
    end_date = "1979-03-31"
    top_n_events = 10

    # Collection 1 Args
    storm_duration_hours = 72
    # min_precip_threshold = 2.81
    min_precip_threshold = 0.05
    storm_collection = new_collection(
        storm_catalog,
        start_date,
        end_date,
        storm_duration_hours,
        min_precip_threshold,
        top_n_events,
        check_every_n_hours=6,
    )
    # # Collection 2 Args
    # storm_duration_hours = 24
    # min_precip_threshold = 2.18
    # storm_collection = new_collection(
    #     storm_catalog,
    #     start_date,
    #     end_date,
    #     storm_duration_hours,
    #     min_precip_threshold,
    #     top_n_events,
    #     check_every_n_hours=2,
    # )

    # # Collection 3 Args
    # storm_duration_hours = 48
    # min_precip_threshold = 2.53
    # storm_collection = new_collection(
    #     storm_catalog,
    #     start_date,
    #     end_date,
    #     storm_duration_hours,
    #     min_precip_threshold,
    #     top_n_events,
    #     check_every_n_hours=4,
    # )
