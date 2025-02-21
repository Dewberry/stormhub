import numpy as np
import pandas as pd
import scipy.stats as stats
from dataretrieval import nwis
import geopandas as gpd
from stormhub.hydro.usgs.usgs import new_gage_collection
from stormhub.hydro.plots import plot_log_pearson_iii
from stormhub.logger import initialize_logger

watershed = "C:\\Users\\sjanke\\Code\\stormhub\\bighorn\\bighorn.geojson"

def find_gages_in_watershed(watershed):

    watershed = gpd.read_file(watershed)
    bbox = [round(coord, 6) for coord in watershed.total_bounds.tolist()]

    gages_in_watershed_bbox = nwis.get_info(bBox=bbox)[0]

    watershed_geom = watershed.iloc[0].geometry
    gages_within_watershed = gages_in_watershed_bbox[gages_in_watershed_bbox.within(watershed_geom)]
    filtered_gages = gages_within_watershed[gages_within_watershed['site_no'].str.len() == 8]
    return(filtered_gages["site_no"].to_list())


initialize_logger()

gage_numbers = ["12105900", "12167000"] # Make this a list, created by a watershed function in hydro.utils
dir = "C:\\Users\\sjanke\\Code\\stormhub\\usgs_gages"
new_gage_collection(gage_nums, dir)