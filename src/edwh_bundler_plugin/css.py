# methods for converting CSS files
from __future__ import annotations

import textwrap
import typing
from functools import singledispatch

from .lazy import JIT
from .shared import _del_whitespace, extract_contents_cdn, extract_contents_local, truthy

import sass


def convert_scss(contents: str, minify=True) -> str:
    """
    Convert SCSS to plain CSS, optionally remove newlines and duplicate whitespace

    Args:
        contents (str): SCSS/SASS String
        minify (bool):

    Returns: CSS String

    """
    try:
        contents = sass.compile(string=contents)
    except sass.CompileError:
        # it was not scss, try sass instead:
        try:
            sass.compile(string=contents, indented=True)
        except sass.CompileError:
            # try to fix broken indentation:
            sass.compile(string=textwrap.dedent(contents), indented=True)

    if minify:
        contents = _del_whitespace(contents)

    return contents


@singledispatch
def extract_contents_for_css(file, cache=True, minify=True) -> str:
    """
    'file' is one line in the 'css' part of the config yaml.
    > singledispatch executes a different method based on the Type of the variable 'file'
    (yes, useful typing in Python - wow.)

    Args:
        file (str | dict): file/url path or dict with key 'file' and optional 'scope' and 'scss'.
                            If 'scope' is provided, all classes will be prefixed in that parent selector.
        cache (bool): get CDN files from local cache
        minify (bool): minify file (remove newlines in the case of CSS)

    Returns: string of contents to write to the css bundle

    """
    raise NotImplementedError("unknown type used, please use str or dict as first arg")


@extract_contents_for_css.register
def _(file: str, cache=True, minify=True):
    """
    Version of 'extract_contents_for_css' for when file is a string (-> file/url path)
    """
    if file.startswith(("http://", "https://")):
        # download
        contents = extract_contents_cdn(file, cache)
    elif file.endswith((".css", ".scss", ".sass")):
        # read
        contents = extract_contents_local(file)
    elif file.startswith("//"):  # scss
        # raw code, should start with comment in CSS to identify it
        contents = file
    elif file.startswith("/*"):  # css
        # raw code, should start with comment in CSS to identify it
        contents = file
    else:
        raise NotImplementedError(
            f"File type of {file} could not be identified. If you want to add inline code, add a comment at the top of the block."
        )

    file = file.split("?")[0].strip()

    if file.endswith((".scss", ".sass")) or file.startswith("//"):
        contents = convert_scss(contents, minify=minify)
    elif minify:
        contents = _del_whitespace(contents)

    return contents


@extract_contents_for_css.register
def _(file: dict, cache=True, minify=True):
    """
    Version of extract_contents_for_css for when a dict is supplied in the config yaml.

    e.g.
    css:
      - file: https://path.to.cdn/bulma.css
        scope: #bulma-section
      - file: https:/path.to.cdn/some_raw.scss
        scss: 1
    """
    f = file["file"]
    contents = extract_contents_for_css(f, cache=cache, minify=minify)

    scss = truthy(file.get("scss")) or f.endswith(".scss") or contents.strip().startswith("//")

    if scope := file.get("scope"):
        # scope the (S)css:
        contents = "%s{%s}" % (scope, contents)
        scss = True
    # more options?

    if scss:
        contents = convert_scss(contents, minify)
    elif minify:
        contents = _del_whitespace(contents)

    return contents
