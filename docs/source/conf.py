"""
Configuration file for the Sphinx documentation builder.

For the full list of built-in configuration values, see the documentation:
https://www.sphinx-doc.org/en/master/usage/configuration.html
"""

import os

# import pathlib
# import subprocess
import sys

sys.path.insert(0, os.path.abspath("../.."))

import stormhub

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "stormhub"
copyright = "2024, Dewberry"
author = "Seth Lawler"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx_autodoc_typehints",
    "sphinx_rtd_theme",
    "sphinx.ext.doctest",
    "myst_parser",
    "sphinx.ext.napoleon",
    "sphinx_design",
]

# numpydoc_show_class_members = False
autosummary_generate = True

templates_path = ["_templates"]
exclude_patterns = ["production"]

master_doc = "index"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_css_files = ["custom.css"]

html_static_path = ["_static"]

html_theme = "pydata_sphinx_theme"

html_theme_options = {
    "navbar_start": ["navbar-logo", "navbar-version"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["navbar-icon-links"],
    "navbar_persistent": ["search-button"],
}

html_sidebars = {
    "tech_summary": [],
    "user_guide": [],
    "change_log": [],
}


# Substitutions
release = str(stormhub.__version__)
version = release


# def fetch_github_releases():
#     subprocess.run(
#         [sys.executable, str(pathlib.Path(__file__).parent.parent.resolve() / "build_release_changelog.py")], check=True
#     )


# def setup(app):
#     fetch_github_releases()
