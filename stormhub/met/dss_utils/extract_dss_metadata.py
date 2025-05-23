"""Script to extract metadata from a directory of local dss files including the first precipitation and temperature path names,
the rank, and the stormtype."""

import os
import json
import re
from hecdss import HecDss
from datetime import datetime


def parse_d_part(d_part):
    """Converts D part of dss path to datetime."""
    try:
        return datetime.strptime(d_part, "%d%b%Y:%H%M")
    except Exception:
        return None


def extract_storm_type_and_rank(filename):
    """Strips the storm type and rank given a dss path in format yyymmdd_72hr_st(x)_r(xxx).dss ."""
    match = re.search(r"_([^_]+)_(r\d+)\.dss$", filename)
    storm_type = match.group(1)
    rank = match.group(2)
    return storm_type, rank


def generate_dss_metadata(dss_dir, output_path):
    """
    Generate metadata from DSS files including earliest precipitation and temperature paths.

    Args:
        dss_dir (str): Directory containing DSS files.
        output_path (str): Path to save the output JSON file.
    """
    result = {}

    for filename in os.listdir(dss_dir):
        if not filename.endswith(".dss"):
            continue

        filepath = os.path.join(dss_dir, filename)
        precip_path = None
        temp_path = None
        earliest_precip_time = None
        earliest_temp_time = None

        try:
            with HecDss(filepath) as dss:
                for path_obj in dss.get_catalog():
                    path = str(path_obj).strip("/")
                    parts = path.split("/")
                    if len(parts) < 6:
                        continue

                    part_c = parts[2].upper()
                    part_d = parts[3]
                    dt = parse_d_part(part_d)

                    if not dt:
                        continue

                    if part_c == "PRECIPITATION":
                        if precip_path is None or dt < earliest_precip_time:
                            precip_path = path_obj
                            earliest_precip_time = dt
                    elif part_c == "TEMPERATURE":
                        if temp_path is None or dt < earliest_temp_time:
                            temp_path = path_obj
                            earliest_temp_time = dt
        except Exception as e:
            print(f"ERROR reading {filename}: {e}")
            continue

        storm_type, rank = extract_storm_type_and_rank(filename)
        result[filename] = {
            "precip_pathname": str(precip_path) if precip_path else None,
            "temperature_pathname": str(temp_path) if temp_path else None,
            "storm_type": storm_type,
            "rank": rank,
        }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Saved pathnames to {output_path}")


if __name__ == "__main__":

    dss_dir = r"C:\Users\sjanke\code\stormhub\dss_utils\dss_downloads"  # directory of local dss files
    output_path = "dss_metadata.json"

    generate_dss_metadata(dss_dir, output_path)
