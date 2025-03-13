from __future__ import annotations

import datetime as dt
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
from shutil import rmtree
from typing import Optional

import edwh
import tomlkit
import yaml
from dotenv import load_dotenv
from edwh import improved_task as task
from invoke import Context

from .css import extract_contents_for_css
from .js import extract_contents_for_js
from .shared import truthy


def now():
    """
    Backwards and forwards compatible way to get the current datetime in UTC.
    """
    try:
        # 3.12
        return datetime.now(dt.UTC)
    except AttributeError:
        # 3.10
        return datetime.utcnow()


# prgram is created in __init__

# defaults/consts
DEFAULT_INPUT = "bundle.yaml"
DEFAULT_INPUT_LTS = "bundle-lts.yaml"
DEFAULT_OUTPUT_JS = "bundle.js"
DEFAULT_OUTPUT_CSS = "bundle.css"

TMP = Path("/tmp")

TEMP_OUTPUT_DIR = TMP / "bundle-build"
TEMP_OUTPUT = ".bundle_tmp"
DEFAULT_ASSETS_DB = TMP / "lts_assets.db"
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
        data = yaml.load(f, yaml.SafeLoader)

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


def _load_config_pyproject():
    data = _load_config_toml("pyproject.toml", key="tool.edwh.bundler")
    data = data or _load_config_toml("pyproject.toml", key="tool.edwh.bundle")
    return "pyproject.toml", data


def _load_config(fname: str = DEFAULT_INPUT, strict=False) -> tuple[str, dict]:
    """
    Load yaml config from file name, default to empty or error if strict
    """
    if os.path.exists(fname) and fname.endswith((".yml", ".yaml")):
        # load default or user-defined yaml
        return fname, _load_config_yaml(fname)
    elif os.path.exists(fname) and fname.endswith(".toml"):
        # load user defined toml
        if fname == "pyproject.toml":
            return _load_config_pyproject()
        else:
            return fname, _load_config_toml(fname)
    elif fname == DEFAULT_INPUT and (altname := DEFAULT_INPUT.replace(".yaml", ".toml")) and os.path.exists(altname):
        # try bundle.toml
        return altname, _load_config_toml(altname)
    elif os.path.exists("pyproject.toml"):
        # look in pyproject
        return _load_config_pyproject()
    elif strict:
        # err !
        raise FileNotFoundError(fname)
    else:
        # fallback to empty config
        return "", {}


def load_config(fname: str = DEFAULT_INPUT, strict=True, verbose=False) -> dict[str, dict]:
    """
    Returns a dict of {name: config dict} where 'name' will be _ if bundle.yaml contains only one config.
    """
    file_used, data = _load_config(fname, strict=strict)

    if not data and strict:
        # empty config!
        raise ValueError(f"Config data found for `{file_used}` was empty!")
    elif verbose:
        print(f"Using config: {file_used}", file=sys.stderr)

    if data.get("configurations"):
        return data["configurations"]
    else:
        return {"_": data} if data else {}


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
    is_bool: bool = True,
    default: typing.Any = None,
) -> bool | typing.Any:
    """
    Get a setting from either the config yaml or the cli (used to override config)
    cli > config > default

    Args:
        value: the value from cli, will override config if anything other than None
        config: the 'config' section of the config yaml
        key: config key to look in (under the 'config' section)
        is_bool: should the result always be a boolean? Useful cli arguments such as --cache y,
                     but should probably be False for named arguments such as --filename ...
        default: if the option can be found in neither the cli arguments or the config file, what should the value be?
    """
    return (truthy(value) if is_bool else value) if value is not None else config.get(key, default)


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

    if "$" not in str(setting):
        return setting

    for reg, repl in variables.items():
        setting = reg.sub(str(repl), str(setting))

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


class FileHandler(typing.Protocol):
    # bijv. extract_contents_for_js, extract_contents_for_css
    def __call__(
        self, file: dict | str, settings: dict, cache: bool = True, minify: bool = True, verbose: bool = False
    ) -> str: ...


