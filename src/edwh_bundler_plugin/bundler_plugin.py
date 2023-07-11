# default 'invoke' tasks

from __future__ import annotations

import io
import os
import re
import sqlite3
import sys
import typing
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import invoke
import tomlkit
import yaml
from invoke import task, Context
from dotenv import load_dotenv
from shutil import rmtree

from .css import extract_contents_for_css
from .js import extract_contents_for_js
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
DEFAULT_ASSETS_DB = "/tmp/lts_assets.db"
DEFAULT_ASSETS_SQL = "py4web/apps/lts/databases/lts_assets.sql"


def convert_data(data: dict[str, typing.Any] | list[typing.Any] | typing.Any):
    """
    Recursively replace "-" in keys to "_"
    """
    if isinstance(data, dict):
        return {key.replace("-", "_"): convert_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_data(value) for value in data]
    else:
        # normal value, don't change!
        return data


def _load_config_yaml(fname: str):
    with open(fname) as f:
        data = yaml.load(f, yaml.Loader)

    return convert_data(data)


def _load_config_toml(fname: str, key: str = ""):
    with open(fname) as f:
        data = tomlkit.load(f)

    if key:
        for part in key.split("."):
            data = data.get(part)
            if data is None:
                # key not found in toml!
                return {}

    return convert_data(data)


def _load_config(fname: str = DEFAULT_INPUT, strict=False) -> tuple[str, dict]:
    """
    Load yaml config from file name, default to empty or error if strict
    """
    if os.path.exists(fname) and fname.endswith((".yml", ".yaml")):
        # load default or user-defined yaml
        return fname, _load_config_yaml(fname)
    elif os.path.exists(fname) and fname.endswith(".toml"):
        # load user defined toml
        return fname, _load_config_toml(fname)
    elif fname == DEFAULT_INPUT and (altname := DEFAULT_INPUT.replace(".yaml", ".toml")) and os.path.exists(altname):
        # try bundle.toml
        return altname, _load_config_toml(altname)
    elif (altname := "pyproject.toml") and os.path.exists(altname):
        # look in pyproject
        return altname, _load_config_toml(altname, key="tool.edwh.bundle")
    elif strict:
        # err !
        raise FileNotFoundError(fname)
    else:
        # fallback to empty config
        return "", {}


def load_config(fname: str = DEFAULT_INPUT, strict=True) -> dict:
    file_used, data = _load_config(fname, strict=strict)
    if not data and strict:
        # empty config!
        raise ValueError(f"Config data found for `{file_used}` was empty!")

    return data or {}


@contextmanager
def start_buffer(temp: str | typing.IO = TEMP_OUTPUT) -> typing.IO:
    """
    Open a temp buffer file in append mode and first remove old version if that exists
    """
    if isinstance(temp, io.IOBase):
        # already writable like io.StringIO or sys.stdout
        yield temp
        return

    path = Path(temp)

    if path.exists():
        path.unlink()

    # ensure the path to the file exists:
    path.parent.mkdir(parents=True, exist_ok=True)

    f = path.open("a")
    try:
        yield f
    finally:
        f.close()


def cli_or_config(
        value: typing.Any,
        config: dict,
        key: typing.Hashable,
        bool: bool = True,
        default: typing.Any = None,
) -> bool | typing.Any:
    """
    Get a setting from either the config yaml or the cli (used to override config)
    cli > config > default

    Args:
        value: the value from cli, will override config if anything other than None
        config: the 'config' section of the config yaml
        key: config key to look in (under the 'config' section)
        bool: should the result always be a boolean? Useful cli arguments such as --cache y,
                     but should probably be False for named arguments such as --filename ...
        default: if the option can be found in neither the cli arguments or the config file, what should the value be?
    """
    return (truthy(value) if bool else value) if value is not None else config.get(key, default)


@typing.overload
def _fill_variables(setting: str, variables: dict[re.Pattern, str]) -> str:
    """
    If a string is passed as setting, the $variables in the string are filled.
    E.g. "$in_app/path/to/css" + {'in_app': 'apps/cmsx'} -> 'apps/cmsx/path/to/css'
    """


@typing.overload
def _fill_variables(setting: dict, variables: dict[re.Pattern, str]) -> dict[str, str]:
    """
    If a dict of settings is passed, all values are filled. Keys are left alone.
    """


def _fill_variables(setting: str | dict, variables: dict[re.Pattern, str]) -> str | dict[str, str]:
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


def _regexify_settings(setting_dict: dict[str, typing.Any]) -> dict[re.Pattern, typing.Any]:
    """
    Convert a dict keys from string to a compiled regex pattern (/$string/)
    """
    return {re.compile(rf"\${key}"): value for key, value in setting_dict.items()}


def store_file_hash(input_filename: str, output_filename: str = None):
    if output_filename is None:
        output_filename = f"{input_filename}.hash"
    c = Context()
    file_hash = calculate_file_hash(c, input_filename)
    with open(output_filename, "w") as f:
        f.write(file_hash)
    return output_filename


