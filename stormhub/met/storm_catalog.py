"""Module for processing and creating stormhub STAC objects."""

import json
import logging
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, List, Union

import pandas as pd
import pystac
from pystac import Asset, Collection, Item, Link, MediaType
from shapely.geometry import mapping, shape

from stormhub.hydro_domain import HydroDomain
from stormhub.logger import initialize_logger
from stormhub.met.analysis import StormAnalyzer
from stormhub.met.aorc.aorc import AORCItem, valid_spaces_item
from stormhub.utils import (
    STORMHUB_REF_LINK,
    StacPathManager,
    generate_date_range,
    validate_config,
)


class StormCollection(pystac.Collection):
    """Storm Collection class."""

    def __init__(self, collection_id: str, items: List[pystac.Item]):
        """
        Initialize a StormCollection instance.

        Args:
            collection_id (str): The ID of the collection.
            items (List[pystac.Item]): List of STAC items to include in the collection.
        """
        spatial_extents = [item.bbox for item in items if item.bbox]
        temporal_extents = [item.datetime for item in items if item.datetime is not None]

        collection_extent = pystac.Extent(
            spatial=pystac.SpatialExtent(
                bboxes=[
                    [
                        min(b[0] for b in spatial_extents),
                        min(b[1] for b in spatial_extents),
                        max(b[2] for b in spatial_extents),
                        max(b[3] for b in spatial_extents),
                    ]
                ]
            ),
            temporal=pystac.TemporalExtent(intervals=[[min(temporal_extents), max(temporal_extents)]]),
        )

        super().__init__(
            id=collection_id,
            description="STAC collection generated from storm items",
            extent=collection_extent,
        )

        for item in items:
            self.add_item_to_collection(item)

        self.add_link(STORMHUB_REF_LINK)

    @classmethod
    def from_collection(cls, collection: pystac.Collection) -> "StormCollection":
        """
        Create a StormCollection from an existing pystac.Collection.

        Args:
            collection (pystac.Collection): The existing STAC collection.

        Returns
        -------
            StormCollection: A new StormCollection instance.
        """
        items = list(collection.get_all_items())
        return cls(collection.id, items)

    def add_item_to_collection(self, item: Item, override: bool = False):
        """
        Add an item to the collection.

        Args:
            item (Item): The STAC item to add.
            override (bool): Whether to override an existing item with the same ID.
        """
        existing_ids = {item.id for item in self.get_all_items()}

        if item.id in existing_ids:
            if override:
                self.remove_item(item.id)
                self.add_item(item)
                logging.info("Overwriting (existing) item with ID '%s'.", item.id)
            else:
                logging.error(
                    "Item with ID '%s' already exists in the collection. Use `override=True` to overwrite.",
                    item.id,
                )

        else:
            self.add_item(item)
            logging.info("Added item with ID '%s' to the collection.", item.id)

    def add_summary_stats(self, spm: StacPathManager, property_name: str = "aorc:statistics", statistic: str = "mean"):
        """
        Add summary statistics to the collection.

        Args:
            spm (StacPathManager): The STAC path manager.
            property_name (str): The property name to summarize.
            statistic (str): The statistic to calculate (e.g., "mean").
        """
        values = []
        for item in self.get_all_items():
            if property_name in item.properties:
                values.append(item.properties[property_name].get(statistic))

        if values:
            min_value = min(values)
            max_value = max(values)
        else:
            min_value, max_value = None, None

        if "summaries" not in self.extra_fields:
            self.extra_fields["summaries"] = {}

        if min_value is not None and max_value is not None:
            self.extra_fields["summaries"][f"{property_name} precip (inches)"] = {
                "minimum": min_value,
                "maximum": max_value,
            }
        else:
            logging.warning("No values found for %s in collection: %s", property_name, self.id)
            self.extra_fields["summaries"][f"{property_name} precip (inches)"] = {
                "minimum": 0,
                "maximum": 0,
            }

        logging.info(
            "Summary statistics for %s: %s - %s saved at %s",
            property_name,
            min_value,
            max_value,
            spm.collection_file(self.id),
        )

        self.save_object(dest_href=spm.collection_file(self.id), include_self_link=False)

    def event_feature_collection(self, spm: StacPathManager, threshold: float):
        """
        Create a feature collection of storm events.

        Args:
            spm (StacPathManager): The STAC path manager.
            threshold (float): The precipitation threshold for including events.
        """
        features = []
        for item in self.get_all_items():
            geom = shape(item.geometry)
            if geom.is_empty:
                continue

            feature = {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "id": item.id,
                    "storm_start_date": item.properties.get("start_datetime").split("T")[0],
                    "aorc:statistics": item.properties.get("aorc:statistics"),
                },
            }
            features.append(feature)

        feature_collection = {"type": "FeatureCollection", "features": features}

        output_geojson = spm.collection_asset(self.id, "top-storms.geojson")
        with open(output_geojson, "w", encoding="utf-8") as f:
            json.dump(feature_collection, f, indent=4)

        self.add_asset(
            "storm-events",
            Asset(
                href=spm.collection_asset(self.id, "top-storms.geojson"),
                title="Storm Summary",
                description=f"Feature collection of all events with mean precipitation greater than {threshold}",
                media_type=MediaType.GEOJSON,
                roles=["storm_summary"],
            ),
        )

        logging.info("FeatureCollection saved to %s", output_geojson)
        self.save_object(dest_href=spm.collection_file(self.id), include_self_link=False)


