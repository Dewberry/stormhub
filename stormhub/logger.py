"""Logging utility and setup."""

import logging
import sys

SUPPRESS_LOGS = ["boto3", "botocore", "geopandas", "fiona", "rasterio", "pyogrio", "xarray", "shapely"]


def initialize_logger(json_logging: bool = False, level: int = logging.INFO):
    """Initialize the logger."""
    datefmt = "%Y-%m-%dT%H:%M:%SZ"
    if json_logging:
        for module in SUPPRESS_LOGS:
            logging.getLogger(module).setLevel(logging.WARNING)

        class FlushStreamHandler(logging.StreamHandler):
            def emit(self, record):
                super().emit(record)
                self.flush()

        handler = FlushStreamHandler(sys.stdout)

        logging.basicConfig(
            level=level,
            handlers=[handler],
            format="""{"time": "%(asctime)s" , "level": "%(levelname)s", "msg": "%(message)s"}""",
            datefmt=datefmt,
        )
    else:
        for package in SUPPRESS_LOGS:
            logging.getLogger(package).setLevel(logging.ERROR)
        logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s", datefmt=datefmt)
    # boto3.set_stream_logger(name="botocore.credentials", level=logging.ERROR)
