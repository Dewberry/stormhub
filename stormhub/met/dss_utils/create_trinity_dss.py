import os
import json
from datetime import datetime
from stormhub.met.zarr_to_dss import noaa_zarr_to_dss, NOAADataVariable


def load_storm_events(json_path: str) -> dict:
    """Load storm event metadata from a JSON file."""
    with open(json_path, "r") as f:
        return json.load(f)


def process_storm_events(storms: dict, dss_dir: str, aoi_path: str, aoi_name: str) -> None:
    """Process each storm event and generate DSS files."""
    for date, attrs in storms.items():
        storm_start_datetime = datetime.strptime(date, "%Y-%m-%d")
        storm_start_str = storm_start_datetime.strftime("%Y%m%d")
        output_name = f"{storm_start_str}_72h_{attrs['st_number']}_r{attrs['event_id']}.dss"
        output_dss_path = os.path.join(dss_dir, output_name)

        if os.path.exists(output_dss_path):
            print(f"Skipping creation for {output_dss_path} as it already exists.")
            continue

        noaa_zarr_to_dss(
            output_dss_path=output_dss_path,
            aoi_geometry_gpkg_path=aoi_path,
            aoi_name=aoi_name,
            storm_start=storm_start_datetime,
            variable_duration_map={
                NOAADataVariable.TMP: 864,
                NOAADataVariable.APCP: 72,
            },
        )


if __name__ == "__main__":
    json_path = "storm_events_redo.json"
    dss_dir = "dss_outputs"
    aoi_path = "trinity-transpo-area-v01.geojson"
    aoi_name = "TRINITY"

    storms = load_storm_events(json_path)
    os.makedirs(dss_dir, exist_ok=True)
    process_storm_events(storms, dss_dir, aoi_path, aoi_name)