class StormCatalog(pystac.Catalog):
    """
    Initialize a StormCatalog instance.

    Args:
        id (str): The ID of the catalog.
        watershed (HydroDomain): The watershed domain.
        transposition_region (HydroDomain): The transposition region domain.
        description (str): Description of the catalog.
        local_dir (str): Local directory for the catalog.
        valid_transposition_region (HydroDomain, optional): Valid transposition region domain.
        **kwargs (Any): Additional keyword arguments.
    """

    def __init__(
        self,
        catalog_id: str,
        watershed: HydroDomain,
        transposition_region: HydroDomain,
        description: str,
        local_dir: str,
        valid_transposition_region: HydroDomain = None,
        **kwargs: Any,
    ):
        super().__init__(id=catalog_id, description=description)
        self.catalog_type = pystac.CatalogType.SELF_CONTAINED
        self.local_dir = local_dir
        self.spm = StacPathManager(local_dir)
        self._watershed = self.add_hydro_domain(watershed)
        self._transposition_region = self.add_hydro_domain(transposition_region)
        if valid_transposition_region:
            self._valid_transposition_region = self.add_hydro_domain(valid_transposition_region)
        else:
            self._valid_transposition_region = None

        if "links" in kwargs:
            self.links = kwargs.get("links", [])
        self.set_self_href(self.spm.catalog_file)

    @classmethod
    def from_file(cls, file_path: str) -> "StormCatalog":
        """Create a StormCatalog from a file.

        Args:
            file_path (str): Path to the catalog file.

        Returns
        -------
            StormCatalog: A new StormCatalog instance.
        """
        catalog = pystac.Catalog.from_file(file_path)
        links = catalog.get_links()
        spm = StacPathManager(os.path.dirname(file_path))
        watershed = get_item_from_catalog_link(links, "Watershed", spm=spm)
        transposition_region = get_item_from_catalog_link(links, "Transposition Region", spm=spm)
        valid_transposition_region = get_item_from_catalog_link(links, "Valid Transposition Region", spm=spm)

        if not watershed or not transposition_region:
            raise ValueError("Both watershed and transposition region must be defined in the catalog.")

        return cls(
            catalog_id=catalog.id,
            watershed=watershed,
            transposition_region=transposition_region,
            description=catalog.description,
            local_dir=os.path.dirname(file_path),
            valid_transposition_region=valid_transposition_region,
            links=links,
        )

    @property
    def valid_transposition_region(self) -> Item:
        """
        Get the valid transposition region from the catalog links.

        Returns
        -------
            Item: The valid transposition region item.
        """
        # if self._valid_transposition_region is None:
        #     vtr_polygon = valid_spaces_item(self.watershed, self.transposition_region)
        #     vtr_id = f"{self.transposition_region.id}_valid"
        #     vtr = HydroDomain(
        #         id=vtr_id,
        #         geometry=vtr_polygon,
        #         hydro_domain_type="valid_transposition_region",
        #         description=f"Valid transposition region for {self.watershed.id} watershed",
        #         href=self.spm.catalog_item(vtr_id),
        #         title="Valid Transposition Region",
        #     )
        #     self.add_item(vtr)
        #     vtr.save_object(include_self_link=False)
        #     self._valid_transposition_region = vtr
        return get_item_from_catalog_link(self.links, "Valid Transposition Region", spm=self.spm)

    @property
    def transposition_region(self) -> Item:
        """
        Get the transposition region from the catalog links.

        Returns
        -------
            Item: The transposition region item.
        """
        return get_item_from_catalog_link(self.links, "Transposition Region", spm=self.spm)

    @property
    def watershed(self) -> Item:
        """
        Get the watershed from the catalog links.

        Returns
        -------
            Item: The watershed item.
        """
        return get_item_from_catalog_link(self.links, "Watershed", spm=self.spm)

    def sanitize_catalog_assets(self):
        """Force the asset paths in the catalog relative to root."""
        for collection in self.get_all_collections():
            for asset in collection.assets.values():
                if self.spm.collection_dir(collection.id).replace("\\", "/") in asset.href:
                    asset.href = asset.href.replace(self.spm.collection_dir(collection.id).replace("\\", "/"), ".")
                elif self.spm.catalog_dir.replace("\\", "/") in asset.href:
                    asset.href = asset.href.replace(self.spm.catalog_dir.replace("\\", "/"), "..")

            for item in collection.get_all_items():
                for asset in item.assets.values():
                    if self.spm.collection_item_dir(collection.id, item.id) in asset.href:
                        asset.href = asset.href.replace(self.spm.collection_item_dir(collection.id, item.id), ".")
                    elif self.spm.collection_dir(collection.id) in asset.href:
                        asset.href = asset.href.replace(self.spm.collection_dir(collection.id), ".")
                    elif self.spm.catalog_dir in asset.href:
                        asset.href = asset.href.replace(self.spm.catalog_dir, "..")
            collection.save()

    def add_hydro_domain(self, hydro_domain: Union[HydroDomain, Item]) -> str:
        """
        Add a hydro domain to the catalog.

        Args:
            hydro_domain (Union[HydroDomain, Item]): The hydro domain to add.

        Returns
        -------
            str: The ID of the added hydro domain.
        """
        if not isinstance(hydro_domain, (HydroDomain, Item)):
            raise ValueError(f"Expected a HydroDomain or an Item object not: {type(hydro_domain)}")
        try:
            title = hydro_domain.title
        except AttributeError:
            title = hydro_domain.id

        self.add_link(
            Link(
                rel="item",
                target=self.spm.catalog_asset(hydro_domain.id).replace(self.spm.catalog_dir, "."),
                title=title,
                media_type=pystac.MediaType.GEOJSON,
                extra_fields={
                    "Name": hydro_domain.id,
                    "Description": f"Input {hydro_domain.id} used to generate this catalog",
                },
            )
        )
        return hydro_domain.id

    def get_storm_collection(self, collection_id: str) -> StormCollection:
        """
        Get a storm collection from the catalog.

        Args:
            collection_id (str): The ID of the collection.

        Returns
        -------
            StormCollection: The storm collection.
        """
        collection = self.get_child(collection_id)
        if not collection:
            raise ValueError(f"Collection with ID '{collection_id}' not found in the catalog.")
        return StormCollection.from_collection(collection)

    def save_catalog(self):
        """Save the catalog and its collections."""
        for collection in self.get_all_collections():
            collection.save_object(dest_href=self.spm.collection_file(collection.id), include_self_link=False)
        self.sanitize_catalog_assets()
        self.save()

    def add_collection_to_catalog(self, collection: Collection, override: bool = False):
        """
        Add a collection to the catalog.

        Args:
            collection (Collection): The collection to add.
            override (bool): Whether to override an existing collection with the same ID.
        """
        existing_collections = {c.id for c in self.get_all_collections()}
        logging.info("Existing collection IDs: %s", existing_collections)

        if collection.id in existing_collections:
            if override:
                self.remove_child(collection.id)
                self.add_child(collection, title=collection.id)
                logging.info("Overwriting (existing) collection with ID '%s'.", collection.id)
            else:
                logging.error(
                    "Collection with ID '%s' already exists in the collection. Use `override=True` to overwrite.",
                    collection.id,
                )

        else:
            self.add_child(collection, title=collection.id)
            logging.info("Added collection with ID '%s' to the catalog.", collection.id)

    def new_collection_from_items(self, collection_id: str, items: List[Item]) -> StormCollection:
        """
        Create a new collection from a list of items.

        Args:
            collection_id (str): The ID of the new collection.
            items (List[Item]): List of items to include in the collection.

        Returns
        -------
            StormCollection: The new storm collection.
        """
        collection = StormCollection(collection_id, items)
        collection.add_asset(
            "valid-transposition-region",
            pystac.Asset(
                href=self.valid_transposition_region.self_href,
                title="Valid Transposition Region",
                description=f"Valid transposition region for {self.watershed.id} watershed",
                media_type=pystac.MediaType.GEOJSON,
                roles=["valid_transposition_region"],
            ),
        )

        collection.add_asset(
            "watershed",
            pystac.Asset(
                href=self.watershed.self_href,
                title="Watershed",
                description=f"{self.watershed.id} watershed",
                media_type=pystac.MediaType.GEOJSON,
                roles=["watershed"],
            ),
        )

        collection.save_object(dest_href=self.spm.collection_file(collection_id), include_self_link=False)
        self.add_collection_to_catalog(collection, override=True)
        self.sanitize_catalog_assets()
        return collection

    def sort_collection(self, collection_id: Collection, property_name: str):
        """
        Sort and save a STAC collection based on a specific property.

        Args:
            collection (Collection): The STAC collection to sort and save.
            property_name (str): The property name to sort by.
        """
        collection = self.get_storm_collection(collection_id)
        sorted_items = sorted(collection.get_all_items(), key=lambda item: item.properties.get(property_name))

        return StormCollection(collection.id, sorted_items)

    def add_rank_to_collection(
        self,
        collection_id: str,
        top_events: pd.DataFrame,
    ) -> StormCollection:
        """
        Create a new collection from a list of items.

        Args:
            collection_id (str): The ID of the new collection.
            items (List[Item]): List of items to include in the collection.

        Returns
        -------
            StormCollection: The new storm collection.
        """
        collection = self.get_storm_collection(collection_id)

        top_events.loc[:, "storm_id"] = top_events["storm_date"].apply(lambda x: f"{x.strftime('%Y-%m-%dT%H')}")
        for item in collection.get_all_items():
            matching_events = top_events[top_events["storm_id"] == item.id]
            if not matching_events.empty:
                item.properties["aorc:calendar_year_rank"] = int(matching_events.iloc[0]["annual_rank"])
                item.properties["aorc:collection_rank"] = int(matching_events.iloc[0]["por_rank"])

        collection = self.sort_collection(collection_id, "aorc:collection_rank")
        collection.add_asset(
            "valid-transposition-region",
            pystac.Asset(
                href=self.valid_transposition_region.self_href,
                title="Valid Transposition Region",
                description=f"Valid transposition region for {self.watershed.id} watershed",
                media_type=pystac.MediaType.GEOJSON,
                roles=["valid_transposition_region"],
            ),
        )

        collection.add_asset(
            "watershed",
            pystac.Asset(
                href=self.watershed.self_href,
                title="Watershed",
                description=f"{self.watershed.id} watershed",
                media_type=pystac.MediaType.GEOJSON,
                roles=["watershed"],
            ),
        )

        collection.save_object(dest_href=self.spm.collection_file(collection_id), include_self_link=False)
        self.add_collection_to_catalog(collection, override=True)
        self.sanitize_catalog_assets()
        return collection


