# StormHub

**StormHub** is an open-source Python library designed to access and process publicly available hydrometeorological data to create catalogs, metadata, and data products for hydrologic modeling. This project automates the generation of STAC catalogs from storm and stream gage data, enabling improved analysis and simulation for flood studies and stochastic storm transposition (SST). StormHub aims to follow the principles of **[FAIR](https://www.nature.com/articles/sdata201618) (Findable, Accessible, Interoperable, and Reusable)** data practices, ensuring that all catalogs can be easily shared, published, and integrated into broader workflows.

## Overview
StormHub consists of two primary modules, with a focus on storm data and stream gage metadata:

### 1. Storm Transposition Module
This module extends the work of [RainyDay2](https://hydroshare.org/resource/3b06e7b93e5a4f94a6d374b27e88b693/) developed by Daniel Wright's research lab at the University of Wisconsin-Madison. It allows users to perform [stochastic storm transposition](https://www.sciencedirect.com/science/article/abs/pii/S0022169420302766) (SST) by systematically shifting a watershed over a predefined transposition region and summing precipitation from existing datasets.

**Key Features:**
- Uses the recently published **[AORC](https://registry.opendata.aws/noaa-nws-aorc/)** hourly 1km gridded precipitation dataset.
- Sums precipitation over a time slice (e.g., 72 hours).
- Generates a catalog ranking storms by mean precipitation over the transposition region.
- Filters storms that exceed a minimum precipitation threshold.
- Stores qualified storms as STAC items with metadata, including:
  - Storm statistics (e.g., total precipitation, duration).
  - Centroid location of the watershed at the point of maximum mean precipitation.
- Links to associated watershed and transposition region STAC items.
- Supports creation of **DSS files** (hourly gridded) for use in HEC-HMS for hydrologic modeling.

### 2. USGS Gage Catalog Module *(Upcoming)*
This future module will create STAC catalogs of USGS stream gages, including frequency analysis data and metadata notes providing a *moment in time* copy of historic observations including discussion of any ommitted data points for reference. 

The catalogs will store:
- Frequency data as assets.
- Metadata supporting flood frequency analysis.
- Links to related datasets for direct comparison within SST workflows.

---

### STAC Server
StormHub includes an HTTP server that serves STAC items locally, allowing users to visualize and explore catalogs for both storms and stream gages. The server integrates with [Radiant Earth's STAC Browser](https://github.com/radiantearth/stac-browser) for seamless data viewing.

### FAIR Data Sharing and Publishing
StormHub facilitates FAIR data principles by enabling:
- Exporting catalogs as **zip files** for easy sharing and archiving.
- Publishing STAC items directly to a **STAC API**.
- Copying catalogs and metadata to **cloud blob stores** for scalable access and distribution.

## Installation
```bash
# Clone the repository
git clone https://github.com/dewberry/stormhub.git

# Navigate to the project directory
cd stormhub

# Install the package
pip install -e .
```

## Usage
```python

# Example in catalogs/example-input-data
config_file = "config.json" 
catalog_id = "indian-creek"
catalog_description="Indian Creek Catalog"
local_directory = "stormhub/catalogs"

# Initialize a storm catalg for the storm collection created in the next step
storm_catalog = new_catalog(
    catalog_id,
    config_file,
    local_directory=local_directory,
    catalog_description=catalog_description,
)

# Collection start date (First available date of AORC data) 
start_date = "1979-02-01"

# Collection end date (typically current date time) 
end_date = "1989-12-31"

# Number of top events to include in the collection
top_n_events = 40

# Choose duration (Consecutive hours of observed data)
storm_duration_hours = 72

# Choose the interval to search for storms. To check every hour set to 1, once a day set to 24
check_every_n_hours

# Set a minimum threshold for a storm (i.e. lower confidence interval for the duration)
min_precip_threshold = 2.81

# Search the AORC data to identify storms and create a new catalog
storm_collection = new_collection(
    storm_catalog,
    start_date,
    end_date,
    storm_duration_hours,
    min_precip_threshold,
    top_n_events,
    check_every_n_hours=6,
)
```

## Sources and References
- **AORC Dataset** - 1km hourly gridded precipitation data, available through NOAA.
- **RainyDay2** - Stochastic Storm Transposition framework by Daniel Wright's lab. [HydroShare link](https://hydroshare.org/resource/3b06e7b93e5a4f94a6d374b27e88b693/)
- **USGS Stream Gage Data** - Accessed via NWIS API.

## Output
- **STAC Catalogs** for storm and gage data.
- **DSS Files** for hydrologic modeling.
- JSON metadata files for integration with existing geospatial workflows.

## Attribution
This project builds on the work of Daniel Wright's [RainyDay2](https://hydroshare.org/resource/3b06e7b93e5a4f94a6d374b27e88b693/) and leverages publicly available datasets from NOAA and USGS.

## License
StormHub is licensed under the MIT License. See [LICENSE](LICENSE) for more information.

## Contributing
Contributions are welcome! Please submit issues and pull requests through the [GitHub repository](https://github.com/slawler/stormhub).

---
For more information, visit the project repository: [https://github.com/dewberry/stormhub](https://github.com/slawler/stormhub).

