import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import numpy as np
import pandas as pd
import scipy.stats as stats
from dataretrieval import nwis
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from pystac import Asset, Item, MediaType, Collection
import pystac


from stormhub.hydro.plots import (
    plot_ams,
    plot_ams_seasonal,
    plot_log_pearson_iii,
    plot_nwis_statistics,
)
from stormhub.utils import file_table


class UsgsGage(Item):

    @classmethod
    def from_usgs(cls, gage_number: str, href: Optional[str] = None, **kwargs):
        if href is None:
            href = f"{gage_number}.json"

        site_data = cls._load_site_data(gage_number)

        geometry = {"type": "Point", "coordinates": [site_data["dec_long_va"], site_data["dec_lat_va"]]}
        bbox = [
            site_data["dec_long_va"],
            site_data["dec_lat_va"],
            site_data["dec_long_va"],
            site_data["dec_lat_va"],
        ]
        properties = {
            "site_no": site_data["site_no"],
            "station_nm": site_data["station_nm"],
            "huc_cd": str(site_data["huc_cd"]),
            "drain_area_va": float(site_data["drain_area_va"]),
            "dv": {
                "begin_date": site_data["dv"]["begin_date"],
                "end_date": site_data["dv"]["end_date"],
                "count_nu": str(site_data["dv"]["count_nu"]),
            },
            "iv": {
                "begin_date": site_data["iv"]["begin_date"],
                "end_date": site_data["iv"]["end_date"],
                "count_nu": str(site_data["iv"]["count_nu"]),
            },
            "site_retrieved": site_data["site_retrieved"],
        }
        start_datetime = None  # datetime.strptime(site_data["dv"]["begin_date"], "%Y-%m-%d")
        end_datetime = None  # datetime.strptime(site_data["dv"]["end_date"], "%Y-%m-%d")

        logging.info(f"Creating UsgsGage {gage_number} {site_data['station_nm']}")

        return cls(
            gage_number,
            geometry,
            bbox,
            datetime.now(),
            properties,
            start_datetime,
            end_datetime,
            None,
            href,
            **kwargs,
        )

    def __repr__(self):
        return f"<UsgsGage {self.id} {self.properties['station_nm']}>"

    @staticmethod
    def _load_site_data(gage_number: str) -> dict:
        """Query NWIS for site information"""
        resp = nwis.get_record(sites=gage_number, service="site")

        return {
            "site_no": resp["site_no"].iloc[0],
            "station_nm": resp["station_nm"].iloc[0],
            "dec_lat_va": float(resp["dec_lat_va"].iloc[0]),
            "dec_long_va": float(resp["dec_long_va"].iloc[0]),
            "drain_area_va": resp["drain_area_va"].iloc[0],
            "huc_cd": resp["huc_cd"].iloc[0],
            "alt_datum_cd": resp["alt_datum_cd"].iloc[0],
            "site_retrieved": datetime.now().isoformat(),
            "dv": {
                "begin_date": resp["begin_date"].iloc[0] if "begin_date" in resp else None,
                "end_date": resp["end_date"].iloc[0] if "end_date" in resp else None,
                "count_nu": resp["count_nu"].iloc[0] if "count_nu" in resp else None,
            },
            "iv": {
                "begin_date": resp["begin_date"].iloc[0] if "begin_date" in resp else None,
                "end_date": resp["end_date"].iloc[0] if "end_date" in resp else None,
                "count_nu": resp["count_nu"].iloc[0] if "count_nu" in resp else None,
            },
        }

    def get_peaks(self, item_dir: str, make_plots: bool = True):
        gage_id = self.properties["site_no"]
        df = nwis.get_record(service="peaks", sites=[gage_id])
        file_name = os.path.join(item_dir, f"{gage_id}-ams.pq")
        if not os.path.exists(item_dir):
            os.makedirs(item_dir)
        df.to_parquet(file_name)

        peaks = self.log_pearson_iii(df["peak_va"])
        asset = Asset(
            file_name,
            media_type=MediaType.PARQUET,
            roles=["data"],
            extra_fields={"file:values": file_table(peaks, "return_period", "discharge_CFS_(Approximate)")},
        )

        self.add_asset("annual_maxima_series", asset)

        if make_plots:
            # AMS Plot 1
            filename = os.path.join(item_dir, f"{gage_id}-ams.png")
            _ = plot_ams(df, gage_id, filename)

            asset = Asset(filename, media_type=MediaType.PNG, roles=["thumbnail"])
            self.add_asset("ams_plot", asset)

            # AMS Plot 2
            filename = os.path.join(item_dir, f"{gage_id}-ams-seasonal.png")
            _ = plot_ams_seasonal(df, gage_id, filename)

            asset = Asset(filename, media_type=MediaType.PNG, roles=["thumbnail"])
            self.add_asset("ams_seasons_plot", asset)

            # LPII Plot
            filename = os.path.join(item_dir, f"{gage_id}-ams-lpiii.png")
            _ = plot_log_pearson_iii(df["peak_va"], gage_id, filename)

            asset = Asset(filename, media_type=MediaType.PNG, roles=["thumbnail"])
            self.add_asset("ams_LPIII_plot", asset)

    def log_pearson_iii(self, peak_flows: pd.Series, standard_return_periods: list = [2, 5, 10, 25, 50, 100, 500]):
        log_flows = np.log10(peak_flows.values)
        mean_log = np.mean(log_flows)
        std_log = np.std(log_flows, ddof=1)
        skew_log = stats.skew(log_flows)

        return {
            str(rp): int(10 ** (mean_log + stats.pearson3.ppf(1 - 1 / rp, skew_log) * std_log))
            for rp in standard_return_periods
        }

    def get_flow_stats(self, item_dir: str, make_plots: bool = True):
        gage_id = self.properties["site_no"]
        df = nwis.get_stats(sites=gage_id)[0]
        file_name = os.path.join(item_dir, f"{gage_id}-flow-stats.pq")

        if not os.path.exists(item_dir):
            os.makedirs(item_dir)

        df.to_parquet(file_name)

        asset = Asset(file_name, media_type=MediaType.PARQUET, roles=["data"])

        self.add_asset("annual_maxima_series", asset)

        if make_plots:
            # AMS Plot 1
            filename = os.path.join(item_dir, f"{gage_id}-flow-stats.png")
            _ = plot_nwis_statistics(df, gage_id, filename)

            asset = Asset(filename, media_type=MediaType.PNG, roles=["thumbnail"])
            self.add_asset("flow_statistics_plot", asset)