def _handle_files(
    files: list,
    callback: FileHandler,
    output: str | typing.IO,
    verbose: bool,
    use_cache: bool,
    minify: bool,
    store_hash: bool,
    settings: dict,
):
    """
    Execute 'callback' (js or css specific) on all 'files'

    Args:
        files: list of files from the 'css' or 'js' section in the config yaml
        callback: method to execute to gather and process file contents
        output: final output file path to write to
        verbose: logs some info to stderr
        use_cache: use cache for online resources?
        minify: minify file contents?
        settings: other configuration options
    """
    re_settings = _regexify_settings(settings)

    output = _fill_variables(output, re_settings)
    files = [_fill_variables(f, re_settings) for f in files]

    if verbose:
        print(
            f"Building {callback.__name__.split('_')[-1]} [verbose]\n{output=}\n",
            f"{minify=}\n",
            f"{use_cache=}\n",
            f"{store_hash=}\n",
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

        output_dir = TEMP_OUTPUT_DIR / ts
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / output_filename

    with start_buffer(output) as bufferf:
        for inf in files:
            if not inf:
                # empty - skip
                continue

            if not minify:
                src = str(inf).replace("/*", "//").replace("*/", "")
                bufferf.write(f"/* SOURCE: {src} */\n")

            res = callback(inf, settings, cache=use_cache, minify=minify, verbose=verbose)

            bufferf.write(res + "\n")
            if verbose:
                print(f"Handled {inf}", file=sys.stderr)

    if not isinstance(output, io.IOBase):
        os.rename(bufferf.name, output)
    if verbose:
        print(f"Written final bundle to {output}", file=sys.stderr)

    if store_hash:
        hash_file = store_file_hash(output)

        print((output, hash_file))
        return output, hash_file

    print(output)
    return output


@task(iterable=["files"])
def build_js(
    _,
    files: list[str] = None,
    config: str = DEFAULT_INPUT,
    verbose: bool = False,
    # overrule config:
    output: str | typing.IO = None,  # DEFAULT_OUTPUT_JS
    minify: bool = None,
    use_cache: bool = None,
    save_hash: bool = None,
    version: str = None,
    stdout: bool = False,  # overrides output
    name: Optional[str] = None,
):
    """
    Build the JS bundle (cli only)
    """
    configs = load_config(config)

    results = {}
    for config_name, config in configs.items():
        if name and config_name != name:
            continue
        if verbose:
            print(f"Starting on JS for `{config_name}`")

        files = files or config.get("js")

        if not files:
            raise NotFound("js")

        settings = config.get("config", {})

        settings["version"] = cli_or_config(version, settings, "version", is_bool=False, default="latest")

        results[config_name] = _handle_files(
            files,
            extract_contents_for_js,
            verbose=verbose,
            output=(
                sys.stdout
                if stdout
                else cli_or_config(output, settings, "output_js", is_bool=False) or DEFAULT_OUTPUT_JS
            ),
            use_cache=cli_or_config(use_cache, settings, "cache", default=True),
            store_hash=cli_or_config(save_hash, settings, "hash"),
            minify=cli_or_config(minify, settings, "minify"),
            settings=settings,
        )

    return results


# import version:
def bundle_js(
    files: list[str] = None,
    verbose: bool = False,
    output: str | typing.IO = None,
    minify: bool = True,
    use_cache: bool = True,
    save_hash: bool = False,
    **settings,
) -> Optional[str]:
    """
    Importable version of 'build_js'.
    If output is left as None, the bundled code will be returned as a string

    Args:
        files: list of things to bundle
        verbose: print some info to stderr?
        output: filepath or IO to write to
        minify: minify files?
        use_cache: save external files to disk for re-use?
        save_hash: store an additional .hash file after bundling?

    Returns: bundle of JS
    """
    if output is None:
        output = io.StringIO()

    _handle_files(
        files,
        extract_contents_for_js,
        output,
        verbose=verbose,
        use_cache=use_cache,
        store_hash=save_hash,
        minify=minify,
        settings=settings,
    )

    if not isinstance(output, io.StringIO):
        return output

    output.seek(0)
    return output.read()


@dataclass
class NotFound(Exception):
    """
    Raised when specified files could not be found.
    """

    type: typing.Literal["js", "css"]

    def __str__(self):
        return f"Please specify either --files or the {self.type} key in a config yaml (e.g. bundle.yaml)"


@task(
    iterable=["files"],
)
def build_css(
    _,
    files: list[str] = None,
    config: str = DEFAULT_INPUT,
    verbose: bool = False,
    # overrule config:
    output: str | typing.IO = None,  # DEFAULT_OUTPUT_CSS
    minify: bool = None,
    use_cache: bool = None,
    save_hash: bool = None,
    version: str = None,
    stdout: bool = False,  # overrides output
    name: Optional[str] = None,
):
    """
    Build the CSS bundle (cli only)
    """
    configs = load_config(config)

    result = {}
    for config_name, config in configs.items():
        if name and config_name != name:
            continue
        if verbose:
            print(f"Starting on JS for `{config_name}`")

        settings = config.get("config", {})

        settings["version"] = cli_or_config(version, settings, "version", is_bool=False, default="latest")

        if not (files := (files or config.get("css"))):
            raise NotFound("css")

        result[config_name] = _handle_files(
            files,
            extract_contents_for_css,
            verbose=verbose,
            output=(
                sys.stdout
                if stdout
                else cli_or_config(output, settings, "output_css", is_bool=False) or DEFAULT_OUTPUT_CSS
            ),
            use_cache=cli_or_config(use_cache, settings, "cache", default=True),
            store_hash=cli_or_config(save_hash, settings, "hash"),
            minify=cli_or_config(minify, settings, "minify"),
            settings=settings,
        )

    return result


# import version:
def bundle_css(
    files: list[str] = None,
    verbose: bool = False,
    output: str | typing.IO = None,
    minify: bool = True,
    use_cache: bool = True,
    save_hash: bool = False,
    **settings,
) -> Optional[str]:
    """
    Importable version of 'build_css'.
    If output is left as None, the bundled code will be returned as a string

    Args:
        files: list of things to bundle
        verbose: print some info to stderr?
        output: filepath or IO to write to
        minify: minify files?
        use_cache: save external files to disk for re-use?
        save_hash: should an additional .hash file be stored after generating the bundle?

    Returns: bundle of CSS
    """
    if output is None:
        output = io.StringIO()

    _handle_files(
        files,
        extract_contents_for_css,
        output,
        verbose=verbose,
        use_cache=use_cache,
        store_hash=save_hash,
        minify=minify,
        settings=settings,
    )

    if not isinstance(output, io.StringIO):
        return output

    output.seek(0)
    return output.read()


@task(iterable=["files"], hookable=False)
def build(
    c,
    config: str = DEFAULT_INPUT,
    verbose: bool = False,
    # defaults from config, can be overwritten:
    output_js: str = None,  # DEFAULT_OUTPUT_JS
    output_css: str = None,  # DEFAULT_OUTPUT_CSS
    minify: bool = None,
    use_cache: bool = None,
    save_hash: bool = None,
    version: str = None,
    name: Optional[str] = None,
):
    """
    Build the JS and CSS bundle
    """

    configs = load_config(config, verbose=True)

    result = []

    for config_name, config_dict in configs.items():
        if name and config_name != name:
            continue

        settings = config_dict.get("config", {})

        do_minify = cli_or_config(minify, settings, "minify")
        do_use_cache = cli_or_config(use_cache, settings, "cache", default=True)
        do_save_hash = cli_or_config(save_hash, settings, "hash")

        # second argument of build_ is None, so files will be loaded from config.
        # --files can be supplied for the build-js or build-css methods, but not for normal build
        # since it would be too ambiguous to determine whether the files should be compiled as JS or CSS.
        try:
            result.append(
                build_js(
                    c,
                    None,
                    config,
                    verbose,
                    output_js,
                    do_minify,
                    do_use_cache,
                    do_save_hash,
                    version,
                    stdout=False,
                    name=config_name,
                )
            )
        except NotFound as e:
            warnings.warn(str(e), source=e)

        try:
            result.append(
                build_css(
                    c,
                    None,
                    config,
                    verbose,
                    output_css,
                    do_minify,
                    do_use_cache,
                    do_save_hash,
                    version,
                    stdout=False,
                    name=config_name,
                ),
            )
        except NotFound as e:
            warnings.warn(str(e), source=e)

    return result


def XOR(first, *extra):
    """
    Exclusive or: only returns True when exactly one of the arguments is Truthy.
    """
    result = bool(first)
    for item in extra:
        result ^= bool(item)

    return result


def dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row):
    """
    Return a dict of {column name: value} for an sqlite row.
    """
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def assert_chmod_777(c: Context, filepath: str | list[str]):
    filepaths: list[str] = [filepath] if isinstance(filepath, str) else filepath

    # filepaths with incorrect chmod are collected,
    #  so require_sudo only has to be executed if any chmod has to happen
    #  skipping annoying sudo prompts when sudo is not actually used
    todos = []
    for fp in filepaths:
        resp = c.run(f'stat --format "%a  %n" {fp}', hide=True)
        chmod = resp.stdout.split(" ")[0]
        if chmod != "777":
            todos.append(fp)

    if todos:
        edwh.tasks.require_sudo(c)  # can't chmod without sudo
    for todo in todos:
        c.sudo(f"chmod 777 {todo}")


