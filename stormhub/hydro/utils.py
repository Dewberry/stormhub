from dataretrieval import nwis, NoSitesError
import geopandas as gpd
from typing import Optional, List
import logging


def find_gages_in_watershed(watershed: str, min_num_records: Optional[int] = None) -> List[str]:
    """
    Identifies USGS gages within a given watershed and optionally filters by a minimum number of records.

    Parameters:
        watershed (str): Path to a GeoJSON containing the watershed geometry.
        min_num_records (Optional[int]): Minimum number of records required for a gage to be included. If None, all valid gages within the watershed are returned.

    Returns:
        List[str]: A list of USGS gage site numbers that meet the criteria.
    """
    logging.info("Finding gages within watershed")
    watershed = gpd.read_file(watershed)
    bbox = [round(coord, 6) for coord in watershed.total_bounds.tolist()]

    gages_in_watershed_bbox = nwis.get_info(bBox=bbox)[0]

    watershed_geom = watershed.iloc[0].geometry
    gages_within_watershed = gages_in_watershed_bbox[gages_in_watershed_bbox.within(watershed_geom)]
    filtered_gages = gages_within_watershed[gages_within_watershed["site_no"].str.len() == 8]
    gage_nums = filtered_gages["site_no"].to_list()

    if min_num_records is None:
        return gage_nums

    valid_gage_nums = []
    for gage_num in gage_nums:
        try:
            if len(nwis.get_record(service="peaks", sites=[gage_num])) >= min_num_records:
                valid_gage_nums.append(gage_num)
        except NoSitesError:
            continue
    logging.info(f"Found {len(valid_gage_nums)} valid gage numbers in watershed")
    return valid_gage_nums