def from_stac(href: str) -> UsgsGage:
    """Create a UsgsGage from a STAC Item"""
    return UsgsGage.from_file(href)

class GageCollection(pystac.Collection):
    def __init__(self, collection_id: str, items: List[pystac.Item], href):
        """
        Initialize a GageCollection instance.

        Args:
            collection_id (str): The ID of the collection.
            items (List[pystac.Item]): List of STAC items to include in the collection.
        """
        spatial_extents = [item.bbox for item in items if item.bbox]
        temporal_extents = [item.datetime for item in items if item.datetime is not None]

        collection_extent = pystac.Extent(
            spatial=pystac.SpatialExtent(
                bboxes=[
                    [
                        min(b[0] for b in spatial_extents),
                        min(b[1] for b in spatial_extents),
                        max(b[2] for b in spatial_extents),
                        max(b[3] for b in spatial_extents),
                    ]
                ]
            ),
            temporal=pystac.TemporalExtent(intervals=[[min(temporal_extents), max(temporal_extents)]]),
        )

        super().__init__(
            id=collection_id,
            description="STAC collection generated from gage items.",
            extent=collection_extent,
            href = href
        )

        for item in items:
            self.add_item_to_collection(item)


    def add_item_to_collection(self, item: Item, override: bool = False):
        """
        Add an item to the collection.

        Args:
            item (Item): The STAC item to add.
            override (bool): Whether to override an existing item with the same ID.
        """
        existing_ids = {item.id for item in self.get_all_items()}

        if item.id in existing_ids:
            if override:
                self.remove_item(item.id)
                item.set_parent(self)
                self.add_item(item)
                logging.info(f"Overwriting (existing) item with ID '{item.id}'.")
            else:
                logging.error(
                    f"Item with ID '{item.id}' already exists in the collection. Use `override=True` to overwrite."
                )
        else:
            item.set_parent(self)
            self.add_item(item)
            logging.info(f"Added item with ID '{item.id}' to the collection.")

def new_gage_collection(gage_numbers, directory):
    base_dir = Path(directory)
    gages_dir = base_dir.joinpath("gages")
    gages_dir.mkdir(parents=True, exist_ok=True)
    collection_href = base_dir.joinpath("collection.json")

    items = []
    for gage_number in gage_numbers:
        try:
            gage_item_dir = gages_dir.joinpath(gage_number)
            gage_item_dir.mkdir(parents=True, exist_ok=True)

            gage = UsgsGage.from_usgs(gage_number, href=str(gage_item_dir.joinpath(f"{gage_number}.json")))
            gage.get_flow_stats(str(gage_item_dir))
            gage.get_peaks(str(gage_item_dir))

            for asset in gage.assets.values():
                asset.href = os.path.relpath(asset.href, gage_item_dir).replace("\\", "/")

            gage.save_object()
            items.append(gage)
        except:
            logging.error(f"{gage_number} failed")

    collection = GageCollection("gages", items, str(collection_href))

    catalog = pystac.Catalog(id='gage_catalog',
                         description='This Catalog is a basic demonstration of how to include a Collection in a STAC Catalog.')
    catalog.add_child(collection)
    catalog.normalize_and_save(root_href=str(base_dir),
                            catalog_type=pystac.CatalogType.SELF_CONTAINED)