def create_bundle_version_table():
    sql = """
    CREATE TABLE IF NOT EXISTS "bundle_version"(
        "id" INTEGER PRIMARY KEY AUTOINCREMENT,
        "filetype" CHAR(512),
        "version" CHAR(512),
        "filename" CHAR(512),
        "major" INTEGER,
        "minor" INTEGER,
        "patch" INTEGER,
        "hash" CHAR(512),
        "created_at" TIMESTAMP,
        "changelog" TEXT,
        "contents" TEXT
    );  
    """
    return sql


def assert_file_exists(c: Context, db_file: str, sql_file: str):
    db_filepath = Path(db_file)
    sql_filepath = Path(sql_file)

    if not db_filepath.parent.exists():
        db_filepath.parent.mkdir(parents=True)
    if not sql_filepath.parent.exists():
        sql_filepath.parent.mkdir(parents=True)

    if not sql_filepath.exists() and not db_filepath.exists():
        # db nor sql exist -> start from scratch
        sql_filepath.touch()
        db_filepath.touch()
        with sqlite3.connect(db_file) as con:
            con.execute(create_bundle_version_table())
            con.commit()
    elif not sql_filepath.exists():
        # db exists, sql doesn't
        sql_filepath.touch()
    elif not db_filepath.exists():
        # load existing
        c.run(f"sqlite3 {db_filepath} < {sql_filepath}")


