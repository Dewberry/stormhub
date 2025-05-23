"""Creates grid file from metadata json created by extract_dss_metadata.py and add_coords_to_metadata.py in format similar to this:
{
  "19790222_72hr_st1_r265.dss": {
    "precip_pathname": "/SHG4K/TRINITY/PRECIPITATION/22FEB1979:0000/22FEB1979:0100/AORC/",
    "temperature_pathname": "/SHG4K/TRINITY/TEMPERATURE/22FEB1979:0100//AORC/",
    "storm_type": "st1",
    "rank": "r265",
    "storm_center_lon": -90.9016,
    "storm_center_lat": 31.1662
  },
  "19790302_72hr_st1_r118.dss": {
    "precip_pathname": "/SHG4K/TRINITY/PRECIPITATION/02MAR1979:0000/02MAR1979:0100/AORC/",
    "temperature_pathname": "/SHG4K/TRINITY/TEMPERATURE/02MAR1979:0100//AORC/",
    "storm_type": "st1",
    "rank": "r118",
    "storm_center_lon": -87.535,
    "storm_center_lat": 32.4662
  },
"""

import json
from pyproj import Transformer
from datetime import datetime
import logging
from stormhub.logger import initialize_logger

initialize_logger()


def parse_date_from_path(path):
    try:
        return datetime.strptime(path.strip("/").split("/")[3], "%d%b%Y:%H%M").date()
    except Exception:
        return None


def transform_coords(lon, lat, transformer):
    x, y = transformer.transform(lon, lat)
    return f"     Storm Center X: {x}\n", f"     Storm Center Y: {y}\n"


def build_lines(dss_data, transformer, defaults):
    lines = [
        "Grid Manager: T Transpose\n",
        "     Version: 4.11\n",
        "     Filepath Separator: \\\n",
        "End:\n\n",
    ]

    for dss_file, meta in sorted(
        dss_data.items(), key=lambda item: int(item[1].get("rank", "r0").lstrip("r"))
    ):  # sort by rank
        precip_path = meta.get("precip_pathname")
        temp_path = meta.get("temperature_pathname")
        storm_date = parse_date_from_path(precip_path or temp_path)
        dss_filename = f"data\\{dss_file}"

        if not storm_date:
            logging.error(f"Could not parse date for {dss_file}")
            continue

        for grid_type, path in [("Precipitation", precip_path), ("Temperature", temp_path)]:

            lines.append(f"Grid: {dss_file.replace('.dss', '')}\n")
            lines.append(f"     Grid Type: {grid_type}\n")
            lines.append(f"     Last Modified Date: {defaults['modified_date']}\n")
            lines.append(f"     Last Modified Time: {defaults['modified_time']}\n")
            lines.append(f"     Reference Height Units: {defaults['ref_units']}\n")
            lines.append(f"     Reference Height: {defaults['ref_height']}\n")
            lines.append("     Data Source Type: External DSS\n")
            lines.append(f"     Variant: {defaults['variant']}\n")
            lines.append(f"       Last Variant Modified Date: {defaults['modified_date']}\n")
            lines.append(f"       Last Variant Modified Time: {defaults['modified_time']}\n")
            lines.append("       Default Variant: Yes\n")
            lines.append(f"       DSS File Name: {dss_filename}\n")
            lines.append(f"       DSS Pathname: {path}\n")
            lines.append(f"     End Variant: {defaults['variant']}\n")
            lines.append(f"     Use Lookup Table: {defaults['use_lookup']}\n")

            if "storm_center_lon" in meta and "storm_center_lat" in meta:
                x_line, y_line = transform_coords(meta["storm_center_lon"], meta["storm_center_lat"], transformer)
                lines.append(x_line)
                lines.append(y_line)

            lines.append("End:\n\n")

    return lines


if __name__ == "__main__":
    metadata_path = "dss_metadata.json"
    output_grid_path = "T_Transpose_recreated.grid"

    output_crs = (
        'PROJCRS["USA_Contiguous_Albers_Equal_Area_Conic_USGS_version",'
        'BASEGEOGCRS["NAD83",DATUM["North American Datum 1983",'
        'ELLIPSOID["GRS 1980",6378137,298.257222101,LENGTHUNIT["metre",1]],'
        'ID["EPSG",6269]],PRIMEM["Greenwich",0,ANGLEUNIT["Degree",0.0174532925199433]]],'
        'CONVERSION["unnamed",METHOD["Albers Equal Area",ID["EPSG",9822]],'
        'PARAMETER["Latitude of false origin",23,ANGLEUNIT["Degree",0.0174532925199433],ID["EPSG",8821]],'
        'PARAMETER["Longitude of false origin",-96,ANGLEUNIT["Degree",0.0174532925199433],ID["EPSG",8822]],'
        'PARAMETER["Latitude of 1st standard parallel",29.5,ANGLEUNIT["Degree",0.0174532925199433],ID["EPSG",8823]],'
        'PARAMETER["Latitude of 2nd standard parallel",45.5,ANGLEUNIT["Degree",0.0174532925199433],ID["EPSG",8824]],'
        'PARAMETER["Easting at false origin",0,LENGTHUNIT["US survey foot",0.304800609601219],ID["EPSG",8826]],'
        'PARAMETER["Northing at false origin",0,LENGTHUNIT["US survey foot",0.304800609601219],ID["EPSG",8827]]],'
        'CS[Cartesian,2],AXIS["(E)",east,ORDER[1],LENGTHUNIT["US survey foot",0.304800609601219,ID["EPSG",9003]]],'
        'AXIS["(N)",north,ORDER[2],LENGTHUNIT["US survey foot",0.304800609601219,ID["EPSG",9003]]]]'
    )

    transformer = Transformer.from_crs("EPSG:4326", output_crs, always_xy=True)

    defaults = {
        "modified_date": "23 May 2025",
        "modified_time": "16:30:15",
        "ref_units": "Meters",
        "ref_height": 10.0,
        "variant": "Variant-1",
        "use_lookup": "No",
    }

    with open(metadata_path) as f:
        dss_data = json.load(f)

    lines = build_lines(dss_data, transformer, defaults)

    with open(output_grid_path, "w") as f:
        f.writelines(lines)

    logging.info(f"Created: {output_grid_path}")
