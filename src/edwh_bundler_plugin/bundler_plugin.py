# default 'invoke' tasks

from __future__ import annotations

import io
import os
import re
import sqlite3
import sys
import typing
from contextlib import contextmanager
from datetime import datetime

import invoke
import yaml
from invoke import task

from .css import extract_contents_for_css
from .js import extract_contents_for_js
from .lazy import JIT
from .shared import truthy

now = datetime.utcnow

# prgram is created in __init__

# defaults/consts
DEFAULT_INPUT = "bundle.yaml"
DEFAULT_INPUT_LTS = "bundle-lts.yaml"
DEFAULT_OUTPUT_JS = "bundle.js"
DEFAULT_OUTPUT_CSS = "bundle.css"
TEMP_OUTPUT_DIR = "/tmp/bundle-build/"
TEMP_OUTPUT = ".bundle_tmp"
DEFAULT_ASSETS_DB = "py4web/apps/lts/databases/lts_assets.db"

load_dotenv = JIT("dotenv", "load_dotenv")


def load_config(fname: str = DEFAULT_INPUT, strict=False) -> dict:
    """
    Load yaml config from file name, default to empty or error if strict
    """
    if os.path.exists(fname):
        with open(fname) as f:
            return yaml.load(f, yaml.Loader)
    else:
        if strict:
            raise FileNotFoundError(fname)
        return {}


@contextmanager
def start_buffer(temp: str | typing.IO = TEMP_OUTPUT) -> typing.IO:
    """
    Open a temp buffer file in append mode and first remove old version if that exists
    """
    if isinstance(temp, io.IOBase):
        # already writable like io.StringIO or sys.stdout
        yield temp
        return

    if os.path.exists(temp):
        os.remove(temp)

    f = open(temp, "a")
    try:
        yield f
    finally:
        f.close()


def cli_or_config(
    value: typing.Any,
    config: dict,
    key: typing.Hashable,
    bool=True,
    default: typing.Any = None,
) -> bool | typing.Any:
    """
    Get a setting from either the config yaml or the cli (used to override config)
    cli > config > default

    Args:
        value: the value from cli, will override config if anything other than None
        config: the 'config' section of the config yaml
        key: config key to look in (under the 'config' section)
        bool: should the result alwasy be a boolean? Useful cli arguments such as --cache y,
                     but should probably be False for named arguments such as --filename ...
        default: if the option can be found in neither the cli arguments or the config file, what should the value be?
    """
    return (
        (truthy(value) if bool else value)
        if value is not None
        else config.get(key, default)
    )


def _fill_variables(setting: str | dict, variables: dict[re.Pattern, str]) -> str:
    """
    Fill in $variables in a dynamic setting.
    E.g. "$in_app/path/to/css" + {'in_app': 'apps/cmsx'} -> 'apps/cmsx/path/to/css'
    """
    if isinstance(setting, dict):
        # recursive fill nested values:
        return {k: _fill_variables(v, variables) for k, v in setting.items()}

    if "$" not in setting:
        return setting

    for reg, repl in variables.items():
        setting = reg.sub(str(repl), setting)

    return setting


def _regexify_settings(setting_dict: dict) -> dict:
    return {re.compile(rf"\${key}"): value for key, value in setting_dict.items()}


def _handle_files(
    files: list,
    callback: typing.Callable,
    output: str | typing.IO,
    verbose: bool,
    cache: bool,
    minify: bool,
    settings: dict,
):
    """
    Execute 'callback' (js or css specific) on all 'files'

    Args:
        files: list of files from the 'css' or 'js' section in the config yaml
        callback: method to execute to gather and process file contents
        output: final output file path to write to
        verbose: logs some info to stderr
        cache: use cache for online resources?
        minify: minify file contents?
        settings: other configuration options
    """
    re_settings = _regexify_settings(settings)

    output = _fill_variables(output, re_settings)
    files = [_fill_variables(f, re_settings) for f in files]

    if verbose:
        print(
            f"Building {callback.__name__.split('_')[-1]} [verbose]\n" f"{output=}\n",
            f"{minify=}\n",
            f"{cache=}\n",
            f"{files=}\n",
            file=sys.stderr,
        )

    if not files:
        if verbose:
            print("No files supplied, quitting", file=sys.stderr)
        return

    # if output starts with sqlite:// write to tmp and save to db later
    if output.startswith("sqlite://"):
        # database_path = output.split("sqlite://", 1)[1]
        output_filename = output.split("/")[-1]
        ts = datetime.now()
        ts = str(ts).replace(" ", "_")
        os.mkdir(f"{TEMP_OUTPUT_DIR}/{ts}")
        output = f"{TEMP_OUTPUT_DIR}/{ts}/{output_filename}"

    with start_buffer(output) as bufferf:
        for inf in files:
            res = callback(inf, cache=cache, minify=minify)
            bufferf.write(res + "\n")
            if verbose:
                print(f"Handled {inf}", file=sys.stderr)

    if not isinstance(output, io.IOBase):
        os.rename(bufferf.name, output)
    if verbose:
        print(f"Written final bundle to {output}", file=sys.stderr)

    return output