def config_setting(key, default=None, config=None, config_path=None, config_name="_"):
    if not config:
        config = load_config(config_path or DEFAULT_INPUT_LTS)
    re_settings = _regexify_settings(config)

    if config_name in config:
        config = config[config_name]

    var = config.get(key) or config.get("config", {}).get(key, default)
    return _fill_variables(var, re_settings)


def setup_db(c: Context, config_path=DEFAULT_INPUT_LTS) -> sqlite3.Connection:
    """
    note: this does NOT work with multiple configurations in one yaml yet!!
    """
    db_path = config_setting("output_db", DEFAULT_ASSETS_DB, config_path=config_path)
    sql_path = config_setting("output_sql", DEFAULT_ASSETS_SQL, config_path=config_path)

    assert_file_exists(c, db_path, sql_path)
    assert_chmod_777(c, [db_path, sql_path])
    con = sqlite3.connect(db_path)
    con.row_factory = dict_factory
    return con


def get_latest_version(db: sqlite3.Connection, filetype: str = None) -> dict:
    query = ["SELECT *", "FROM bundle_version"]

    if filetype:
        query.append(f"WHERE filetype = '{filetype}'")

    query.append("ORDER BY major DESC, minor DESC, patch DESC")

    cur = db.execute(" ".join(query))
    return cur.fetchone() or {}


def _update_assets_sql(c: Context, config: str = None):
    """
    ... todo docs ...
    Should be done after each db.commit()
    """
    # for line in db.iterdump():
    db_path = config_setting("output_db", DEFAULT_ASSETS_DB, config_path=config)
    sql_path = config_setting("output_sql", DEFAULT_ASSETS_SQL, config_path=config)

    c.run(f"sqlite3 {db_path} .dump > {sql_path}", hide=True)


@task()
def update_assets_sql(c, config: str = None):
    # db = setup_db(c)
    _update_assets_sql(c, config)


def insert_version(c: Context, db: sqlite3.Connection, values: dict, config: str = None):
    columns = ", ".join(values.keys())
    placeholders = ":" + ", :".join(values.keys())

    query = "INSERT INTO bundle_version ({}) VALUES ({})"

    db.execute(query.format(columns, placeholders), values)
    db.commit()
    _update_assets_sql(c, config)


def version_exists(db: sqlite3.Connection, filetype: str, version: str):
    query = "SELECT COUNT(*) AS c FROM bundle_version WHERE filetype = ? AND version = ?;"

    return db.execute(query, (filetype, version)).fetchone()["c"] > 0


def prompt_changelog(db: sqlite3.Connection, filename: str, filetype: str, version: str):
    load_dotenv()

    query = "SELECT id, changelog FROM bundle_version WHERE filename = ? AND filetype = ? AND version = ?;"
    row = db.execute(query, (filename, filetype, version)).fetchone()
    if row["changelog"]:
        print("Changelog already filled in! ", "It can be updated at:")
    else:
        print(f"Please fill in a changelog for this {filetype} publication at: ")

    idx = row["id"]

    hostingdomain = os.environ.get("HOSTINGDOMAIN", "your.domain")

    print(f"https://py4web.{hostingdomain}/lts/manage_versions/edit/{idx}")


