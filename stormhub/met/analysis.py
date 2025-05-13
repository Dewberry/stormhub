"""Storm analysis utilities."""

import datetime
import logging
import os

import numpy as np
import pandas as pd

from stormhub.utils import StacPathManager


class StormAnalyzer:
    """Analyze storm events."""

    def __init__(self, csv_path: str, threshold: float, duration_hours: int):
        self.csv_path = csv_path
        self.threshold = threshold
        self.duration_hours = duration_hours
        self.metrics_df = self._load_and_filter_data()
        if self.metrics_df.shape[0] == 0:
            raise ValueError("No storm events meet the threshold. Please adjust the threshold and try again.")
        self.filter = self._initialize_filter()

    def _load_and_filter_data(self) -> pd.DataFrame:
        """Load and filter storm data to above mean threshold."""
        df = pd.read_csv(self.csv_path)
        df["storm_date"] = pd.to_datetime(df["storm_date"])
        return df[df["mean"] >= self.threshold]

    def _initialize_filter(self):
        """Initialize storm filter."""
        if self.metrics_df["storm_date"].isnull().all():
            raise ValueError(
                "All storm_date values are NaT. Please check the input data and ensure events meet threshold."
            )

        start = self.metrics_df["storm_date"].min()
        end = self.metrics_df["storm_date"].max()

        if pd.isna(start) or pd.isna(end):
            raise ValueError("Start or end date is NaT. Please check the input data and ensure events meet threshold.")

        return StormFilter(start, end, datetime.timedelta(hours=1))

    def rank_and_filter_storms(self, buffer_hours: int = 24) -> pd.DataFrame:
        """Rank and filter storms.

        buffer_hours represent the time between potential storm events.
        TODO: Investigate appropriate values for this and verify functionality.
        """
        storm_records = []
        overlapping_overall_rank = 1
        non_overlapping_rank = 1
        year_rank_dict = {}
        year_rank = 1

        sorted_metrics_df = self.metrics_df.sort_values(by="mean", ascending=False)

        for _, row in sorted_metrics_df.iterrows():
            start_dt = row["storm_date"]
            end_dt = start_dt + datetime.timedelta(hours=self.duration_hours + buffer_hours)
            year = start_dt.year

            overlapping_year_rank, non_overlapping_year_rank = year_rank_dict.get(year, (1, 1))

            record = {
                "storm_date": start_dt.strftime("%Y-%m-%dT%H"),
                "mean": row["mean"],
                "min": row["min"],
                "max": row["max"],
                "overlapping_overall_rank": overlapping_overall_rank,
                "year_rank": year_rank,
            }
            overlapping_overall_rank += 1
            year_rank += 1

            if self.filter.try_block_period(start_dt, end_dt):
                record["non_overlapping_rank"] = non_overlapping_rank
                record["non_overlapping_year_rank"] = non_overlapping_year_rank
                non_overlapping_rank += 1
                non_overlapping_year_rank += 1
            else:
                record["non_overlapping_rank"] = -1
                record["non_overlapping_year_rank"] = -1

            year_rank_dict[year] = (overlapping_year_rank, non_overlapping_year_rank)
            storm_records.append(record)

        df = pd.DataFrame(storm_records)
        df.drop(columns=["overlapping_overall_rank", "year_rank"], inplace=True)
        df = df[df["non_overlapping_rank"] > 0]
        df.rename(
            columns={"non_overlapping_year_rank": "annual_rank", "non_overlapping_rank": "por_rank"}, inplace=True
        )

        return df.sort_values(by="por_rank").reset_index(drop=True)

    def _rank_storm_ids(self) -> list[str]:
        """Rank storm ids."""
        sorted_indices = np.argsort(self.metrics_df["mean"].values)[::-1]
        return self.metrics_df["storm_date"].dt.strftime("%Y-%m-%dT%H").iloc[sorted_indices].tolist()

    def rank_and_save(self, collection_id: str, spm: StacPathManager) -> pd.DataFrame:
        """Rank storms and save to csv."""
        output_file = os.path.join(spm.collection_dir(collection_id), "ranked-storms.csv")
        ranked_df = self.rank_and_filter_storms()
        ranked_df.to_csv(output_file, index=False)
        ranked_df["storm_date"] = pd.to_datetime(ranked_df["storm_date"])
        logging.info("Saved ranked storm data to %s", output_file)
        return ranked_df


class StormFilter:
    """Filter storm events from a series of cumulative grid statistics."""

    def __init__(
        self,
        start: datetime.datetime,
        end: datetime.datetime,
        interval: datetime.timedelta,
    ) -> None:
        self.start = start
        self.end = end
        self.interval = interval
        self.datetime_array = self._generate_datetime_array()

    def available_dates(self) -> np.ndarray:
        """Get available dates."""
        return self.datetime_array.compressed()

    def _generate_datetime_array(self) -> np.ma.MaskedArray:
        """Generate datetime array."""
        dt_list = np.arange(self.start, self.end, self.interval).astype("datetime64")
        return np.ma.array(data=dt_list, dtype=np.datetime64)

    def block_period(self, start: np.datetime64, end: np.datetime64) -> None:
        """Block a period of time."""
        mask = (self.datetime_array >= start) & (self.datetime_array < end)
        self.datetime_array[mask] = np.ma.masked

    def try_block_period(self, start: datetime.datetime, end: datetime.datetime) -> bool:
        """Try to block a period of time."""
        start_np = np.datetime64(start)
        end_np = np.datetime64(end)
        if start_np in self.available_dates() and end_np in self.available_dates():
            self.block_period(start_np, end_np)
            return True
        return False
