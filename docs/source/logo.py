import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from matplotlib.pyplot import get_cmap
from shapely.geometry import Point, Polygon

watershed_path = "https://raw.githubusercontent.com/Dewberry/stormhub/refs/heads/main/catalogs/example-input-data/indian-creek.geojson"
transposition_path = "https://raw.githubusercontent.com/Dewberry/stormhub/refs/heads/main/catalogs/example-input-data/indian-creek-transpo-area-v01.geojson"

watershed = gpd.read_file(watershed_path).buffer(0.03)
transposition_domain = gpd.read_file(transposition_path)

if watershed.crs != transposition_domain.crs:
    transposition_domain = transposition_domain.to_crs(watershed.crs)

np.random.seed(112)
num_storms = 15
storm_catalog_locations = []
bounds = transposition_domain.total_bounds
storm_radius = 0.5

while len(storm_catalog_locations) < num_storms:
    random_point = Point(
        np.random.uniform(bounds[0], bounds[2]),  # x-coordinate
        np.random.uniform(bounds[1], bounds[3]),  # y-coordinate
    )

    angles = np.linspace(0, 2 * np.pi, 100)
    storm_circle = Polygon(
        [
            (
                random_point.x + storm_radius * np.cos(angle),
                random_point.y + storm_radius * np.sin(angle),
            )
            for angle in angles
        ]
    )

    if transposition_domain.contains(storm_circle).any():
        storm_catalog_locations.append(random_point)

moved_storms = [
    Point(storm.x + np.random.uniform(-1, 1), storm.y + np.random.uniform(-1, 1)) for storm in storm_catalog_locations
]

cmap = get_cmap("tab10")
storm_colors = [cmap(i % cmap.N) for i in range(num_storms)]

with plt.xkcd():
    fig, ax = plt.subplots(figsize=(10, 10))
    transposition_domain.plot(ax=ax, color="none", edgecolor="blueviolet", linestyle="--", linewidth=2)
    for original, moved, color in zip(storm_catalog_locations, moved_storms, storm_colors):
        ax.scatter(original.x, original.y, color=color, alpha=0.5, s=80)

        ax.plot([original.x, moved.x], [original.y, moved.y], color=color, linestyle="-", alpha=0.5, linewidth=1)
        storm_x = moved.x + storm_radius * np.cos(angles)
        storm_y = moved.y + storm_radius * np.sin(angles)
        ax.fill(storm_x, storm_y, color=color, alpha=0.1, edgecolor="black", linewidth=1.5)

    legend_handles = [
        Patch(facecolor="lightblue", edgecolor="black", label="Watershed"),
        Patch(facecolor="none", edgecolor="blueviolet", linestyle="--", label="Transposition Domain"),
        Patch(
            facecolor="gray", edgecolor="black", alpha=0.5, label="Storms (Observed Centroid and Transposed Footprint)"
        ),
    ]

    ax.legend(handles=legend_handles, fontsize=10, loc="upper left")
    ax.set_title("Random Storm Selection and Transposition", fontsize=14, weight="bold")

    x_padding = (bounds[2] - bounds[0]) * 0.1  # 10% of the x range
    y_padding = (bounds[3] - bounds[1]) * 0.1  # 10% of the y range

    ax.set_xlim(bounds[0] - x_padding, bounds[2] + x_padding)
    ax.set_ylim(bounds[1] - y_padding, bounds[3] + y_padding)

    watershed.plot(ax=ax, color="lightblue", edgecolor="black", alpha=0.8, label="Watershed", linewidth=2)

    plt.show()
