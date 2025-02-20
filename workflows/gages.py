import numpy as np
import pandas as pd
import scipy.stats as stats
from dataretrieval import nwis

from stormhub.hydro.usgs.usgs import UsgsGage
from stormhub.logger import initialize_logger

initialize_logger()

gage_number = "12105900"

gage = UsgsGage.from_usgs(gage_number, href=f"/Users/slawler/Downloads/{gage_number}.json")
gage.get_flow_stats(f"/Users/slawler/Downloads/{gage_number}")
gage.get_peaks(f"/Users/slawler/Downloads/{gage_number}")

gage.save_object()

site_info = nwis.get_record(sites=gage_number, service="site")


# flow_stats = nwis.get_stats(sites=gage_number)[0]
# peaks_df = nwis.get_discharge_peaks(sites=gage_number)[0]


# def log_pearson_iii(peak_flows: pd.Series, standard_return_periods: list = [2, 5, 10, 25, 50, 100, 500]):
#     log_flows = np.log10(peak_flows.values)
#     mean_log = np.mean(log_flows)
#     std_log = np.std(log_flows, ddof=1)
#     skew_log = stats.skew(log_flows)

#     return {
#         str(rp): int(10 ** (mean_log + stats.pearson3.ppf(1 - 1 / rp, skew_log) * std_log))
#         for rp in standard_return_periods
#     }


# peak_flows = peaks_df["peak_va"]


# def stac_table(data: dict, col1: str, col2: str):
#     table = []
#     for k, v in data.items():
#         table.append({col1: k, col2: v})
#     return table


# peaks = log_pearson_iii(peak_flows)
# plot_log_pearson_iii(peak_flows)

# gage.properties["file:values"] = stac_table(peaks, "return_period", "discharge_CFS_(Approximate)")

# gage.save_object()


# # ams_plot_sorted(peaks, gage_number)
# # ams_plot(peaks, gage_number)
# # plot_nwis_statistics(stats, gage_number)
# # hist_plot(peaks)

# # probability_plot(peaks)


# # peaks = log_pearson_iii(peaks["peak_va"])

# # # site_stats[0].to_csv(f"/Users/slawler/Downloads/{gage_number}.usgsgage.stats.csv")
# # # Example usage

# # fig = plot_log_pearson_iii_return_period(peaks["Peak Flow (cfs)"])
