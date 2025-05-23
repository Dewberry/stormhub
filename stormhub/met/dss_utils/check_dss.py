"""Script to validate dss files against expected lengths for each dss path Part C variable."""

import boto3
import os
import logging
from hecdss import HecDss
from dotenv import load_dotenv

# log to a file
logging.basicConfig(filename="dss_validation.log", level=logging.INFO, format="%(message)s")

load_dotenv()
s3 = boto3.client("s3")

EXPECTED_LENGTHS = {"PRECIPITATION": 72, "TEMPERATURE": 864}  # Expected number of part C dss paths.


def list_dss_files(bucket_name, prefix):
    """
    List all .dss files located directly under the specified S3 bucket and prefix.

    Yields:
        str: S3 key for each .dss file found.
    """
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key.endswith(".dss") and "/" not in key[len(prefix) :]:
            yield key


def check_dss_file(s3_key, bucket_name, download_dir):
    """Downloads and validates given dss s3 key."""

    filename = os.path.join(download_dir, os.path.basename(s3_key))
    s3.download_file(bucket_name, s3_key, filename)

    results = {"PRECIPITATION": 0, "TEMPERATURE": 0}

    try:
        with HecDss(filename) as dss:
            catalog = dss.get_catalog()
            for path_obj in catalog:
                path = str(path_obj)
                parts = path.strip("/").split("/")
                part_c = parts[2].upper()
                if part_c in results:
                    results[part_c] += 1
    except Exception as e:
        logging.error(f"ERROR opening {s3_key} - {str(e)}")
        return

    if results == EXPECTED_LENGTHS:
        logging.info(f"PASS - {s3_key} - {results}")
    else:
        logging.info(f"FAIL - {s3_key} - {results}")


def main(bucket_name, prefix, download_dir):

    os.makedirs(download_dir, exist_ok=True)

    for dss_key in list_dss_files(bucket_name, prefix):
        try:
            check_dss_file(dss_key, bucket_name, download_dir)
        except Exception as e:
            logging.error(f"ERROR - {dss_key} - {str(e)}")


if __name__ == "__main__":

    bucket_name = "trinity-pilot"
    prefix = "stac/prod-support/conformance/storm-catalog/storms/"
    download_dir = "dss_downloads"

    main(bucket_name, prefix, download_dir)
