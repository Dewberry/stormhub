import logging

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats


def plot_ams_seasonal(df, site: str, save_to: str):
    # Map months to seasons
    df["season"] = ((df.index.month % 12 + 3) // 3).map({1: "Winter", 2: "Spring", 3: "Summer", 4: "Fall"})

    # Rank flows in ascending order
    df = df.sort_values("peak_va").reset_index()
    df["rank"] = range(1, len(df) + 1)

    # Define custom colors for seasons
    season_colors = {
        "Winter": "blue",
        "Spring": "green",
        "Summer": "orange",
        "Fall": "brown",
    }

    # Create scatter plot
    fig, ax = plt.subplots()
    for season, color in season_colors.items():
        subset = df[df["season"] == season]
        ax.scatter(subset["rank"], subset["peak_va"], color=color, label=season, edgecolor="black", linewidth=0.5, s=50)

    ax.set_xlabel("Rank (Low to High Flow)")
    ax.set_ylabel("Flow (cfs)")
    ax.set_title(f"Gage ID: {site} | Flow Ranked from Low to High")
    ax.legend(title="Season")
    ax.grid(True, linestyle="--", alpha=0.6)

    fig.savefig(save_to, bbox_inches="tight")
    plt.close()


def plot_ams(df: pd.DataFrame, site: str, save_to: str):
    fig, ax = plt.subplots()
    ax.scatter(df.index, df["peak_va"], color="blue", edgecolor="black", linewidth=0.5, s=25)

    ax.set_xlabel("Annual Maxima Series")
    ax.set_ylabel("Flow (cfs)")
    ax.set_title(f"Gage ID: {site} | Peak FLows")
    ax.grid(True, linestyle="--", alpha=0.6)
    fig.savefig(save_to, bbox_inches="tight")
    plt.close()


def plot_nwis_statistics(stats_df: pd.DataFrame, site: str, save_to: str):
    """
    Plots streamflow statistics from NWIS.

    Parameters:
        stats_df (pd.DataFrame): DataFrame containing NWIS statistical data.
        site (str): USGS site number.

    Returns:
        matplotlib.figure.Figure: The generated plot.
    """
    # Ensure data is sorted by day of the year
    stats_df = stats_df.sort_values(by=["month_nu", "day_nu"])

    # Create x-axis as day of year
    stats_df["day_of_year"] = stats_df["month_nu"] * 30 + stats_df["day_nu"]  # Approximate day of year

    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot percentiles
    ax.fill_between(
        stats_df["day_of_year"],
        stats_df["p05_va"],
        stats_df["p95_va"],
        color="lightblue",
        alpha=0.4,
        label="5th-95th Percentile",
    )
    ax.fill_between(
        stats_df["day_of_year"],
        stats_df["p10_va"],
        stats_df["p90_va"],
        color="blue",
        alpha=0.4,
        label="10th-90th Percentile",
    )
    ax.fill_between(
        stats_df["day_of_year"],
        stats_df["p25_va"],
        stats_df["p75_va"],
        color="darkblue",
        alpha=0.4,
        label="25th-75th Percentile",
    )

    # Plot mean values
    ax.plot(
        stats_df["day_of_year"],
        stats_df["mean_va"],
        marker="o",
        markersize=2,
        linestyle="-",
        color="black",
        label="Mean Flow",
    )

    # Labels and title
    ax.set_xlabel("Day of Year")
    ax.set_ylabel("Flow (cfs)")
    ax.set_title(f"Flow Statistics for USGS Site {site}")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)

    fig.savefig(save_to, bbox_inches="tight")
    plt.close()


def plot_log_pearson_iii(
    peak_flows: pd.Series,
    gage_id: str,
    save_to: str,
):
    """
    Plots the return period (recurrence interval) vs. peak flow using Log-Pearson Type III analysis.

    Parameters:
        peak_flows (array-like): List or array of peak flow values.

    Returns:
        matplotlib.figure.Figure: The generated plot.
    """
    log_flows = np.log10(peak_flows.values)
    mean_log = np.mean(log_flows)
    std_log = np.std(log_flows, ddof=1)
    skew_log = stats.skew(log_flows)
    lp3_estimates = []
    standard_return_periods = [2, 5, 10, 25, 50, 100, 500]
    for rp in standard_return_periods:
        lp3_estimates.append(10 ** (mean_log + stats.pearson3.ppf(1 - 1 / rp, skew_log) * std_log))

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(
        standard_return_periods,
        lp3_estimates,
        marker="o",
        linestyle="-",
        color="blue",
        label="Log-Pearson III Fit",
        zorder=2,
    )

    # Set predefined tick marks
    ax.set_xscale("log")  # Log scale for return period
    ax.set_xticks(standard_return_periods)  # Set ticks at predefined return periods
    ax.set_xticklabels([str(rp) for rp in standard_return_periods])  # Force display of exact labels

    # Labels and title
    ax.set_xlabel("Return Period (years)")
    ax.set_ylabel("Peak Flow (cfs)")
    ax.set_title(f"{gage_id } | Log-Pearson Type III Estimates \n(No regional skew))")
    ax.grid(True, which="both", linestyle="--", alpha=0.6)
    ax.legend()

    fig.savefig(save_to, bbox_inches="tight")
    plt.close()