def storm_search(
    catalog: StormCatalog,
    storm_start_date: datetime,
    storm_duration_hours: int,
    por_rank: int = None,
    return_item: bool = False,
    scale_max: float = 12.0,
    collection_id: str = None,
) -> Union[dict, AORCItem]:
    """
    Search for a storm event.

    Args:
        catalog (StormCatalog): The storm catalog.
        storm_start_date (datetime): The start date of the storm.
        storm_duration_hours (int): The duration of the storm in hours.
        return_item (bool): Whether to return the storm item.
        scale_max (float): The maximum scale for the thumbnail.
        collection_id (str): The ID of the collection.

    Returns
    -------
        Union[dict, AORCItem]: The storm search results or the storm item.
    """
    if not collection_id:
        collection_id = catalog.spm.storm_collection_id(storm_duration_hours)
    watershed = catalog.watershed
    valid_transposition_domain = catalog.valid_transposition_region

    logging.debug(
        "%s: searching %s - for max %d hr event.",
        storm_start_date.strftime("%Y-%m-%dT%H"),
        watershed.id,
        storm_duration_hours,
    )
    if por_rank:
        item_id = f"{por_rank}"
    else:
        item_id = f"{storm_start_date.strftime('%Y-%m-%dT%H')}"
    item_dir = catalog.spm.collection_item_dir(collection_id, item_id)

    event_item = AORCItem(
        item_id,
        storm_start_date,
        timedelta(hours=storm_duration_hours),
        shape(watershed.geometry),
        shape(valid_transposition_domain.geometry),
        item_dir,
        watershed.id,
        valid_transposition_domain.id,
        href=catalog.spm.collection_item(collection_id, item_id),
    )

    _, _, event_stats, centroid = event_item.max_transpose()
    logging.debug("Centroid: %s", centroid)
    logging.debug("Statistics: %s", event_stats)
    logging.debug("Storm Date: %s", storm_start_date.strftime("%Y-%m-%dT%H"))
    logging.debug("Destination href: %s", catalog.spm.collection_item(collection_id, event_item.id))
    if return_item:
        if not os.path.exists(item_dir):
            os.makedirs(item_dir)
        event_item.aorc_thumbnail(scale_max=scale_max)
        event_item.save_object(dest_href=catalog.spm.collection_item(collection_id, event_item.id))
        return event_item
    else:
        return {
            "storm_date": storm_start_date.strftime("%Y-%m-%dT%H"),
            "centroid": centroid,
            "aorc:statistics": event_stats,
        }


