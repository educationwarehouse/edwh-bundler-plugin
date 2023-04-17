# methods for converting JS and hyperscript files

from __future__ import annotations

from functools import singledispatch

from rjsmin import jsmin

from .shared import (
    extract_contents_cdn,
    extract_contents_local,
    HS_COMMENT_RE,
    DOUBLE_SPACE_RE,
    _del_whitespace,
)


@singledispatch
def extract_contents_for_js(file, cache=True, minify=True) -> str:
    """
    'file' is one line in the 'js' part of the config yaml.
    > singledispatch executes a different method based on the Type of the variable 'file'
    (yes, useful typing in Python - wow.)

    Args:
        file (str): file/url path (dict is only supported in CSS right now)
        cache (bool): get CDN files from local cache
        minify (bool): minify file (using rjsmin for js or custom logic for hyperscript)

    Returns: string of contents to write to the js bundle

    """
    raise NotImplementedError("unknown type used, please use str or dict as first arg")


@extract_contents_for_js.register
def _(file: str, cache=True, minify=True) -> str:
    """
    Download file from remote if a url is supplied, load from local otherwise.
    If unsupported extension is used, an error will be thrown
    """

    if file.startswith(("http://", "https://")):
        # download
        contents = extract_contents_cdn(file, cache)
    elif file.endswith((".js", "._hs", ".html", ".htm")):
        # read
        contents = extract_contents_local(file)
    elif file.startswith(("_(", "//", "/*", "_hyperscript(")):
        # raw code, should start with comment in JS to identify it
        contents = file
    else:
        raise NotImplementedError(f"File type of {file} could not be identified.")

    file = file.split("?")[0]

    if file.endswith("._hs"):
        if minify:
            contents = hsmin(contents)

        contents = _include_hyperscript(contents)
    elif file.endswith(".html"):
        contents = _append_to_dom(contents)
    elif file.endswith(".js") and minify:
        contents = jsmin(contents)
    elif file.endswith(".css"):
        if minify:
            contents = _del_whitespace(contents)
        contents = _append_to_head(contents)

    return contents


@extract_contents_for_js.register
def _(file: dict, cache=True, minify=True) -> str:
    raise NotImplementedError("dict for JS entries is not supported yet")


def _include_hyperscript(contents: str) -> str:
    """
    Execute the _hs file with the '_hyperscript' function, escaping some characters
    """
    contents = contents.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("{", "\\{")

    return f"_hyperscript(`{contents}`)"


def _append_to_dom(html: str) -> str:
    """
    Append some html fragment at the end of the page
    """
    html = html.replace("`", "\\`")
    return f"""document.body.innerHTML += `{html}`"""


def _append_to_head(css: str) -> str:
    """
    Append some CSS fragment at the end of the head of the page
    """
    css = css.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("{", "\\{")
    return f"document.head.innerHTML += `<style>{css}</style>`"


def hsmin(contents: str) -> str:
    """
    Minify hyperscript code by removing comments and minimizing whitespace
    """
    # " \n " -> "   " -> " "
    return DOUBLE_SPACE_RE.sub(
        " ",
        # -- at the first line will not be caught by HS_COMMENT_RE, so prefix with newline
        HS_COMMENT_RE.sub(" ", "\n" + contents)
        # replace every newline with space for minification
        .replace("\n", " "),
    )
