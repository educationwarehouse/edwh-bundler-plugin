# methods for converting JS/TS and hyperscript files
from __future__ import annotations

from pathlib import Path
from typing import Optional

import dukpy
from rjsmin import jsmin

from .shared import (
    DOUBLE_SPACE_RE,
    HS_COMMENT_RE,
    _del_whitespace,
    extract_contents_cdn,
    extract_contents_local,
)


def find_dependencies(ts_compiled: str) -> list[str]:
    """
    Use dukpy to parse a System.register call in order to extract paths of TS dependencies (e.g. `./shared`).
    """
    system_code = """
    const System = {
        register(deps, _) {
            return deps
        }
    };
    """
    return dukpy.evaljs(f"{system_code};{ts_compiled}")


def extract_contents_typescript(_path: str | Path, settings: dict, name: Optional[str] = None) -> str:
    """
    Convert typescript to JS (via dukpy) and prepend dependencies.
    """
    path = Path(_path)
    typescript_code = extract_contents_local(path)

    js_code = dukpy.typescript_compile(typescript_code)

    dependencies = find_dependencies(js_code)
    # System.register([deps] ...
    # -> System.register(namespace, [deps] ...
    namespace = name or "__main__"
    js_code = js_code.replace("System.register(", f"System.register('{namespace}', ", 1)

    for dep in dependencies:
        key = f"__typescript_dependency_{dep}__"
        if key in settings:
            # already included
            continue

        settings[key] = True
        dep_path = path.parent.joinpath(dep).with_suffix(".ts")

        dep_code = extract_contents_typescript(dep_path, settings, name=dep)

        js_code = dep_code + "\n" + js_code

    return include_typescript_system_loader(settings) + js_code


LOADER_KEY = "__loader_code_included_once__"


def include_typescript_system_loader(settings: dict):
    """
    Instead of depending on SystemJS like dukpy does,
    ts_loader.js contains a custom loader that tracks and injects dependencies at build time.
    """
    if LOADER_KEY in settings:
        return ""

    pth = Path(__file__).parent / "js/ts_loader.js"
    loader_code = extract_contents_local(pth)

    settings[LOADER_KEY] = 1

    return loader_code


def extract_contents_for_js(file: str, settings: dict, cache=True, minify=True, verbose=False) -> str:
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
    elif file.endswith(".ts"):
        contents = extract_contents_typescript(file, settings)
        if minify:
            contents = jsmin(contents)

    elif file.startswith(("_(", "//", "/*", "_hyperscript(")):
        # raw code, should start with comment in JS to identify it
        contents = file
    else:
        raise NotImplementedError(
            f"File type of {file} could not be identified. If you want to add inline code, add a comment at the top of the block."
        )

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