def serial_processor(
    func: callable,
    catalog: StormCatalog,
    storm_duration: int,
    output_csv: str,
    event_dates: list[datetime],
    with_tb: bool = False,
):
    """
    Run function in serial using only one processor.

    Args:
        func (callable): The function to run.
        catalog (StormCatalog): The storm catalog.
        storm_duration (int): The duration of the storm.
        output_csv (str): Path to the output CSV file.
        event_dates (list[datetime]): List of event dates.
        with_tb (bool): Whether to include traceback in error logs.
    """
    if not os.path.exists(output_csv):
        with open(output_csv, "w", encoding="utf-8") as f:
            f.write("storm_date,min,mean,max,x,y\n")

    count = len(event_dates)

    with open(output_csv, "a", encoding="utf-8") as f:
        for date in event_dates:
            try:
                r = func(catalog, date, storm_duration)
                f.write(storm_search_results_to_csv_line(r))
                logging.info("%s processed (%d remaining)", r["storm_date"], count)
                count -= 1
            except Exception as e:
                if with_tb:
                    tb = traceback.format_exc()
                    logging.error("Error processing: %s\n%s", e, tb)
                else:
                    logging.error("Error processing: %s", e)


def multi_processor(
    func: callable,
    catalog: StormCatalog,
    storm_duration: int,
    output_csv: str,
    event_dates: list[datetime],
    num_workers: int = None,
    use_threads: bool = False,
    with_tb: bool = False,
):
    """
    Run function in parallel using multiple processors or threads.

    TODO: Consider using this for `storm_search` in creating items as well as collecting event stats.

    Args:
        func (callable): The function to run.
        catalog (StormCatalog): The storm catalog.
        storm_duration (int): The duration of the storm.
        output_csv (str): Path to the output CSV file.
        event_dates (list[datetime]): List of event dates.
        num_workers (int, optional): Number of workers to use.
        use_threads (bool): Whether to use threads instead of processes.
        with_tb (bool): Whether to include traceback in error logs.
    """
    if use_threads:
        executor = ThreadPoolExecutor
    else:
        executor = ProcessPoolExecutor

    if not os.path.exists(output_csv):
        # append_mode=True
        with open(output_csv, "w", encoding="utf-8") as f:
            f.write("storm_date,min,mean,max,x,y\n")

    count = len(event_dates)

    with open(output_csv, "a", encoding="utf-8") as f:
        with executor(max_workers=num_workers) as executor:
            futures = [executor.submit(func, catalog, date, storm_duration) for date in event_dates]
            for future in as_completed(futures):
                count -= 1
                try:
                    r = future.result()
                    f.write(storm_search_results_to_csv_line(r))
                    logging.info("%s processed (%d remaining)", r["storm_date"], count)

                except Exception as e:
                    if with_tb:
                        tb = traceback.format_exc()
                        logging.error("Error processing: %s\n%s", e, tb)
                        continue
                    else:
                        logging.error("Error processing: %s", e)
                        continue


