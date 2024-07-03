# code used by both js.py and css.py (and possibly tasks.py)
from __future__ import annotations

import hashlib
import os
import re
from functools import singledispatch
from pathlib import Path

import requests

_CACHE_DIR = ".cdn_cache"
CACHE_DIR = Path(_CACHE_DIR)

# https://stackoverflow.com/questions/70064025/regex-pattern-to-match-comments-but-not-urls
HS_COMMENT_RE = re.compile(r"(?<=[^:])(//|--).+$", re.MULTILINE)
DOUBLE_SPACE_RE = re.compile(" {2,}")


def _del_whitespace(contents: str) -> str:
    return DOUBLE_SPACE_RE.sub(" ", contents.replace("\n", " "))


def _extract_contents_cdn(url: str) -> str:
    """
    Download contents from some url
    """
    return requests.get(url, allow_redirects=True, timeout=10).text


def cache_hash(filename: str) -> str:
    """
    Cached CDN Files are stored by the hash if its url
    """

    # sha1 will probably™ have no collsions
    return hashlib.sha1(filename.encode("UTF-8")).hexdigest()


def extract_contents_cdn(url: str, cache=True) -> str:
    """
    Download contents from some url or from cache if possible/desired

    Args:
        url (str): online resource location
        cache (bool): use .cdn_cache if possible?
    """
    if not cache:
        return _extract_contents_cdn(url)

    h_url = str(cache_hash(url))

    cache_path = CACHE_DIR / h_url
    if cache_path.exists():
        return extract_contents_local(str(cache_path))
    _resp = _extract_contents_cdn(url)

    if not CACHE_DIR.exists():
        os.mkdir(CACHE_DIR)

    with open(cache_path, "w") as f:
        f.write(_resp)
    return _resp


def extract_contents_local(path: str | Path) -> str:
    """
    Read a file from disk
    """
    with open(path) as f:
        return f.read()


@singledispatch
def truthy(val) -> bool:
    """
    Validate if the cli argument passed is something indicating yes (e.g. 1, y, t) or simply a boolean True

    Args:
        val (bool | str):

    Returns:

    """
    raise TypeError(f"{type(val)} could not be evaluated (only str or bool)")


@truthy.register
def _(val: bool):
    """
    Usually truthy() will be used with a string
    but sometimes it can be useful to not have to do typechecking in the code,
    ergo this case
    """
    return val


@truthy.register
def _(val: None):
    """
    Usually truthy() will be used with a string
    but sometimes it can be useful to not have to do typechecking in the code,
    ergo this case
    """
    return val


@truthy.register
def _(val: str):
    """
    Useful for cli interaction with lazy people
    """
    return val.lower().startswith(("1", "t", "y"))  # true, yes etc.


@truthy.register
def _(val: int):
    """
    Negative numbers are often not truthy
    """
    return val > 0
