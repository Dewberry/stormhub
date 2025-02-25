from stormhub.hydro.usgs.usgs import new_gage_collection, new_gage_catalog
from stormhub.hydro.utils import find_gages_in_watershed
from stormhub.logger import initialize_logger


if __name__ == "__main__":

    initialize_logger()
    catalog_id = "gage_catalog"
    local_directory = "C:\\Users\\sjanke\\Code\\stormhub\\usgs_gages"
    watershed = "C:\\Users\\sjanke\\Code\\stormhub\\bighorn\\bighorn.geojson"

    gage_catalog = new_gage_catalog(
        catalog_id,
        local_directory=local_directory,
        catalog_description="Bighorn Catalog",
    )

    # gage_numbers = ["12105900", "12167000"]
    gage_numbers = find_gages_in_watershed(watershed, 15)
    new_gage_collection(gage_catalog, gage_numbers, local_directory)