def collect_event_stats(
    event_dates: list[datetime],
    catalog: StormCatalog,
    collection_id: str = None,
    storm_duration: int = 72,
    num_workers: int = None,
    use_threads: bool = False,
    with_tb: bool = False,
    use_parallel_processing: bool = True,
):
    """
    Collect statistics for storm events.

    Args:
        event_dates (list[datetime]): List of event dates.
        catalog (StormCatalog): The storm catalog.
        collection_id (str, optional): The ID of the collection.
        storm_duration (int): The duration of the storm.
        num_workers (int, optional): Number of workers to use.
        use_threads (bool): Whether to use threads instead of processes.
        with_tb (bool): Whether to include traceback in error logs.
        use_parallel_processing (bool): Whether to process storm stats using parallel processing.
    """
    if not collection_id:
        collection_id = catalog.spm.storm_collection_id(storm_duration)

    collection_dir = catalog.spm.collection_dir(collection_id)

    if not os.path.exists(collection_dir):
        os.makedirs(collection_dir)

    if not num_workers and not use_threads:
        if os.cpu_count() > 2:
            num_workers = os.cpu_count() - 2
        else:
            num_workers = 1
    elif not num_workers and use_threads:
        num_workers = 15

    output_csv = os.path.join(collection_dir, "storm-stats.csv")
    if use_parallel_processing:
        logging.info("Using %s cpu's for collecting event stats", num_workers)
        multi_processor(
            func=storm_search,
            catalog=catalog,
            storm_duration=storm_duration,
            output_csv=output_csv,
            event_dates=event_dates,
            num_workers=num_workers,
            use_threads=use_threads,
            with_tb=with_tb,
        )
    else:
        logging.info("Processing event stats serially.")
        serial_processor(
            func=storm_search,
            catalog=catalog,
            storm_duration=storm_duration,
            output_csv=output_csv,
            event_dates=event_dates,
            with_tb=with_tb,
        )


