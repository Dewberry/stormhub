"""Updates the metadata json created by extract_dss_metadata.py to include storm center coordinates from stac items
by matching the dss rank to the stac item prefix and id."""

import os
import re
import json
import boto3
from io import BytesIO
from dotenv import load_dotenv
import logging
from stormhub.logger import initialize_logger

initialize_logger()
load_dotenv()
s3 = boto3.client("s3")


def extract_rank(filename):
    """Extract rank from filename, removing leading 0's ('_r003' -> '3')."""
    match = re.search(r"_r(\d+)", filename)
    return str(int(match.group(1))) if match else None


def update_dss_metadata_with_coords(json_path, dss_filenames, bucket, stac_prefix):
    """Add storm center coordinates to DSS metadata based on matched STAC items."""

    for dss_filename in dss_filenames:
        rank = extract_rank(dss_filename)
        if not rank:
            logging.error(f"Skipping {dss_filename}: no rank found.")
            continue

        stac_key = f"{stac_prefix}{rank}/{rank}.json"
        logging.info(f"Extracting coordinates from: {stac_key}")
        try:
            obj = s3.get_object(Bucket=bucket, Key=stac_key)
            item = json.load(obj["Body"])
            transform = item.get("properties", {}).get("aorc:transform", {})
            dss_filenames[dss_filename]["storm_center_lon"] = round(transform.get("storm_center_lon", 0), 4)
            dss_filenames[dss_filename]["storm_center_lat"] = round(transform.get("storm_center_lat", 0), 4)
        except Exception as e:
            logging.error(f"Failed to update {dss_filename}: {e}")

    with open(json_path, "w") as f:
        json.dump(dss_filenames, f, indent=2)

    logging.info(f"Updated storm center coordinates in {json_path}.")


def main(json_path, bucket_name, stac_prefix):
    with open(json_path, "r") as f:
        dss_filenames = json.load(f)
    update_dss_metadata_with_coords(json_path, dss_filenames, bucket_name, stac_prefix)


if __name__ == "__main__":
    bucket_name = "trinity-pilot"
    stac_prefix = "stac/prod-support/storms/72hr-events/"
    json_path = r"C:\Users\sjanke\code\stormhub\stormhub\met\dss_utils\dss_metadata.json"

    main(json_path, bucket_name, stac_prefix)

##### Function to update dss assets in stac items #####

# def update_stac_item(dss_key, bucket, stac_prefix, dss_description):
#     """Update the STAC item corresponding to a DSS file with new DSS asset metadata."""
#     filename = os.path.basename(dss_key)
#     rank = extract_rank(filename)
#     if not rank:
#         logging.info(f"Skipping {filename}: no rank found.")
#         return

#     json_key = f"{stac_prefix}{rank}/{rank}.json"

#     try:
#         obj = s3.get_object(Bucket=bucket, Key=json_key)
#         item = json.load(obj["Body"])
#     except s3.exceptions.NoSuchKey:
#         logging.info(f"STAC item not found for rank {rank}.")
#         return

#     if "dss" not in item.get("assets", {}):
#         logging.info(f"'dss' asset not found in {json_key}.")
#         return

#     item["assets"]["dss"]["href"] = f"../../../conformance/storm-catalog/storms/{filename}"
#     item["assets"]["dss"]["description"] = dss_description

#     s3.put_object(
#         Bucket=bucket,
#         Key=json_key,
#         Body=BytesIO(json.dumps(item, indent=2).encode("utf-8")),
#         ContentType="application/json",
#     )
#     logging.info(f"Updated STAC item for rank {rank} with DSS: {filename}")
