import re
from io import TextIOWrapper
from pathlib import Path

import requests

CHANGE_LOG_PATH = str(Path(__file__).parent.resolve() / "source" / "change_log.rst")


def get_content() -> dict:
    """Get the content of the changelog from the GitHub API."""
    url = "https://api.github.com/repos/Dewberry/stormhub/releases"
    headers = {"Accept": "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def add_heading(file: TextIOWrapper):
    """Add the heading for the changelog."""
    file.write(".. note::\n")
    file.write(
        "   Go to the `Releases <https://github.com/Dewberry/stormhub/releases.html>`__  page for a list of all releases.\n\n"
    )


def add_release_body(file: TextIOWrapper, body: str):
    """Add the body of a release to the changelog."""
    lines = body.split("\n")
    for l in lines:
        if l.startswith("# "):
            file.write(f"{l[2:]}")
            file.write(f"{'-' * len(l[2:])}\n")
        elif l.startswith("## "):
            file.write(f"{l[3:]}")
            file.write(f"{'^' * len(l[3:])}\n")
        elif l.startswith("### "):
            file.write(f"{l[4:]}")
            underline = '"' * len(l[4:])
            file.write(f"{underline}\n")
        else:
            l = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"`\1 <\2>`_", l)  # fix links
            file.write(f"{l}\n")


def add_release(file: TextIOWrapper, release: dict):
    """Add a release to the changelog."""
    file.write(f"{release['name']}\n")
    file.write(f"{'=' * len(release['name'])}\n\n")
    file.write(f"**Tag:** {release['tag_name']}\n\n")
    file.write(f"**Published at:** {release['published_at']}\n\n")
    file.write(f"**Author:** {release['author']['login']}\n\n")
    file.write(f"**Release Notes:**\n\n")
    add_release_body(file, release["body"])
    file.write("\n\n")


def build_changelog():
    """Build the changelog for the documentation."""
    releases = get_content()

    # Write release information to an .rst file
    with open(CHANGE_LOG_PATH, "w") as file:
        add_heading(file)
        for release in releases:
            add_release(file, release)


if __name__ == "__main__":
    build_changelog()