def create_items(
    event_dates: list[dict],
    catalog: StormCatalog,
    collection_id: str = None,
    storm_duration: int = 72,
    num_workers: int = None,
    with_tb: bool = False,
) -> List:
    """
    Create items for storm events, setting the item ID to `por_rank` instead of storm_date.

    Args:
        event_dates (list[dict]): List of event metadata (includes storm_date & por_rank).
        catalog (StormCatalog): The storm catalog.
        collection_id (str, optional): The ID of the collection.
        storm_duration (int): The duration of the storm.
        num_workers (int, optional): Number of workers to use.
        with_tb (bool): Whether to include traceback in error logs.

    Returns
    -------
        list: List of created event items.
    """
    event_items = []

    if not collection_id:
        collection_id = catalog.spm.storm_collection_id(storm_duration)

    collection_dir = catalog.spm.collection_dir(collection_id)
    if not os.path.exists(collection_dir):
        os.makedirs(collection_dir)

    count = len(event_dates)

    if not num_workers:
        num_workers = os.cpu_count()

    storm_data = [(e["storm_date"], e["por_rank"]) for e in event_dates]

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(
                storm_search,
                catalog,
                storm_date,
                storm_duration,
                por_rank=por_rank,
                collection_id=collection_id,
                return_item=True,
            )
            for storm_date, por_rank in storm_data
        ]

        for future in as_completed(futures):
            count -= 1
            try:
                r = future.result()
                logging.info("%s processed (%d remaining)", r.datetime, count)
                event_items.append(r)

            except Exception as e:
                if with_tb:
                    tb = traceback.format_exc()
                    logging.error("Error processing: %s\n%s", e, tb)
                else:
                    logging.error("Error processing: %s", e)

    return event_items


def init_storm_catalog(
    catalog_id: str, config: dict, local_catalog_dir: str, create_valid_transposition_region: bool = False
) -> pystac.Catalog:
    """
    Initialize a storm catalog.

    Args:
        catalog_id (str): The ID of the catalog.
        config (dict): Configuration dictionary.
        local_catalog_dir (str): Local directory for the catalog.
        create_valid_transposition_region (bool): Whether to create a valid transposition region.

    Returns
    -------
        pystac.Catalog: The initialized catalog.
    """
    watershed_config = config.get("watershed")
    tr_config = config.get("transposition_region")

    spm = StacPathManager(local_catalog_dir)

    if not os.path.exists(spm.catalog_dir):
        os.makedirs(spm.catalog_dir, exist_ok=True)

    logging.info("Creating `transposition_region` item for catalog: %s", catalog_id)
    transposition_region = HydroDomain(
        item_id=tr_config.get("id"),
        geometry=tr_config.get("geometry_file"),
        hydro_domain_type="transposition_region",
        description=tr_config.get("description"),
        title="Transposition Region",
    )
    transposition_region.save_object(dest_href=spm.catalog_asset(tr_config.get("id")), include_self_link=False)

    logging.info("Creating `watershed` item for catalog: %s", catalog_id)
    watershed = HydroDomain(
        item_id=watershed_config.get("id"),
        geometry=watershed_config.get("geometry_file"),
        hydro_domain_type="watershed",
        description=watershed_config.get("description"),
        title="Watershed",
    )
    watershed.save_object(dest_href=spm.catalog_asset(watershed_config.get("id")), include_self_link=False)

    if create_valid_transposition_region:
        logging.info("Creating `valid_transposition_region` item for catalog: %s", catalog_id)
        vtr_polygon = valid_spaces_item(watershed, transposition_region)
        vtr_id = f"{tr_config.get('id')}_valid"
        vtr = HydroDomain(
            item_id=vtr_id,
            geometry=vtr_polygon,
            hydro_domain_type="valid_transposition_region",
            description=f"Valid transposition region for {watershed.id} watershed",
            title="Valid Transposition Region",
        )
        vtr.save_object(dest_href=spm.catalog_asset(vtr_id), include_self_link=False)
        return watershed, transposition_region, vtr

    return watershed, transposition_region