@task()
def show_changelog_url(c, filename, filetype, version, config=DEFAULT_INPUT_LTS):
    """
    note: this does NOT work with multiple configurations in one yaml yet!!
    """
    db = setup_db(c, config)
    prompt_changelog(db, filename, filetype, version)


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


def calculate_file_hash(c: Context, filename: str | Path):
    return c.run(f"sha1sum {filename}", hide=True).stdout.split(" ")[0]


@task()
def publish(
    c: Context,
    version: str = None,
    config: str = DEFAULT_INPUT_LTS,  # note: goes BEFORE 'css' so this one claims -c !
    major: bool = False,
    minor: bool = False,
    patch: bool = False,
    js: bool = True,
    css: bool = True,
    verbose: bool = False,
    force: bool = False,
):
    """
    note: this does NOT work with multiple configurations in one yaml yet!!
    """
    load_dotenv()
    db = setup_db(c, config)
    previous = get_latest_version(db, "js")

    TEMP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    major, minor, patch, version = _decide_new_version(major, minor, patch, previous, version)

    if js and version_exists(db, "js", version):
        print(f"JS Version {version} already exists!")
        js = confirm("Are you sure you want to overwrite it? ", force)

    if css and version_exists(db, "css", version):
        print(f"CSS Version {version} already exists!")
        css = confirm("Are you sure you want to overwrite it? ", force)

    output_js = {}
    if js:
        output_js = build_js(c, config=config, version=version, verbose=verbose)

    output_css = {}
    if css:
        output_css = build_css(c, config=config, version=version, verbose=verbose)

    for key, js_file in output_js.items():
        if isinstance(js_file, tuple):
            # (file, hash)
            js_file = js_file[0]

        go, file_hash, filename, file_contents = _should_publish(c, force, js_file, previous.get("hash"), "JS")

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
                    "hash": file_hash,
                    "created_at": now(),
                    "changelog": "",
                    "contents": file_contents,
                },
                config=config,
            )
            print(f"{filename} (JS) version {version} published.")
            prompt_changelog(db, filename, "js", version)

    for key, css_file in output_css.items():
        if isinstance(css_file, tuple):
            # (file, hash)
            css_file = css_file[0]

        previous_css = get_latest_version(db, "css")
        go, file_hash, filename, file_contents = _should_publish(c, force, css_file, previous_css.get("hash"), "CSS")

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
                    "hash": file_hash,
                    "created_at": now(),
                    "changelog": "",
                    "contents": file_contents,
                },
                config=config,
            )
            print(f"{filename} (CSS) version {version} published.")
            prompt_changelog(db, filename, "css", version)

    rmtree(TEMP_OUTPUT_DIR)


def _should_publish(
    c: Context, force: bool, output_filename: str | Path, previous_hash: str, filetype: typing.Literal["JS", "CSS"]
):
    output_path = Path(output_filename)

    file_hash = calculate_file_hash(c, output_path)
    if file_hash == previous_hash:
        print(f"{filetype} hash matches previous version.")
        go = confirm("Are you sure you want to release a new version? [yN] ", force)
    else:
        go = True
    if not go:
        return False, None, None, None

    # if go:
    file_contents = output_path.read_text(encoding="UTF-8")

    return True, file_hash, output_path.name, file_contents


@task(name="list")
def list_versions(c, config=DEFAULT_INPUT_LTS):
    """
    note: this does NOT work with multiple configurations in one yaml yet!!
    """
    db = setup_db(c, config)
    for row in db.execute(
        "SELECT filetype, version FROM bundle_version ORDER BY major DESC, minor DESC, patch DESC"
    ).fetchall():
        print(row)


@task()
def reset(c, config=DEFAULT_INPUT_LTS):
    """
    note: this does NOT work with multiple configurations in one yaml yet!!
    """
    db = setup_db(c, config)

    if not confirm("Are you sure you want to reset the versions database? [yN]"):
        print("Wise.")
        return

    # noinspection SqlWithoutWhere
    # ^ that's the whole point of 'reset'.
    db.execute("DELETE FROM bundle_version;")
    db.commit()
    _update_assets_sql(c, config)

    assert db.execute("SELECT COUNT(*) AS c FROM bundle_version;").fetchone()["c"] == 0
