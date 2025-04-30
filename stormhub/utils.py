import json
import logging
import socket
from datetime import datetime, timedelta
from typing import List
import os

from pystac import Link, Collection
from shapely.geometry import mapping, shape

STORMHUB_REF_LINK = Link(
    rel="Processing",
    target="https://github.com/Dewberry/stormhub",
    title="Source Code",
    media_type="text/html",
    extra_fields={"Description": "Source code used to generate STAC objects"},
)


def is_port_in_use(port: int = 8080, host: str = "http://localhost") -> bool:
    """Check if a given port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except socket.error:
            return True


def load_config(config_file: str) -> dict:
    """Load a json config file."""
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: dict) -> dict:
    """Validate a config dictionary against required keys."""
    required_keys = {
        "watershed": ["id", "geometry_file", "description"],
        "transposition_region": ["id", "geometry_file", "description"],
    }

    for key, sub_keys in required_keys.items():
        if key not in config:
            raise ValueError(f"Missing required section: {key}")
        for sub_key in sub_keys:
            if sub_key not in config[key] or not config[key][sub_key]:
                raise ValueError(f"Missing value for {sub_key} in section {key}")
    return config


def generate_date_range(
    start_date: str, end_date: str, every_n_hours: int = 6, date_format: str = "%Y-%m-%d"
) -> List[datetime]:
    """Generates a list of datetime objects at a given interval between start and end dates."""
    start = datetime.strptime(start_date, date_format)
    end = datetime.strptime(end_date, date_format)

    date_range = []
    current_date = start
    while current_date <= end:
        date_range.append(current_date)
        current_date += timedelta(hours=every_n_hours)

    return date_range


def create_feature_collection_from_items(
    collection: Collection, output_geojson: str, select_properties: str = "aorc:statistics"
):
    """Generates a geojson feature collection from a collection of STAC items."""
    features = []
    for item in collection.get_all_items():
        geom = shape(item.geometry)
        if geom.is_empty:
            continue

        feature = {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "id": item.id,
                select_properties: item.properties.get(select_properties),
                # **item.properties,
            },
        }
        features.append(feature)

    feature_collection = {"type": "FeatureCollection", "features": features}

    with open(output_geojson, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, indent=4)

    logging.info("FeatureCollection saved to %s", output_geojson)


class StacPathManager:
    """
    Builds consistent paths for STAC items and collections assuming a top-level local catalog.
    """

    def __init__(self, local_catalog_dir: str):
        self._catalog_dir = os.path.abspath(local_catalog_dir)

    @property
    def catalog_dir(self):
        return self._catalog_dir

    @property
    def catalog_file(self):
        return os.path.join(self._catalog_dir, "catalog.json")

    def storm_collection_id(self, duration: int) -> str:
        return f"{duration}hr-events"

    def catalog_item(self, item_id: str) -> str:
        return os.path.join(self.catalog_dir, item_id, f"{item_id}.json")

    def catalog_asset(self, item_id: str, asset_dir: str = "hydro_domains") -> str:
        return os.path.join(self.catalog_dir, asset_dir, f"{item_id}.json")

    def collection_file(self, collection_id: str) -> str:
        return os.path.join(self.catalog_dir, collection_id, "collection.json")

    def collection_dir(self, collection_id: str) -> str:
        return os.path.join(self.catalog_dir, collection_id)

    def collection_asset(self, collection_id: str, filename: str) -> str:
        return os.path.join(self.catalog_dir, collection_id, filename)

    def collection_item_dir(self, collection_id: str, item_id: str) -> str:
        return os.path.join(self.catalog_dir, collection_id, item_id)

    def collection_item(self, collection_id: str, item_id: str) -> str:
        return os.path.join(self.catalog_dir, collection_id, item_id, f"{item_id}.json")

    def collection_item_asset(self, collection_id: str, item_id: str, filename: str) -> str:
        return os.path.join(self.catalog_dir, collection_id, item_id, filename)


def file_table(data: dict, col1: str, col2: str):
    table = []
    for k, v in data.items():
        table.append({col1: k, col2: v})
    return table