def get_item_from_catalog_link(links: list, link_title: str, spm: StacPathManager) -> Item:
    """
    Get an item from the catalog links.

    Args:
        links (list): List of catalog links.
        link_title (str): The title of the link.
        spm (StacPathManager): The STAC path manager.

    Returns
    -------
        Item: The item from the catalog link.
    """
    matched_links = [link for link in links if link.title == link_title]
    if len(matched_links) == 0:
        return None
    if len(matched_links) > 1:
        raise ValueError(f"Multiple links found with title: {link_title}")

    relative_path = matched_links[0].target.replace("./", "")
    absolute_path = os.path.join(spm.catalog_dir, relative_path)

    absolute_path = os.path.abspath(absolute_path)

    item = pystac.read_file(absolute_path)
    if not isinstance(item, Item):
        raise ValueError(f"Expected an Item object at {absolute_path} not : {type(item)}")
    return item


def storm_search_results_to_csv_line(storm_search_results: dict) -> str:
    """
    Convert storm search results to a CSV line.

    Args:
        storm_search_results (dict): The storm search results.

    Returns
    -------
        str: The CSV line.
    """
    event_stats = storm_search_results["aorc:statistics"]
    storm_date = storm_search_results["storm_date"]
    centroid = storm_search_results["centroid"]
    stats = f"{event_stats['min']},{event_stats['mean']},{event_stats['max']}"
    return f"{storm_date},{stats},{centroid.x},{centroid.y}\n"


def find_missing_storm_dates(file_path: str, start_date: str, stop_date: str, every_n_hours: int) -> List:
    """
    Find missing storm dates in a CSV file.

    Args:
        file_path (str): Path to the CSV file.
        start_date (str): The start date.
        stop_date (str): The stop date.
        every_n_hours (int): The interval in hours.

    Returns
    -------
        list: List of missing storm dates.
    """
    df = pd.read_csv(file_path)
    df["storm_date"] = pd.to_datetime(df["storm_date"], format="%Y-%m-%dT%H")
    logging.info("Loaded %d storm events from %s", len(df), file_path)

    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
    stop_datetime = datetime.strptime(stop_date, "%Y-%m-%d")
    duration = timedelta(hours=every_n_hours)

    complete_range = pd.date_range(start=start_datetime, end=stop_datetime, freq=duration)
    logging.info("Expecting %d storm events for %s - %s", len(complete_range), start_date, stop_date)

    existing_datetimes = set(df["storm_date"])
    missing_datetimes = [dt for dt in complete_range if dt not in existing_datetimes]

    return missing_datetimes


def new_catalog(
    catalog_id: str,
    config_file: str,
    local_directory: str = None,
    catalog_description: str = "",
) -> StormCatalog:
    """
    Create a new storm catalog.

    Args:
        catalog_id (str): The ID of the catalog.
        config_file (str): Path to the configuration file.
        local_directory (str, optional): Local directory for the catalog.
        catalog_description (str): Description of the catalog.

    Returns
    -------
        StormCatalog: The new storm catalog.
    """
    # Step 1: Load config
    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)
    validate_config(config)

    # Step 2: Create catalog
    if not local_directory:
        local_directory = os.getcwd()

    # Utility class to force and manage paths
    spm = StacPathManager(os.path.join(local_directory, catalog_id))

    watershed, transposition_region, vtr = init_storm_catalog(
        catalog_id, config, spm.catalog_dir, create_valid_transposition_region=True
    )

    storm_catalog = StormCatalog(
        catalog_id,
        watershed,
        transposition_region,
        catalog_description,
        spm.catalog_dir,
        valid_transposition_region=vtr,
    )

    storm_catalog.save()
    logging.info("Catalog has been created.")
    return storm_catalog


