"""Utility functions for the jade package."""

from datetime import datetime, timedelta
from pathlib import Path
import shutil
import gzip
import json
import os
import re
import sys

from loguru import logger
import pandas as pd
import numpy as np
from pydss.exceptions import InvalidParameter
from pydss.utils import toml_utils


MAX_PATH_LENGTH = 255
DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"  # '%Y-%m-%d %H:%M:%S.%f', "%m/%d/%Y %H:%M:%S"


def _get_module_from_extension(filename, **kwargs):
    if isinstance(filename, Path):
        ext = filename.suffix.lower()
    else:
        ext = os.path.splitext(filename)[1].lower()
    if ext == ".json":
        mod = json
    elif ext == ".toml":
        mod = toml_utils
    elif "mod" in kwargs:
        mod = kwargs["mod"]
    else:
        raise InvalidParameter(f"Unsupported extension {filename}")

    return mod


def dump_data(data, filename, **kwargs):
    """Dump data to the filename.
    Supports JSON, TOML, YAML, or custom via kwargs.

    Parameters
    ----------
    data : dict
        data to dump
    filename : str
        file to create or overwrite

    """
    mod = _get_module_from_extension(filename, **kwargs)
    mode = "wb" if mod is toml_utils else "w"
    with open(filename, mode) as f_out:
        mod.dump(data, f_out)

    logger.debug(
        f"Dumped data to {filename}",
    )


def load_data(filename, **kwargs):
    """Load data from the file.
    Supports JSON, TOML, YAML, or custom via kwargs.

    Parameters
    ----------
    filename : str

    Returns
    -------
    dict

    """
    mod = _get_module_from_extension(filename, **kwargs)
    mode = "rb" if mod is toml_utils else "r"
    with open(filename, mode) as f_in:
        data = mod.load(f_in)

    logger.debug(
        f"Loaded data from {filename}",
    )
    return data


def get_cli_string():
    """Return the command-line arguments issued.

    Returns
    -------
    str

    """
    return os.path.basename(sys.argv[0]) + " " + " ".join(sys.argv[1:])


def decompress_file(filename):
    """Decompress a file.

    Parameters
    ----------
    filename : str

    Returns
    -------
    str
        Returns the new filename.

    """
    assert os.path.splitext(filename)[1] == ".gz"

    new_filename = filename[:-3]
    with open(new_filename, "wb") as f_out:
        with gzip.open(filename, "rb") as f_in:
            shutil.copyfileobj(f_in, f_out)

    os.remove(filename)
    logger.debug("Decompressed %s", new_filename)
    return new_filename


def interpret_datetime(timestamp):
    """Return a datetime object from a timestamp string.

    Parameters
    ----------
    timestamp : str

    Returns
    -------
    datetime.datetime

    """
    formats = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d_%H:%M:%S.%f",
        "%Y-%m-%d_%H-%M-%S-%f",
        DATE_FORMAT,
    )

    for i, fmt in enumerate(formats):
        try:
            return datetime.strptime(timestamp, fmt)
        except ValueError:
            if i == len(formats) - 1:
                raise
            continue


def make_human_readable_size(size, decimals=2):
    """Convert bytes to human readable representation.

    Parameters
    ----------
    size : float
        Size in bytes.
    decimals : int, optional
        the decimal places, by default 2

    Returns
    -------
    str:
        Human reable size string with unit.
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimals}f} {unit}"


def make_json_serializable(obj):
    if isinstance(obj, np.int64):
        obj = int(obj)
    elif isinstance(obj, complex):
        obj = str(obj)
    elif isinstance(obj, np.ndarray):
        if len(obj) > 0 and isinstance(obj[0], complex):
            obj = [str(x) for x in obj]
        else:
            obj = [x for x in obj]
    return obj


def make_timestamps(data):
    return pd.to_datetime(data, unit="s")


def serialize_timedelta(timedelta_object):
    return f"days={timedelta_object.days}, seconds={timedelta_object.seconds}"


def deserialize_timedelta(text):
    regex = re.compile(r"days=(\d+), seconds=(\d+)")
    match = regex.search(text)
    if match:
        days = int(match.group(1))
        seconds = int(match.group(2))
        return timedelta(days=days, seconds=seconds)
    raise Exception(f"invalid time string: {text}")
