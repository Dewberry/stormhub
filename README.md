# StormHub
[![CI](https://github.com/dewberry/stormhub/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/dewberry/stormhub/actions/workflows/ci.yaml)
[![Documentation Status](https://readthedocs.org/projects/stormhub/badge/?version=latest)](https://stormhub.readthedocs.io/en/latest/?badge=latest)
[![Release](https://github.com/dewberry/stormhub/actions/workflows/release.yaml/badge.svg)](https://github.com/dewberry/stormhub/actions/workflows/release.yaml)
[![PyPI version](https://badge.fury.io/py/stormhub.svg)](https://badge.fury.io/py/stormhub)


**StormHub** is an open-source Python library designed to access and process publicly available hydrometeorological data to create catalogs, metadata, and data products for hydrologic modeling. This project automates the generation of STAC catalogs from storm and stream gage data, enabling improved analysis and simulation for flood studies and stochastic storm transposition (SST). StormHub aims to follow the principles of **[FAIR](https://www.nature.com/articles/sdata201618) (Findable, Accessible, Interoperable, and Reusable)** practices, ensuring that all catalogs can be easily reproduced, shared, published, and integrated into broader workflows.

## Overview
StormHub consists of two primary modules, with a focus on storm data and stream gage metadata:

### 1. Storm Transposition Module
This module extends the work of [RainyDay2](https://her.cee.wisc.edu/rainyday/rainyday-users-guide/) developed by Daniel Wright's Hydroclimate Extremes Research group at the University of Wisconsin-Madison. It allows users to perform [stochastic storm transposition](https://www.sciencedirect.com/science/article/abs/pii/S0022169420302766) (SST) by systematically shifting a watershed over a predefined transposition region and summing precipitation from existing datasets.

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
See the [User Guide](https://stormhub.readthedocs.io/en/latest/user_guide.html).

## Sources and References
- **AORC Dataset** - 1km hourly gridded precipitation data, available through NOAA.
- **RainyDay2** - Stochastic Storm Transposition framework by the [Hydroclimate Extremes Research Group](https://her.cee.wisc.edu/)
- **USGS Stream Gage Data** - Accessed via NWIS API.

## Output
- **STAC Catalogs** for storm and gage data.
- **DSS Files** for hydrologic modeling.
- JSON metadata files for integration with existing geospatial workflows.

## Attribution
This project builds on the work of Daniel Wright's [RainyDay2](https://her.cee.wisc.edu/rainyday/rainyday-users-guide/) and leverages publicly available datasets from NOAA and USGS.

## License
StormHub is licensed under the MIT License. See [LICENSE](LICENSE) for more information.