def _handle_files(
        files: list,
        callback: typing.Callable,
        output: str | typing.IO,
        verbose: bool,
        cache: bool,
        minify: bool,
        hash: bool,
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
            f"{hash=}\n",
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

    if hash:
        hash_file = store_file_hash(output)
        return (output, hash_file)

    return output


@task(iterable=["files"])
def build_js(
        c,
        files=None,
        input=DEFAULT_INPUT,
        verbose=False,
        # overrule config:
        output=None,  # DEFAULT_OUTPUT_JS
        minify=None,
        cache=None,
        hash=None,
        version=None,
        stdout=False,  # overrides output
):
    """
    Build the JS bundle (cli only)
    """
    config = load_config(input)

    files = files or config.get("js")

    if not files:
        raise NotFound("js")

    settings = config.get("config", {})

    minify = cli_or_config(minify, settings, "minify")
    cache = cli_or_config(cache, settings, "cache", default=True)
    hash = cli_or_config(hash, settings, "hash")

    output = sys.stdout if stdout else cli_or_config(output, settings, "output_js", bool=False) or DEFAULT_OUTPUT_JS

    settings["version"] = cli_or_config(version, settings, "version", bool=False, default="latest")

    return _handle_files(
        files,
        extract_contents_for_js,
        output,
        verbose=verbose,
        cache=cache,
        hash=hash,
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
        hash: bool = False,
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
        hash=hash,
        minify=minify,
        settings=settings,
    )

    if not isinstance(output, io.StringIO):
        return output

    output.seek(0)
    return output.read()


@dataclass
class NotFound(Exception):
    type: typing.Literal["js", "css"]

    def __str__(self):
        return f"Please specify either --files or the {self.type} key in a config yaml (e.g. bundle.yaml)"


@task(iterable=["files"], )
def build_css(
        c,
        files=None,
        input=DEFAULT_INPUT,
        verbose=False,
        # overrule config:
        output=None,  # DEFAULT_OUTPUT_CSS
        minify=None,
        cache=None,
        hash=None,
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
    hash = cli_or_config(hash, settings, "hash")

    settings["version"] = cli_or_config(version, settings, "version", bool=False, default="latest")

    output = sys.stdout if stdout else cli_or_config(output, settings, "output_css", bool=False) or DEFAULT_OUTPUT_CSS

    if not (files := (files or config.get("css"))):
        raise NotFound("css")

    return _handle_files(
        files,
        extract_contents_for_css,
        output,
        verbose=verbose,
        cache=cache,
        hash=hash,
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
        hash: bool = False,
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
        hash: should an additional .hash file be stored after generating the bundle?

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
        hash=hash,
        minify=minify,
        settings=settings,
    )

    if not isinstance(output, io.StringIO):
        return output

    output.seek(0)
    return output.read()


@task(iterable=["files"])
def build(
        c,
        input=DEFAULT_INPUT,
        verbose=False,
        # defaults from config, can be overwritten:
        output_js=None,  # DEFAULT_OUTPUT_JS
        output_css=None,  # DEFAULT_OUTPUT_CSS
        minify=None,
        cache=None,
        hash=None,
        version=None,
):
    """
    Build the JS and CSS bundle
    """
    # invoke build

    settings = load_config(input).get("config", {})

    minify = cli_or_config(minify, settings, "minify")
    cache = cli_or_config(cache, settings, "cache", default=True)
    hash = cli_or_config(hash, settings, "hash")

    # second argument of build_ is None, so files will be loaded from config.
    # --files can be supplied for the build-js or build-css methods, but not for normal build
    # since it would be too ambiguous to determine whether the files should be compiled as JS or CSS.
    result = []
    try:
        result.append(build_js(c, None, input, verbose, output_js, minify, cache, hash, version))
    except NotFound as e:
        warnings.warn(str(e), source=e)

    try:
        result.append(
            build_css(c, None, input, verbose, output_css, minify, cache, hash, version),
        )
    except NotFound as e:
        warnings.warn(str(e), source=e)

    print(result)
    return result


def XOR(first, *extra):
    result = bool(first)
    for item in extra:
        result ^= bool(item)

    return result


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def assert_chmod_777(c: Context, filepath: str | list[str]):
    filepaths: list[str] = [filepath] if isinstance(filepath, str) else filepath

    for fp in filepaths:
        resp = c.run(f'stat --format "%a  %n" {fp}', hide=True)
        chmod = resp.stdout.split(" ")[0]
        if chmod != 777:
            c.sudo(f"chmod 777 {fp}")


def assert_file_exists(c: Context, db_filepath: str, sql_filepath: str):
    if not os.path.exists(db_filepath):
        # load existing
        c.run(f"sqlite3 {db_filepath} < {sql_filepath}")


def config_setting(key, default=None, config=None, config_path=None):
    if not config:
        config = load_config(config_path or DEFAULT_INPUT_LTS)
    re_settings = _regexify_settings(config)
    var = config.get(key, default)
    return _fill_variables(var, re_settings)


def setup_db(c: invoke.context.Context, config_path=DEFAULT_INPUT_LTS) -> sqlite3.Connection:
    db_path = config_setting("output_db", DEFAULT_ASSETS_DB, config_path=config_path)
    sql_path = config_setting("output_sql", DEFAULT_ASSETS_SQL, config_path=config_path)

    assert_file_exists(c, db_path, sql_path)
    assert_chmod_777(c, [db_path, sql_path])
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
    sql_path = config_setting("output_sql", DEFAULT_ASSETS_SQL)

    sql: invoke.Result = c.run(f"sqlite3 {db_path} .dump", hide=True)

    with open(sql_path, "w", encoding="UTF-8") as f:
        f.write(sql.stdout)


@task()
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
    query = "SELECT COUNT(*) as c FROM bundle_version WHERE filetype = ? AND version = ?;"

    return db.execute(query, (filetype, version)).fetchone()["c"] > 0


def prompt_changelog(db: sqlite3.Connection, filetype: str, version: str):
    load_dotenv()

    query = "SELECT id, changelog FROM bundle_version WHERE filetype = ? AND version = ?;"
    row = db.execute(query, (filetype, version)).fetchone()
    if row["changelog"]:
        print("Changelog already filled in! ", "It can be updated at:")
    else:
        print(f"Please fill in a changelog for this {filetype} publication at: ")

    idx = row["id"]

    hostingdomain = os.environ.get("HOSTINGDOMAIN", "your.domain")

    print(f"https://py4web.{hostingdomain}/lts/manage_versions/edit/{idx}")


@task()
def show_changelog_url(c, filetype, version):
    db = setup_db(c)
    prompt_changelog(db, filetype, version)


def confirm(prompt: str, force=False) -> bool:
    return force or truthy(input(prompt))


def _decide_new_version(major: int, minor: int, patch: int, previous: dict, version: str):
    if not any((version, major, minor, patch)):
        print("Previous version is:", previous.get("version", "0.0.0"))
        version = input("Which version would you like to publish? ")
    elif not XOR(version, major, minor, patch):
        # error on more than one:
        raise ValueError("Please specify only one of --version, --major, --minor or --patch")
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
        raise ValueError(f"Invalid version {version}. Please use the format major.major.patch (e.g. 3.5.0)")
    major, minor, patch = (
        int(groups[0][0]),
        int(groups[0][1].strip(".") or 0),
        int(groups[0][2].strip(".") or 0),
    )
    version = f"{major}.{minor}.{patch}"
    return major, minor, patch, version


def calculate_file_hash(c: Context, filename: str):
    return c.run(f"sha1sum {filename}", hide=True).stdout.split(" ")[0]


@task()
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

    major, minor, patch, version = _decide_new_version(major, minor, patch, previous, version)

    if js and version_exists(db, "js", version):
        print(f"JS Version {version} already exists!")
        js = confirm("Are you sure you want to overwrite it? ", force)

    if css and version_exists(db, "css", version):
        print(f"CSS Version {version} already exists!")
        css = confirm("Are you sure you want to overwrite it? ", force)

    output_js = output_css = None
    if js and css:
        output_js, output_css = build(c, input=config, version=version, verbose=verbose)
    elif js:
        output_js = build_js(c, input=config, version=version, verbose=verbose)
    elif css:
        output_css = build_css(c, input=config, version=version, verbose=verbose)
    # else: no build

    if output_js:
        go, hash, filename, file_contents = _should_publish(c, force, output_js, previous.get("hash"), "JS")

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
        previous_css = get_latest_version(db, "css")
        go, hash, filename, file_contents = _should_publish(c, force, output_css, previous_css.get("hash"), "CSS")

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

    rmtree(TEMP_OUTPUT_DIR)

    # after publish: run `up -s py4web` so the bjoerns are all updated
    c.run("inv up -s py4web")


def _should_publish(c: Context, force: bool, output_path: str, previous_hash: str, type: typing.Literal["JS", "CSS"]):
    file_hash = calculate_file_hash(c, output_path)
    if file_hash == previous_hash:
        print(f"{type} hash matches previous version.")
        go = confirm("Are you sure you want to release a new version? ", force)
    else:
        go = True
    if not go:
        return False, None, None, None

    # if go:

    with open(output_path, "r", encoding="UTF-8") as f:
        file_contents = f.read()

    filename = output_path.split("/")[-1]

    return True, file_hash, filename, file_contents


@task(name="list")
def list_versions(c):
    db = setup_db(c)
    for row in db.execute(
            "SELECT filetype, version FROM bundle_version ORDER BY major DESC, minor DESC, patch DESC"
    ).fetchall():
        print(row)


@task()
def reset(c):
    db = setup_db(c)
    if not confirm("Are you sure you want to reset the versions database? "):
        print("Wise.")
        return

    # noinspection SqlWithoutWhere
    # ^ that's the whole point of 'reset'.
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
