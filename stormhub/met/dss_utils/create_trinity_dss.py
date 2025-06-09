from datetime import datetime
import json
import os

from stormhub.met.zarr_to_dss import noaa_zarr_to_dss, NOAADataVariable

with open("storm_events.json") as f:
    storms = json.load(f)

dss_dir = "dss_outputs"
os.makedirs(dss_dir, exist_ok=True)

for date, attrs in storms.items():
    storm_start_datetime = datetime.strptime(date, "%Y-%m-%d")
    storm_start_str = datetime.strftime(storm_start_datetime, "%Y%m%d")
    output_name = f"{storm_start_str}_72h_{attrs['st_number']}_r{attrs['event_id']}.dss"

    output_dss_path = os.path.join(dss_dir, output_name)

    if os.path.exists(output_dss_path):
        print(f"Skipping creation for {output_dss_path} as it already exists.")
    else:
        noaa_zarr_to_dss(
            output_dss_path=output_dss_path,
            aoi_geometry_gpkg_path="trinity-transpo-area-v01.geojson",
            aoi_name="TRINITY",
            storm_start=storm_start_datetime,
            variable_duration_map={
                NOAADataVariable.TMP: 864,
                NOAADataVariable.APCP: 72,
            },
        )