@task
def require_jsmin(c):
    try:
        import rjsmin
    except ImportError:
        c.run("pip install rjsmin")


@task
def require_httpx(c):
    try:
        import httpx
    except ImportError:
        c.run("pip install httpx")


@task
def require_sass(c):
    try:
        import sass
    except ImportError:
        c.run("pip install pysass")


@task
def require_dotenv(c):
    try:
        import dotenv
    except ImportError:
        c.run("pip install python-dotenv")


@task(iterable=["files"], pre=[require_jsmin, require_httpx])
def build_js(
    c,
    files=None,
    input=DEFAULT_INPUT,
    verbose=False,
    # overrule config:
    output=None,  # DEFAULT_OUTPUT_JS
    minify=None,
    cache=None,
    version=None,
    stdout=False,  # overrides output
):
    """
    Build the JS bundle (cli only)
    """
    config = load_config(input)

    files = files or config.get("js")

    if not files:
        raise ValueError(
            "Please specify either --files or the js key in a config yaml (e.g. bundle.yaml)"
        )

    settings = config.get("config", {})

    minify = cli_or_config(minify, settings, "minify")
    cache = cli_or_config(cache, settings, "cache", default=True)
    output = (
        sys.stdout
        if stdout
        else cli_or_config(output, settings, "output_js", bool=False)
        or DEFAULT_OUTPUT_JS
    )

    settings["version"] = cli_or_config(
        version, settings, "version", bool=False, default="latest"
    )

    return _handle_files(
        files,
        extract_contents_for_js,
        output,
        verbose=verbose,
        cache=cache,
        minify=minify,
        settings=settings,
    )


# import version:
def bundle_js(
    files: list = None,
    verbose: bool = False,
    output: str | typing.IO = None,
    minify: bool = True,
    cache: bool = True,
    **settings,
) -> typing.Optional[str]:
    """
    Importable version of 'build_js'.
    If output is left as None, the bundled code will be returned as a string

    Args:
        files: list of things to bundle
        verbose: print some info to stderr?
        output: filepath or IO to write to
        minify: minify files?
        cache: save external files to disk for re-use?

    Returns: bundle of JS
    """
    if output is None:
        output = io.StringIO()

    _handle_files(
        files,
        extract_contents_for_js,
        output,
        verbose=verbose,
        cache=cache,
        minify=minify,
        settings=settings,
    )

    if isinstance(output, io.StringIO):
        output.seek(0)
        return output.read()
    else:
        return output


@task(iterable=["files"], pre=[require_sass, require_httpx])
def build_css(
    c,
    files=None,
    input=DEFAULT_INPUT,
    verbose=False,
    # overrule config:
    output=None,  # DEFAULT_OUTPUT_CSS
    minify=None,
    cache=None,
    version=None,
    stdout=False,  # overrides output
):
    """
    Build the CSS bundle (cli only)
    """
    config = load_config(input)
    settings = config.get("config", {})

    minify = cli_or_config(minify, settings, "minify")
    cache = cli_or_config(cache, settings, "cache", default=True)

    settings["version"] = cli_or_config(
        version, settings, "version", bool=False, default="latest"
    )

    output = (
        sys.stdout
        if stdout
        else cli_or_config(output, settings, "output_css", bool=False)
        or DEFAULT_OUTPUT_CSS
    )

    files = files or config.get("css")

    if not files:
        raise ValueError(
            "Please specify either --files or the css key in a config yaml (e.g. bundle.yaml)"
        )

    return _handle_files(
        files,
        extract_contents_for_css,
        output,
        verbose=verbose,
        cache=cache,
        minify=minify,
        settings=settings,
    )


# import version:
def bundle_css(
    files: list = None,
    verbose: bool = False,
    output: str | typing.IO = None,
    minify: bool = True,
    cache: bool = True,
    **settings,
) -> typing.Optional[str]:
    """
    Importable version of 'build_css'.
    If output is left as None, the bundled code will be returned as a string

    Args:
        files: list of things to bundle
        verbose: print some info to stderr?
        output: filepath or IO to write to
        minify: minify files?
        cache: save external files to disk for re-use?

    Returns: bundle of CSS
    """
    if output is None:
        output = io.StringIO()

    _handle_files(
        files,
        extract_contents_for_css,
        output,
        verbose=verbose,
        cache=cache,
        minify=minify,
        settings=settings,
    )

    if isinstance(output, io.StringIO):
        output.seek(0)
        return output.read()
    else:
        return output


