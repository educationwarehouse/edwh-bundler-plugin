# methods for converting CSS files
import contextlib
import os
import sys
import textwrap
import typing
import warnings

import sassquatch
from configuraptor import load_data as try_load_data
from configuraptor.core import T_data
from configuraptor.errors import FailedToLoad

from .shared import _del_whitespace, extract_contents_cdn, extract_contents_local, ignore_ssl

SCSS_TYPES = None | bool | int | float | str | list["SCSS_TYPES"] | dict[str, "SCSS_TYPES"]

def load_data(data: T_data, **kwargs) -> dict[str, typing.Any]:
    try:
        kwargs["strict"] = True
        return try_load_data(data, **kwargs)
    except FailedToLoad as e:
        print('ja hallo', e, e.__cause__)
        return {}

@contextlib.contextmanager
def as_warning(exception_type: typing.Type[Exception]):
    # works similarly to contextlib.suppress but prints the error as warning instead.
    # however, pycharm does not understand it, so you will get annoying "Code Unreachable"
    try:
        yield
    except exception_type as e:
        filename = e.__traceback__.tb_frame.f_code.co_filename
        line_number = e.__traceback__.tb_lineno
        warnings.warn_explicit(str(e), source=e, lineno=line_number, filename=filename, category=UserWarning)


def try_sass_compile(
    code: str, verbose: bool, **kwargs: typing.Unpack[sassquatch.SassSettings]
) -> typing.Optional[str]:
    kwargs.setdefault("verbose", verbose)
    kwargs.setdefault("quiet", not verbose)
    try:
        return sassquatch.compile(string=code, **kwargs)
    except sassquatch.CompileError as e:
        if verbose:
            cprint(str(e), file=sys.stderr, color="red")
        return None


def convert_scss(
    contents: str,
    minify: bool = True,
    path: list[str] = None,
    insert_variables: dict[str, SCSS_TYPES] = None,
    verbose: bool = False,
) -> str:
    """
    Convert SCSS to plain CSS, optionally remove newlines and duplicate whitespace

    Args:
        contents: SCSS/SASS String
        minify: should the output be minified?
        path: which directory does the file exist in? (for imports)
        insert_variables: Python variables to prefix the contents with
        verbose: print scss/sass compile errors?

    Returns: CSS String
    """
    path = path or ["."]

    insert_variables = insert_variables or {}

    output_style = "compressed" if minify else "expanded"  # type: typing.Literal["expanded", "compressed"]

    # first try: scss
    variables = convert_to_css_variables("scss", **insert_variables)

    if result := try_sass_compile(variables + contents, verbose, load_path=path, style=output_style):
        return result

    # next try: sass
    variables = convert_to_css_variables("sass", **insert_variables)

    if result := try_sass_compile(
        variables + contents,
        verbose,
        indented=True,
        load_path=path,
        style=output_style,
    ):
        return result

    # last option: sass with fixed indentation:
    if result := try_sass_compile(
        variables + textwrap.dedent(contents), verbose, indented=True, load_path=path, style=output_style
    ):
        return result

    if verbose:
        print(f"{variables=}", file=sys.stderr)
        print(f"{contents=}", file=sys.stderr)
    raise sassquatch.CompileError(
        stderr="Something went wrong with your styles. Are you sure they have valid scss/sass syntax?"
    )


def load_css_contents(file: str, cache: bool = True):
    if file.startswith(("http://", "https://")):
        # download
        return extract_contents_cdn(file, cache)
    elif file.endswith((".css", ".scss", ".sass")):
        # read
        return extract_contents_local(file)
    elif file.startswith("//") or file.startswith("/*"):  # scss and css
        # raw code, should start with comment in CSS to identify it
        return file
    else:
        raise NotImplementedError(
            f"File type of {file} could not be identified. "
            f"If you want to add inline code, add a comment at the top of the block."
        )


def prepend_global_css_variables(combined: str, settings: dict) -> str:
    # postprocess step for css
    minify = settings.get("minify", 0)
    variables = load_data(settings.get("scss_variables", {}))
    css_root_variables = convert_to_css_variables("css", **variables)
    css_root_variables = _del_whitespace(css_root_variables) if minify else css_root_variables

    return f"{css_root_variables}\n{combined}" if css_root_variables else combined


def extract_contents_for_css(file: dict | str, settings: dict, cache=True, minify=True, verbose=False) -> str:
    ignore_ssl()

    variables = load_data(settings.get("scss_variables", {}))
    scss = False
    scope = None
    if isinstance(file, dict):
        data = file
        file = data["file"]
        if block_variables := load_data(data.get("variables", {})):
            variables |= block_variables
            scss = True
        if scope := data.get("scope"):
            scss = True

    contents = load_css_contents(file, cache)

    file = file.split("?")[0].strip()

    if scss or file.endswith((".scss", ".sass")) or file.startswith("//"):
        if scope:
            contents = "%s{%s}" % (scope, contents)
        contents = convert_scss(
            contents, minify=minify, path=[os.path.dirname(file)], insert_variables=variables, verbose=verbose
        )
    elif minify:
        contents = _del_whitespace(contents)

    return contents


### python to scss
def convert_scss_key(key: str, _level: int = 0) -> str:
    prefix = "" if _level else "$"
    return prefix + key.replace("_", "-")


def convert_scss_value(value: SCSS_TYPES, _level: int = 0) -> str:
    _level += 1

    match value:
        case str():
            return value.removesuffix(";")  # ; is handled on another level
        case list():
            converted = ", ".join(convert_scss_value(_, _level=_level) for _ in value)
            if _level > 1:
                # nested - include parens ()
                converted = f"({converted})"
            return converted
        case dict():
            converted = ", ".join(
                (
                    f"{convert_scss_key(key, _level=_level)}: {convert_scss_value(value, _level=_level + 1)}"
                    for key, value in value.items()
                )
            )
            return f"({converted})"
        case float():
            return str(value)
        case None:
            return "null"
        case True:
            return "true"
        case False:
            return "false"
        # int must come AFTER bool (otherwise True and False are matched)
        case int():
            return str(value)
        case _:
            raise NotImplementedError(f"Unsupported type {type(value)}")


def convert_to_css_variables(_language: typing.Literal["scss", "sass", "css"], **variables) -> str:
    code = ""
    eol = "\n" if _language == "sass" else ";\n"

    if _language == "css":
        for key, value in variables.items():
            if isinstance(value, dict):
                # unsupported in css:
                continue

            css_key = "--" + key.replace("_", "-")
            css_value = convert_scss_value(value)
            code += f" {css_key}: {css_value}{eol}"
        return ":root {\n%s}" % code if code else ""
    else:
        for key, value in variables.items():
            key = convert_scss_key(key)
            value = convert_scss_value(value)
            code += f"{key}: {value}{eol}"

    return code
