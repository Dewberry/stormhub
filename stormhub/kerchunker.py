"""Write and read kerchunk references as .json.zst or .parquet, as individual NetCDF file sidecars or for aggregated datasets. Attach to STAC items.

Requires Python 3.11+ for Kerchunk support.

Writing: see ``KerchunkConfig``, ``Kerchunker``, ``create_kerchunker_for_stormhub_nc_forcing``, and ``register_storm_netcdf``.
Reading: see ``kerchunk_reader`` and ``kerchunk_reader_options``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable

import fsspec
import pystac
import xarray as xr
import zstandard
from pystac import Asset
from stormhub.met.consts import (
    NETCDF_TIME_DIMENSION_PREFIX,
    STORM_NC_KERCHUNK_COLLECTION_ASSET_DESCRIPTION,
    STORM_NC_KERCHUNK_COLLECTION_ASSET_KEY,
    STORM_NC_KERCHUNK_INDIVIDUAL_ASSET_DESCRIPTION,
)

KERCHUNK_JSON_ZSTD_LEVEL = 8
KERCHUNK_SUPPORTED = sys.version_info >= (3, 11)

if KERCHUNK_SUPPORTED:
    from kerchunk.combine import concatenate_arrays
    from kerchunk.df import refs_to_dataframe
    from kerchunk.hdf import SingleHdf5ToZarr
else:
    logging.info(f"Python version {sys.version_info} detected. Kerchunk not supported (requires Python version 3.11+)")


def _require_kerchunk_support() -> None:
    if not KERCHUNK_SUPPORTED:
        raise NotImplementedError("Kerchunk not supported (requires Python version 3.11+)")


class KerchunkFormat(str, Enum):
    """Supported serialization formats for Kerchunk references."""

    JSON = "json.zst"
    PARQUET = "parquet"


def create_kerchunker_for_stormhub_nc_forcing(config: KerchunkConfig) -> Kerchunker:
    """Create a Kerchunker instance for the stormhub NetCDF forcing data use case.

    The returned Kerchunker is configured partly on the provided config instance of
    KerchunkConfig, with some Kerchunker parameters set to static constants for this use case.
    """
    return Kerchunker(
        replace(
            config,
            collection_axes=(config.collection_axes or storm_netcdf_collection_axes)
            if config.make_collection_ref is not None
            else None,
            collection_asset_key=STORM_NC_KERCHUNK_COLLECTION_ASSET_KEY,
            individual_asset_description=STORM_NC_KERCHUNK_INDIVIDUAL_ASSET_DESCRIPTION,
            collection_asset_description=STORM_NC_KERCHUNK_COLLECTION_ASSET_DESCRIPTION,
        )
    )


def register_storm_netcdf(
    item: pystac.Item,
    written_path: str | Path | None,
    dss_path: str | Path,
    kerchunker: Kerchunker,
) -> FileNotFoundError | None:
    """Add a stormhub NetCDF forcing file as an asset to an existing storm STAC item, and kerchunk it (if configured as such)."""
    if written_path is not None:
        netcdf_path = Path(written_path).resolve()
        if not netcdf_path.is_file():
            return FileNotFoundError(netcdf_path)
        dss_asset = item.assets.get(Path(dss_path).name)
        if dss_asset is not None:
            netcdf_href = f"{dss_asset.href.rsplit('.', 1)[0]}.nc"
        else:
            netcdf_href = str(Path(dss_path).with_suffix(".nc"))
        from stormhub.utils import add_storm_netcdf_asset

        add_storm_netcdf_asset(item, netcdf_path, netcdf_href)
        kerchunker.add(item, netcdf_path, netcdf_href, item.properties["start_datetime"])
    return None


def kerchunk_reader(storage_options: dict, **open_zarr_kwargs) -> xr.Dataset:
    """Open a .json.zst or .parquet Kerchunk reference as a lazy xarray Dataset.

    Example::

        options = kerchunk_reader_options("s3://foo/bar/events/72hr-events.kerchunk.parquet")
        ds = kerchunk_reader(options)

    ``storage_options`` are for fsspec, passed to ``xr.open_zarr``. They can be generated
    manually or by using ``kerchunk_reader_options()``.

    ``open_zarr_kwargs`` are passed to ``xr.open_zarr``.
    """
    _require_kerchunk_support()
    open_zarr_kwargs.setdefault("consolidated", False)
    return xr.open_zarr("reference://", storage_options=storage_options, **open_zarr_kwargs)


def kerchunk_reader_options(
    reference_href: str | Path,
    base_href: str | Path | None = None,
    storage_options: dict | None = None,
    target_storage_options: dict | None = None,
) -> dict:
    """Build stock fsspec ``storage_options`` for opening a .json.zst or .parquet Kerchunk reference with xarray.

    Example::

        options = kerchunk_reader_options("s3://foo/bar/events/72hr-events.kerchunk.parquet")
        ds = xr.open_zarr("reference://", storage_options=options, consolidated=False)

    The returned dictionary contains only built-in fsspec options, so readers may also build it manually.
    Stored source paths are relative, and resolve against ``base_href`` through a ``dir`` filesystem.

    Parameters
    ----------
        reference_href: Local path or URL of the reference file (.json.zst) or directory (.parquet).
        base_href: Directory that relative source paths resolve against.
            Defaults to the reference's parent directory, so uploading files with the same layout requires no override.
        storage_options: fsspec options for reading the reference itself.
        target_storage_options: fsspec options for reading the NetCDF files, such as credentials or ``anon``.
    """
    _require_kerchunk_support()
    reference_href = str(reference_href).rstrip("/")
    if not reference_href.endswith((".json.zst", ".parquet")):
        raise ValueError(f"Expected a .json.zst file or .parquet directory, got: {reference_href}")
    if base_href is None:
        base_href = reference_href.rsplit("/", 1)[0] if "/" in reference_href else "."
    base_href = str(base_href)
    target_storage_options = dict(target_storage_options or {})

    protocol = fsspec.core.split_protocol(base_href)[0] or "file"
    target_class = fsspec.get_filesystem_class(protocol)
    # Zarr reopens the reference filesystem in async mode, so the source filesystem must be async too.
    if target_class.async_impl:
        target = {"target_protocol": protocol, "target_options": {**target_storage_options, "asynchronous": True}}
    else:
        target = {
            "target_protocol": "async_wrapper",
            "target_options": {
                "target_protocol": protocol,
                "target_options": target_storage_options,
                "asynchronous": True,
            },
        }

    reference_options = dict(storage_options or {})
    if reference_href.endswith(".json.zst"):
        reference_options["compression"] = "zstd"
    return {
        "fo": reference_href,
        "target_options": reference_options,
        "remote_protocol": "dir",
        "remote_options": {"path": target_class._strip_protocol(base_href), "asynchronous": True, **target},
        "skip_instance_cache": True,
    }


def _translate_nc(source_path: Path, source_url: str) -> dict:
    """Translate a NetCDF file into a kerchunk reference dictionary.

    ``translate()`` builds array metadata and byte-range references in memory.
    It does not write a reference file.
    """
    with closing(SingleHdf5ToZarr(str(source_path), url=source_url, error="raise")) as translator:
        return translator.translate()


@dataclass(frozen=True)
class KerchunkConfig:
    """Configure kerchunk writing behavior. Also affects associated STAC assets for kerchunk references.

    Attributes
    ----------
        make_individual_refs: Provide None to disable individual (per-NetCDF) kerchunk reference creation. Otherwise specify ``"json.zst"`` or ``"parquet"``.
            Recommended: ``"json.zst"``.
            Default: None.
        make_collection_ref: Provide None to disable collection-level kerchunk reference creation. Otherwise specify ``"json.zst"`` or ``"parquet"``.
            Recommended: ``"parquet"`` for large collections, which writes a cloud-optimized directory.
            Default: None.
        collection_axes: Callback receiving the first source path and returning a dictionary from each time-dependent array path to its concatenation axis. Supply this when enabling collection-level references.
            Example, with time on axis 0: axes = {"PRECIPITATION": 0, "TEMPERATURE": 0}
            Default: None.
        collection_asset_key: Key under which the final reference is added to the STAC collection.
            Example: asset_key = "storm_kerchunk_refs".
            Default: ``"kerchunk"``.
        individual_asset_description: Description used for each per-item reference asset.
            Example: description = "Kerchunk reference for this storm.".
            Default: ``"Kerchunk references for this item."``.
        collection_asset_description: Description used for the final collection reference asset.
            Example: description = "Kerchunk reference for the storm collection.".
            Default: ``"Kerchunk references for this collection."``.
        translator: Callback that translates one source into a kerchunk reference dictionary.
            Example: translator = custom_translate, where custom_translate(path, url) returns a reference dictionary.
            Default: ``_translate_nc``.
        collection_output_dir: Directory where the collection reference is written. All sources must be inside it.
            Example: collection_output_dir = Path("basin-data/storm-catalog").
            Default: None, which uses the STAC collection JSON's directory.
    """

    make_individual_refs: KerchunkFormat | str | None = None
    make_collection_ref: KerchunkFormat | str | None = None
    collection_axes: Callable[[Path], dict[str, int]] | None = None
    collection_asset_key: str = "kerchunk"
    individual_asset_description: str = "Kerchunk references for this item."
    collection_asset_description: str = "Kerchunk references for this collection."
    individual_asset_roles: tuple[str, ...] = ("data", "kerchunk-ref", "kerchunk-ref-individual")
    collection_asset_roles: tuple[str, ...] = ("data", "kerchunk-ref", "kerchunk-ref-collection")
    translator: Callable[[Path, str], dict] = _translate_nc
    collection_output_dir: str | Path | None = None

    def __post_init__(self) -> None:
        """Validate that the selected reference formats are supported."""
        if not KERCHUNK_SUPPORTED and (self.make_individual_refs is not None or self.make_collection_ref is not None):
            _require_kerchunk_support()
        for field_name, scope in (("make_individual_refs", "Individual"), ("make_collection_ref", "Collection")):
            output_format = getattr(self, field_name)
            if output_format is None:
                continue
            try:
                output_format = KerchunkFormat(output_format)
            except ValueError as error:
                raise ValueError(
                    f"{scope}-level Kerchunk references must be 'json.zst' or 'parquet', got: {output_format!r}"
                ) from error
            object.__setattr__(self, field_name, output_format)


class Kerchunker:
    """Create Kerchunk references incrementally and attach them as assets to STAC objects.

    Supports making per-NetCDF file references, as well as collection-level references.
    Call ``add`` incrementally to make references to individual data files (per-file references), and then call ``finish`` to create the collection-level reference.
    ``add`` and ``finish`` also attach the references to the appropriate STAC objects as assets.

    Configuration: in every case, the reference is not actually written to disk unless the ``config: KerchunkConfig`` indicates that it should be.
    Meaning, if that config attribute indicates that the per-file references should not be created, you should still call ``add``
    so that you may later call ``finish`` to create the collection-level reference.

    ``finish`` is one-shot, it may not be called more than once, and ``add`` may not be called after it.
    """

    MEDIA_TYPES = {
        KerchunkFormat.JSON: "application/zstd",
        KerchunkFormat.PARQUET: "application/vnd.apache.parquet",
    }

    def __init__(self, config: KerchunkConfig = KerchunkConfig()):
        """Initialize a reference builder.

        Parameters
        ----------
            config: Output formats, collection-axis callback, and STAC asset metadata to use.
        """
        if config.make_collection_ref is not None and config.collection_axes is None:
            raise ValueError("Collection Kerchunk references require a collection_axes callback.")
        if config.make_individual_refs is not None or config.make_collection_ref is not None:
            _require_kerchunk_support()
        self.config = config
        self._collection_references: list[tuple[str, Path, str, dict]] = []
        self._collection_axes: dict[str, int] | None = None
        self._finished = False

    @staticmethod
    def reference_path(source_path: str | Path, output_format: KerchunkFormat) -> Path:
        """Build the sidecar reference path for a source file.

        Parameters
        ----------
            source_path: Local path to the source file.
            output_format: Reference serialization format used in the sidecar name.

        Returns
        -------
            The path beside the source file where the reference should be written.
        """
        source_path = Path(source_path)
        return source_path.with_name(f"{source_path.stem}.kerchunk.{output_format.value}")

    def add(
        self,
        item: pystac.Item,
        source_path: str | Path,
        source_href: str,
        order: str,
    ) -> Path | None:
        """Register a source and create its configured individual reference.

        Parameters
        ----------
            item: existing STAC item in which to add this reference asset.
            source_path: Local path used to read and translate the source data.
            source_href: STAC href.
            order: Sort key used to order this source in the final collection reference.

        Returns
        -------
            The individual reference path when individual output is enabled, otherwise None.

        If both output formats are disabled, this returns before validating or opening the source.

        Local filesystem paths are used for translation. Recognized source URLs are then
        rewritten relative to the reference so the files can be moved or uploaded together.

        This writes the sidecar locally and updates the item in memory. It does not
        upload the files or save the STAC item's updated JSON to disk.
        """
        if self._finished:
            raise RuntimeError("Cannot add a source after Kerchunker.finish() has been called.")
        if self.config.make_individual_refs is None and self.config.make_collection_ref is None:
            return None
        source_path = Path(source_path).resolve(strict=True)
        # Kerchunk stores the local path it opened, which is then rewritten relative to the reference.
        source_url = str(source_path)
        references = self.config.translator(source_path, source_url)

        reference_path = None
        if self.config.make_individual_refs is not None:
            reference_path = self.reference_path(source_path, self.config.make_individual_refs)
            individual_references = (
                copy.deepcopy(references) if self.config.make_collection_ref is not None else references
            )
            self._make_source_urls_relative(individual_references, {source_url: source_path.name})
            self._write(individual_references, reference_path, self.config.make_individual_refs)
            reference_href = self._sidecar_href(source_href, reference_path.name)
            item_href = item.get_self_href()
            if item_href and pystac.utils.is_absolute_href(reference_href):
                reference_href = pystac.utils.make_relative_href(reference_href, item_href)

            item.add_asset(
                reference_path.name,
                Asset(
                    reference_href,
                    reference_path.name,
                    description=self.config.individual_asset_description,
                    media_type=self.MEDIA_TYPES[self.config.make_individual_refs],
                    roles=list(self.config.individual_asset_roles),
                ),
            )

        if self.config.make_collection_ref is not None:
            if self._collection_axes is None:
                self._collection_axes = dict(self.config.collection_axes(source_path))
            # Retain translations so finish() can combine them without reopening source files.
            self._collection_references.append((order, source_path, source_url, references))
        return reference_path

    def finish(self, collection: pystac.Collection) -> Path | None:
        """Write the collection reference and attach it to the STAC collection.

        Parameters
        ----------
            collection: STAC collection receiving the final reference asset. Its local self href
                determines the output directory unless ``config.collection_output_dir`` is set.

        Returns
        -------
            The collection reference path when collection output is enabled, otherwise None.

        This method is one-shot even if collection output is disabled or finalization fails.

        The finished flag is set before validation or writing.
        A failed call cannot be retried with the same instance and no more sources can be added afterward.
        """
        if self._finished:
            raise RuntimeError("Kerchunker.finish() can only be called once.")
        self._finished = True

        if self.config.make_collection_ref is None:
            return None

        if not self._collection_references or self._collection_axes is None:
            raise ValueError("At least one source must be added before finishing collection Kerchunk output.")

        collection_href = collection.get_self_href()
        if not collection_href or collection_href.startswith(("s3://", "http://", "https://")):
            raise ValueError("Collection Kerchunk output requires a local STAC collection href.")
        output_name = f"{collection.id}.kerchunk.{self.config.make_collection_ref.value}"
        output_dir = self.config.collection_output_dir or Path(collection_href).parent
        output_path = Path(output_dir).resolve() / output_name

        sources = sorted(self._collection_references, key=lambda entry: entry[0])
        relative_sources = {
            source_url: Path(os.path.relpath(source_path, output_path.parent)).as_posix()
            for _, source_path, source_url, _ in sources
        }
        outside = [path for path in relative_sources.values() if path.startswith("../")]
        if outside:
            raise ValueError(
                f"Collection Kerchunk sources must be inside the output directory {output_path.parent}, but got: {outside[0]}"
            )

        references = [reference for _, _, _, reference in sources]
        combined = copy.deepcopy(references[0])
        # Arrays may use different concat axes, so combine each array independently.
        for variable_name, axis in self._collection_axes.items():
            metadata_key = f"{variable_name}/.zarray"
            if any(metadata_key not in reference["refs"] for reference in references):
                raise ValueError(
                    f"Collection Kerchunk mismatch: '{variable_name}' is missing from at least one source reference."
                )
            concatenated = concatenate_arrays(references, axis=axis, path=variable_name, check_arrays=True)
            combined["refs"].update(concatenated["refs"])

        self._make_source_urls_relative(combined, relative_sources)
        self._write(combined, output_path, self.config.make_collection_ref)
        collection.add_asset(
            self.config.collection_asset_key,
            Asset(
                pystac.utils.make_relative_href(str(output_path), str(Path(collection_href).resolve())),
                output_name,
                description=self.config.collection_asset_description,
                media_type=self.MEDIA_TYPES[self.config.make_collection_ref],
                roles=list(self.config.collection_asset_roles),
            ),
        )
        collection.save_object()
        logging.info("Added collection Kerchunk asset: %s", output_path)
        return output_path

    @staticmethod
    def _make_source_urls_relative(references: dict, relative_sources: dict[str, str]) -> None:
        """Rewrite recognized external URLs as paths relative to the reference's directory.

        Parameters
        ----------
            references: Kerchunk reference dictionary to update in place.
            relative_sources: Dictionary from translated source URLs to their relative paths.

        Inline values, metadata strings, and external URLs absent from ``relative_sources`` are preserved.
        Only external reference entries whose URL matches a dictionary key are rewritten.

        Example input and output::

            relative_sources = {"/data/storm.nc": "1/storm.nc"}
            reference = ["/data/storm.nc", 1000, 200]
            result = ["1/storm.nc", 1000, 200]

        Readers resolve the relative path against the reference's directory. See ``kerchunk_reader_options``.
        """
        for value in references["refs"].values():
            if isinstance(value, list) and value and value[0] in relative_sources:
                value[0] = relative_sources[value[0]]

    @staticmethod
    def _write(references: dict, output_path: Path, output_format: KerchunkFormat) -> Path:
        """Stage and publish references as JSON or a Parquet directory.

        Parameters
        ----------
            references: Kerchunk reference dictionary to serialize.
            output_path: New destination path. Existing references are never overwritten.
            output_format: Serialization format to write.

        Returns
        -------
            The destination path.

        ``FileExistsError`` is raised if the output already exists.
        A temporary directory is used during serialization step, adjacent to the destination.
        """
        if output_path.exists():
            raise FileExistsError(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=output_path.parent, prefix=f".{output_path.name}.") as temp_dir:
            temporary_path = Path(temp_dir) / output_path.name
            if output_format is KerchunkFormat.JSON:
                compressor = zstandard.ZstdCompressor(level=KERCHUNK_JSON_ZSTD_LEVEL)
                with zstandard.open(temporary_path, mode="wt", cctx=compressor, encoding="utf-8") as output:
                    json.dump(references, output, separators=(",", ":"))
            elif output_format is KerchunkFormat.PARQUET:
                refs_to_dataframe(references, str(temporary_path))
            else:
                raise ValueError(f"Unsupported Kerchunk output format: {output_format!r}")
            temporary_path.replace(output_path)
        return output_path

    @staticmethod
    def _sidecar_href(source_href: str, sidecar_name: str) -> str:
        """Compose a string to make a sidecar href beside a source href.

        Parameters
        ----------
            source_href: STAC href of the source asset.
            sidecar_name: Filename of the kerchunk reference sidecar.

        Returns
        -------
            The sidecar href, preserving the source href's path separator style.

        This handles Posix, s3://, and Windows-style backslash hrefs without interpreting a
        remote or relative href as a local filesystem path. A bare filename stays a bare filename.

        Example::

            source_href = "s3://foo/bar/events/storm.nc"
            sidecar_name = "storm.kerchunk.json.zst"
            result = "s3://foo/bar/events/storm.kerchunk.json.zst"

        For a bare filename, source_href = "storm.nc" produces result = "storm.kerchunk.json.zst".
        """
        separator = "\\" if "\\" in source_href else "/"
        directory = source_href.rsplit(separator, 1)[0] if separator in source_href else ""
        return f"{directory}{separator}{sidecar_name}" if directory else sidecar_name


def storm_netcdf_collection_axes(netcdf_path: Path) -> dict[str, int]:
    """Return axes for the independent time arrays in a stormhub NetCDF.

    Stormhub's NetCDFs receive a time dimension for each independent time array.
    For example "time_precipitation" and "time_temperature".
    This is to allow for use cases such as this, where temperature has a 864-hour duration but precipitation has a 72-hour duration:
    https://github.com/Dewberry/stormhub/blob/c6a156bd85bc750eedadd8e6f381cac907a6959e/stormhub/met/dss_utils/create_dss.py#L44-L47

    Since the time axes are indepndent to support that use case, it is possible that different axes use
    different indexes for the time variable. This function inspects the time variables and returns the
    mapping to each variable's time axis index. In many cases, this will return:
        {
            "time_precipitation": 0,
            "time_temperature": 0,
        }
    """
    with xr.open_dataset(netcdf_path, engine="h5netcdf") as dataset:
        time_dimensions = {
            dimension for dimension in dataset.dims if dimension.startswith(NETCDF_TIME_DIMENSION_PREFIX)
        }
        collection_axes = {}
        for name, variable in dataset.variables.items():
            for axis, dimension in enumerate(variable.dims):
                if dimension in time_dimensions:
                    collection_axes[name] = axis
                    break
        return collection_axes