@task(iterable=["files"], pre=[require_sass, require_jsmin, require_httpx])
def build(
    c,
    input=DEFAULT_INPUT,
    verbose=False,
    # defaults from config, can be overwritten:
    output_js=None,  # DEFAULT_OUTPUT_JS
    output_css=None,  # DEFAULT_OUTPUT_CSS
    minify=None,
    cache=None,
    version=None,
):
    """
    Build the JS and CSS bundle
    """
    # invoke build

    # second argument of build_ is None, so files will be loaded from config.
    # --files can be supplied for the build-js or build-css methods, but not for normal build
    # since it would be too ambiguous to determine whether the files should be compiled as JS or CSS.
    return (
        build_js(c, None, input, verbose, output_js, minify, cache, version),
        build_css(c, None, input, verbose, output_css, minify, cache, version),
    )


def XOR(first, *extra):
    result = bool(first)
    for item in extra:
        result ^= bool(item)

    return result


def dict_factory(cursor, row):
    # https://stackoverflow.com/questions/3300464/how-can-i-get-dict-from-sqlite-query

    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def assert_chmod_777(c: invoke.context.Context, filepath: str):
    resp = c.run(f'stat --format "%a  %n" {filepath}', hide=True)
    chmod = resp.stdout.split(" ")[0]
    if chmod != 777:
        c.sudo(f"chmod 777 {filepath}")


def config_setting(key, default=None, config=None, config_path=None):
    if not config:
        config = load_config(config_path or DEFAULT_INPUT_LTS)
    re_settings = _regexify_settings(config)
    var = config.get(key, default)
    return _fill_variables(var, re_settings)


