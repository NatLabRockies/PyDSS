# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# from pathlib import Path
import os
import io
import re
# import sys


import sphinx_rtd_theme

# -- Project information -----------------------------------------------------

def read(*names, **kwargs):
    with io.open(
        os.path.join(os.path.dirname(__file__), *names),
        encoding=kwargs.get("encoding", "utf8")
    ) as fp:
        return fp.read()

def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

project = 'PyDSS'
copyright = '2018-2026, Aadil Latif'
author = 'Aadil Latif'

# The full version, including alpha/beta/rc tags
release = find_version("../../src/pydss", "__init__.py")

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.napoleon', 'sphinx.ext.ifconfig', "sphinx_click", "sphinxcontrib.openapi", 'sphinxcontrib.redoc',
    'sphinx.ext.autosectionlabel', 'sphinx.ext.githubpages', 'sphinx.ext.todo', "sphinxcontrib.autodoc_pydantic",
    'sphinx.ext.todo', 'sphinx.ext.autosummary', 'sphinx.ext.extlinks',
    'sphinx.ext.autodoc', 'sphinx.ext.coverage', 'sphinx.ext.doctest',
    'sphinx.ext.inheritance_diagram', 'sphinx.ext.imgmath', "sphinx_enum_extend",
    'sphinx.ext.autodoc', 'sphinx.ext.viewcode', 'enum_tools.autoenum',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
#html_theme = 'classic'
#tml_theme = 'sphinx_rtd_theme'
html_theme = 'furo'
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

# html_theme_options = {
#     'collapse_navigation': False,
#     'sticky_navigation': True,
#     'titles_only': False
# }

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

autosectionlabel_prefix_document = True

redoc = [
    {
        'name': 'Pydss API',
        'page': 'api',
        'spec': 'spec/swagger.yml',
        'embed': True,
    },
]

autosummary_generate = True
autodoc_pydantic_model_show_json = True
autodoc_pydantic_settings_show_json = True
autodoc_pydantic_model_erdantic_figure_collapsed = True