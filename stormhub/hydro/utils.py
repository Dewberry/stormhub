"""USGS gage utility functions."""

import logging
from typing import List, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import scipy.stats as stats
from dataretrieval import NoSitesError, nwis


def find_gages_in_watershed(watershed: str, min_num_records: Optional[int] = None) -> List[str]:
    """
    Identify USGS gages within a given watershed and optionally filters by a minimum number of records.

    Parameters
    ----------
        watershed (str): Path to a GeoJSON containing the watershed geometry.
        min_num_records (Optional[int]): Minimum number of records required for a gage to be included. If None, all valid gages within the watershed are returned.

    Returns
    -------
        List[str]: A list of USGS gage site numbers that meet the criteria.
    """
    logging.info("Searching watershed for gages")
    watershed = gpd.read_file(watershed)
    bbox = [round(coord, 6) for coord in watershed.total_bounds.tolist()]

    gages_in_watershed_bbox = nwis.get_info(bBox=bbox, parameterCd=["00060", "00065"])[0]

    watershed_geom = watershed.iloc[0].geometry
    gages_within_watershed = gages_in_watershed_bbox[gages_in_watershed_bbox.within(watershed_geom)]

    candidate_gages = []
    logging.info(
        f"USGS API returned {len(gages_within_watershed)} responses, filtering for valid gages based in site_no length (must = 8 characters)"
    )
    for row in gages_within_watershed.itertuples():
        site_id = row.site_no
        logging.info(f"Checking gage {site_id}")
        if len(site_id) == 8:
            candidate_gages.append(site_id)
        else:
            logging.info(f"Removing potentially invalid gage {site_id}")

    if len(candidate_gages) == 0:
        logging.error("No valid gages found within given watershed.")
    else:
        logging.info(f"Found {len(candidate_gages)} valid gage numbers in watershed")

    if min_num_records is None:
        return candidate_gages

    valid_gage_nums = []
    for gage_num in candidate_gages:
        try:
            logging.info(f"Checking period of record for `{gage_num}`")
            if len(nwis.get_record(service="peaks", sites=[gage_num])) >= min_num_records:
                valid_gage_nums.append(gage_num)
        except NoSitesError:
            continue
    logging.info(f"Found {len(valid_gage_nums)} valid gage numbers in watershed with min period of record.")
    return valid_gage_nums


def log_pearson_iii(peak_flows: pd.Series, standard_return_periods: list = [2, 5, 10, 25, 50, 100, 500]) -> dict:
    """Calculate peak flow estimates for specified return periods using the Log-Pearson Type III distribution.

    Args:
        peak_flows (pd.Series): A pandas Series containing peak flow values.
        standard_return_periods (list, optional): A list of return periods for which to calculate peak flow estimates.

    Returns
    -------
        dict: A dictionary where keys are return periods and values are the peak flow estimates.
    """
    log_flows = np.log10(peak_flows.values)
    mean_log = np.mean(log_flows)
    std_log = np.std(log_flows, ddof=1)
    skew_log = stats.skew(log_flows)

    return {
        str(rp): int(10 ** (mean_log + stats.pearson3.ppf(1 - 1 / rp, skew_log) * std_log))
        for rp in standard_return_periods
    }