def new_collection(
    catalog: Union[str | StormCatalog],
    start_date: str = "1979-02-01",
    end_date: str = None,
    storm_duration: int = 72,
    min_precip_threshold: int = 1,
    top_n_events: int = 5,
    check_every_n_hours: int = 6,
    specific_dates: list = None,
    num_workers: int = None,
    with_tb: bool = False,
    create_new_items: bool = True,
):
    """
    Create a new storm collection.

    Args:
        catalog (Union[str | StormCatalog]): The storm catalog or path to the catalog file.
        start_date (str): The start date for the collection.
        end_date (str, optional): The end date for the collection.
        storm_duration (int): The duration of the storm.
        min_precip_threshold (int): The minimum precipitation threshold.
        top_n_events (int): The number of top events to include.
        check_every_n_hours (int): The interval in hours to check for storms.
        specific_dates (list, optional): Specific dates to include.
        num_workers (int, optional): Number of cpu's to use during processing.
        with_tb (bool): Whether to include traceback in error logs.
        create_new_items (bool): Create items (or skip if items exist)
    """
    initialize_logger()

    if isinstance(catalog, str):
        storm_catalog = StormCatalog.from_file(catalog)
    elif isinstance(catalog, StormCatalog):
        storm_catalog = catalog
    else:
        raise ValueError(f"Catalog must be a path to a catalog file or a StormCatalog object not {type(catalog)}")

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%dT%H")

    # logging.info(f"specific_dates: {specific_dates}")
    if not specific_dates:
        logging.info("Generating date range from %s to %s", start_date, end_date)
        dates = generate_date_range(start_date, end_date, every_n_hours=check_every_n_hours)
    elif len(specific_dates) > 0:
        logging.debug("Using specific dates: %s", specific_dates)
        dates = specific_dates
    elif len(specific_dates) == 0:
        logging.info("No specific dates provided.")
        dates = None
    else:
        logging.error("Unrecognized specific_dates argument or related  error.")
        dates = None

    collection_id = storm_catalog.spm.storm_collection_id(storm_duration)
    logging.info("Creating collection `%s` for period %s - %s", collection_id, start_date, end_date)

    if dates:
        logging.info("Collecting event stats for %d dates", len(dates))
        collect_event_stats(
            dates, storm_catalog, collection_id, storm_duration, num_workers=num_workers, with_tb=with_tb
        )
    stats_csv = os.path.join(storm_catalog.spm.collection_dir(collection_id), "storm-stats.csv")
    try:
        logging.info("Starting storm analysis for: %s", stats_csv)
        analyzer = StormAnalyzer(stats_csv, min_precip_threshold, storm_duration)
    except ValueError as e:
        logging.error("No events at threshold `min_precip_threshold` %d: %s", min_precip_threshold, e)
        return

    ranked_data = analyzer.rank_and_save(collection_id, storm_catalog.spm)

    top_events = ranked_data[ranked_data["por_rank"] <= top_n_events].copy()

    if create_new_items:
        event_items = create_items(
            top_events.to_dict(orient="records"), storm_catalog, storm_duration=storm_duration, with_tb=with_tb
        )
        collection = storm_catalog.new_collection_from_items(collection_id, event_items)

    else:
        collection = storm_catalog.add_rank_to_collection(collection_id, top_events)

    collection.add_summary_stats(storm_catalog.spm)
    collection.event_feature_collection(storm_catalog.spm, min_precip_threshold)

    storm_catalog.add_collection_to_catalog(collection, override=True)
    storm_catalog.save_catalog()
    return collection


def resume_collection(
    catalog: str,
    start_date: str = "1979-02-01",
    end_date: str = None,
    storm_duration: int = 24,
    min_precip_threshold: int = 1,
    top_n_events: int = 5,
    check_every_n_hours: int = 6,
    num_workers: int = None,
    with_tb: bool = False,
    create_items: bool = True,
):
    """
    Resume a storm collection.

    Args:
        catalog (str): Path to the catalog file.
        start_date (str): The start date for the collection.
        end_date (str, optional): The end date for the collection.
        storm_duration (int): The duration of the storm.
        min_precip_threshold (int): The minimum precipitation threshold.
        top_n_events (int): The number of top events to include.
        check_every_n_hours (int): The interval in hours to check for storms.
        num_workers (int, optional): Number of cpu's to use during processing.
        with_tb (bool): Whether to include traceback in error logs.
    """
    initialize_logger()
    storm_catalog = StormCatalog.from_file(catalog)

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    collection_id = storm_catalog.spm.storm_collection_id(storm_duration)
    partial_stats_csv = os.path.join(storm_catalog.spm.collection_dir(collection_id), "storm-stats.csv")
    logging.info("Searching for missing storm dates in %s", partial_stats_csv)
    dates = find_missing_storm_dates(partial_stats_csv, start_date, end_date, every_n_hours=check_every_n_hours)
    logging.info("%d dates found missing from %s - %s.", len(dates), start_date, end_date)

    new_collection(
        catalog=storm_catalog,
        start_date=start_date,
        end_date=end_date,
        storm_duration=storm_duration,
        min_precip_threshold=min_precip_threshold,
        top_n_events=top_n_events,
        check_every_n_hours=check_every_n_hours,
        specific_dates=dates,
        num_workers=num_workers,
        with_tb=with_tb,
        create_new_items=create_items,
    )
