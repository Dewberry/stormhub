import json
import logging
import os

if __name__ == "__main__":

    port = 8080
    local_directory = "/Users/slawler/Desktop/review/stormhub/catalogs"
    catalog_id = "indian-creek-catalog"
    os.system(
        f"python /Users/slawler/Desktop/review/stormhub/stormhub/server/serve.py {os.path.join(local_directory,catalog_id)}"
    )