def setup_db(
    c: invoke.context.Context, config_path=DEFAULT_INPUT_LTS
) -> sqlite3.Connection:
    db_path = config_setting("output_db", DEFAULT_ASSETS_DB, config_path=config_path)

    assert_chmod_777(c, db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = dict_factory
    return con


def get_latest_version(db: sqlite3.Connection, type=None) -> dict:
    query = ["SELECT *", "FROM bundle_version"]

    if type:
        query.append(f"WHERE filetype = '{type}'")

    query.append("ORDER BY major DESC, minor DESC, patch DESC")

    cur = db.execute(" ".join(query))
    return cur.fetchone() or {}


def _update_assets_sql(c: invoke.context.Context):
    """
    ... todo docs ...
    Should be done after each db.commit()
    """
    # for line in db.iterdump():
    db_path = config_setting("output_db", DEFAULT_ASSETS_DB)
    sql: invoke.Result = c.run(f"sqlite3 {db_path} .dump", hide=True)

    sql_path = db_path.replace(".db", ".sql")
    with open(sql_path, "w", encoding="UTF-8") as f:
        f.write(sql.stdout)


@task
def update_assets_sql(c):
    # db = setup_db(c)
    _update_assets_sql(c)


def insert_version(c: invoke.context.Context, db: sqlite3.Connection, values: dict):
    columns = ", ".join(values.keys())
    placeholders = ":" + ", :".join(values.keys())

    query = "INSERT INTO bundle_version ({}) VALUES ({})"

    db.execute(query.format(columns, placeholders), values)
    db.commit()
    _update_assets_sql(c)


def version_exists(db: sqlite3.Connection, filetype: str, version: str):
    query = (
        "SELECT COUNT(*) as c FROM bundle_version WHERE filetype = ? AND version = ?;"
    )

    return db.execute(query, (filetype, version)).fetchone()["c"] > 0


def prompt_changelog(db: sqlite3.Connection, filetype: str, version: str):
    load_dotenv()

    query = (
        "SELECT id, changelog FROM bundle_version WHERE filetype = ? AND version = ?;"
    )
    row = db.execute(query, (filetype, version)).fetchone()
    if row["changelog"]:
        print("Changelog already filled in! ", "It can be updated at:")
    else:
        print(f"Please fill in a changelog for this {filetype} publication at: ")

    idx = row["id"]

    hostingdomain = os.environ.get("HOSTINGDOMAIN", "your.domain")

    print(f"https://py4web.{hostingdomain}/lts/manage_versions/edit/{idx}")


@task(pre=[require_dotenv])
def show_changelog_url(c, filetype, version):
    db = setup_db(c)
    prompt_changelog(db, filetype, version)


def confirm(prompt: str, force=False) -> bool:
    return force or truthy(input(prompt))


@task(pre=[require_dotenv, require_jsmin, require_sass, require_httpx])
def publish(
    c,
    version=None,
    major=False,
    minor=False,
    patch=False,
    filename=None,
    js=True,
    css=True,
    verbose=False,
    config=DEFAULT_INPUT_LTS,
    force=False,
):
    c: invoke.context.Context
    db = setup_db(c)
    previous = get_latest_version(db, "js")

    if not os.path.exists(TEMP_OUTPUT_DIR):
        os.mkdir(TEMP_OUTPUT_DIR)

    if not any((version, major, minor, patch)):
        print("Previous version is:", previous.get("version", "0.0.0"))
        version = input("Which version would you like to publish? ")
    elif not XOR(version, major, minor, patch):
        # error on more than one:
        raise ValueError(
            "Please specify only one of --version, --major, --minor or --patch"
        )
    elif major:
        new_major = previous.get("major", 0) + 1
        version = f"{new_major}.0.0"
    elif minor:
        major = previous.get("major", 0)
        new_minor = previous.get("minor", 0) + 1
        version = f"{major}.{new_minor}.0"
    elif patch:
        major = previous.get("major", 0)
        minor = previous.get("minor", 0)
        new_patch = previous.get("patch", 0) + 1
        version = f"{major}.{minor}.{new_patch}"

    version_re = re.compile(r"^(\d{1,3})(\.\d{1,3})?(\.\d{1,3})?$")
    if not (groups := version_re.findall(version)):
        raise ValueError(
            f"Invalid version {version}. Please use the format major.major.patch (e.g. 3.5.0)"
        )

    major, minor, patch = (
        int(groups[0][0]),
        int(groups[0][1].strip(".") or 0),
        int(groups[0][2].strip(".") or 0),
    )

    version = f"{major}.{minor}.{patch}"

    if js and version_exists(db, "js", version):
        print(f"JS Version {version} already exists!")
        js = confirm("Are you sure you want to overwrite it? ", force)

    if css and version_exists(db, "css", version):
        print(f"CSS Version {version} already exists!")
        css = confirm("Are you sure you want to overwrite it? ", force)

    if js and css:
        output_js, output_css = build(c, input=config, version=version, verbose=verbose)
    elif js:
        output_js = build_js(c, input=config, version=version, verbose=verbose)
        output_css = None
    elif css:
        output_css = build_css(c, input=config, version=version, verbose=verbose)
        output_js = None
    else:
        # no build
        output_css = output_js = None

    if output_js:
        with open(output_js, "r", encoding="UTF-8") as f:
            file_contents = f.read()

        filename = output_js.split("/")[-1]
        hash = c.run(f"sha1sum {output_js}", hide=True).stdout.split(" ")[0]

        if hash == previous.get("hash"):
            print("JS hash matches previous version.")
            go = confirm("Are you sure you want to release a new version? ", force)
        else:
            go = True

        if go:
            insert_version(
                c,
                db,
                {
                    "filetype": "js",
                    "version": version,
                    "filename": filename,
                    "major": major,
                    "minor": minor,
                    "patch": patch,
                    "hash": hash,
                    "created_at": now(),
                    "changelog": "",
                    "contents": file_contents,
                },
            )
            print(f"JS version {version} published.")
            prompt_changelog(db, "js", version)

    if output_css:
        with open(output_css, "r", encoding="UTF-8") as f:
            file_contents = f.read()

        previous_css = get_latest_version(db, "css")

        filename = output_css.split("/")[-1]
        hash = c.run(f"sha1sum {output_css}", hide=True).stdout.split(" ")[0]

        if hash == previous_css.get("hash"):
            print("CSS hash matches previous version.")
            go = confirm("Are you sure you want to release a new version? ", force)
        else:
            go = True

        if go:
            insert_version(
                c,
                db,
                {
                    "filetype": "css",
                    "version": version,
                    "filename": filename,
                    "major": major,
                    "minor": minor,
                    "patch": patch,
                    "hash": hash,
                    "created_at": now(),
                    "changelog": "",
                    "contents": file_contents,
                },
            )
            print(f"CSS version {version} published.")
            prompt_changelog(db, "css", version)

    from shutil import rmtree

    rmtree(TEMP_OUTPUT_DIR)

    # after publish: run `up -s py4web` so the bjoerns are all updated
    c.run("inv up -s py4web")


@task
def list(c):
    db = setup_db(c)
    for row in db.execute(
        "SELECT filetype, version FROM bundle_version ORDER BY major DESC, minor DESC, patch DESC"
    ).fetchall():
        print(row)


@task
def reset(c):
    db = setup_db(c)
    if not confirm("Are you sure you want to reset the versions database? "):
        print("Wise.")
        return

    db.execute("DELETE FROM bundle_version;")
    db.commit()
    _update_assets_sql(c)

    assert db.execute("SELECT COUNT(*) as c FROM bundle_version;").fetchone()["c"] == 0


# DEV:

#
# @task
# def update_dependencies(c):
#     # invoke update-dependencies
#     c.run("pip-compile requirements.in")
#     c.run("pip-compile requirements-dev.in")
#     c.run("pip-sync *.txt")