import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats as stats
from dataretrieval import nwis
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from pystac import Asset, Item, MediaType

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
