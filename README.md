# edwh-bundler-plugin

[![PyPI - Version](https://img.shields.io/pypi/v/edwh-bundler-plugin.svg)](https://pypi.org/project/edwh-bundler-plugin)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/edwh-bundler-plugin.svg)](https://pypi.org/project/edwh-bundler-plugin)

-----

EDWH Python-only bundler for static assets (JS and CSS).
Try it out with an example:
`edwh bundle.build --input example.yaml -v`

**Table of Contents**

- [Installation](#installation)
- [Usage](#usage)
- [License](#license)
- [Changelog](#changelog)

## Installation

```console
pip install edwh-bundler-plugin
```

But probably you want to install the whole edwh package:

```console
pipx install edwh[bundler]
# or
pipx install edwh[plugins,omgeving]
```

## Usage

After setting up a correct `bundle.yaml`, simply run `edwh bundle.build' to build your JS and CSS bundles!

### JS

Since this package is Python-only, it can't do any of the more fancy stuff that nodejs-based bundlers can.
For simplistic purposes however, where the bundler is embedded in some other Python workflow, this package could be
useful.
It can combine JS files (in a naive way) and minify them using [rjsmin](https://pypi.org/project/rjsmin/).
In addition to this, it can also add [_hyperscript](https://hyperscript.org) to the bundle and 'minify' it (by removing
comments and newlines).
These JS and _hs files can be fetched from a remote URL or loaded from a file path.
CSS files can be also included in the bundle, and will be inlined as `<style>`s in the page's head.
The same goes for HTML files, which will be appended to the end of the `<body>` (useful for `<template>`s).
Typescript files can now also be bundled, using [dukpy](https://pypi.org/project/dukpy/).
Basic imports should work thanks to a custom resolver, but this hasn't been tested with anything complex such
as `node_modules` yet.

### CSS

(S)CSS can also be bundled (naively) and minified (using [libsass](https://pypi.org/project/libsass/)) and can also be
loaded from either remote or local files.
A scope can also be defined and using sass all styles in the file will be prefixed with the provided selector.

### Configuration

A bundle with a specific configuration can be built with: `edwh bundle.build --input some.yaml`.
If no `--input` is defined, `bundle.yaml` in the current directory will be used.
This yaml can contain these keys:

```yaml
js:
  - ... # list of resources
css:
  - ... # list of resources
config:
  minify: bool  # should the outputs be minified?
  cache: bool   # should CDN resources be cached locally?
  hash: bool    # should a .hash file be created in addition to the output files?
  # - and _ are interchangable in variable names:
  version: 1.2.3 # default: 'latest'
  output-css: static/css/$filename-$version.css # where should the css be stored?
  output_js: static/js/$filename-$version.js    # where should the js be stored?
  scss-variables: # will be available for all .scss files
    - variables.toml # from a toml, json, yaml file
    - https://my.site/api/styles.json?secret=${AUTH_TOKEN} # or from a remote file


  # extra variables, available via $varname (e.g. see output-css)
  filename: bundled


```

`js` contains input files for the JS bundle, `css` input files for the CSS bundle and `config` contains general
configuration options.

#### JS

The JS part of the configuration has the following options:

```yaml
js:
  - https://some.cdn/mypackage.js   # remote JS file
  - ./path/to/file.js               # local JS file
  - https://some.cdn/mypackage._hs  # remote hyperscript file
  - /path/to/file._hs               # local hyperscript file
  - >
    // inline JavaScript (requires starting with a comment so the bundler can detect it)
    console.log("inline multiline js")
  - _hyperscript("log 'inline hyperscript'") # if you've included 'hyperscript' from a file or cdn above! Tip: alias `_ = _hyperscript` for ease of use)
  - https://some.cdn/mystyles.css  # remote CSS (will be inlined in the head)
  - path/to/styles.css             # local CSS (will be inlined in the head)
  - path/to/template.html          # will be added to the end of the DOM 
```

SCSS is not supported in this section.

#### CSS

```yaml
css:
  - https://some.cdn/mystyles.scss # remote SCSS
  - https://some.cdn/mystyles.css  # remote CSS
  - path/to/styles.scss            # local SCSS
  - path/to/styles.css             # local CSS
  - file: url_or_path.css          # dict with options: 
    scope: '#my-style-scope'       # every rule in this file will be scoped
  - file: url_or_path.css          # transform a .css file with sass
    scss: 1
  - |
    // inline scss or css
  - file: url_or_path.scss
    variables: # extra SCSS variables
      primary: "#000033"
      secondary: "green"
      width: "20px"
  - file: url_or_path.scss
    variables: # one or more files with variables:
      - variables.toml                                       # local configuration file (toml, yaml, json, ...)
      - https://my.site/api/settings.json?secret=${APIKEY}   # remote config file with .env setting for auth 
```

SCSS will be applied if the file extension is `sass` or `scss` or if the scss option is true.
SCSS will be disabled for files with that extension if the config option is set to false.
The `scope` selector can be any CSS selector (e.g. `#id`, `.class`, `element` etc.)
The `scope` and `scss` options do not work together, as `scope` always uses scss to add the parent selector.

### Config

The config options from the config file can be overridden on the command line with the corresponding flags (
see `edwh bundle.build -h`).
Booleans such as `minify` and `cache` can start with 1, 'y' or 't' (e.g. be 1, 'y', 'Y', 'Yes', 'yup', 'true' or
something similar) to be truthy.
Anything else is considered falsey. The flag `--stdout` can only be used from the commandline, and will yield the result
to stdout instead of an output file (overrides `--output`)

### Other commands

`edwh bundle.build-js` or `edwh bundle.build-css` can be used to only build one output file (.js or .css respectively).
These commands can be used with multiple `--file`s as arguments. The rest of the options are the same as the
regular `build`.

### Integrated use as an API

Instead of using the cli, this package can also be integrated in other Python scripts.

```python
# individual helpers
from edwh_bundler_plugin import extract_contents_for_js
from edwh_bundler_plugin import extract_contents_for_css

extract_contents_for_css("https://some.cdn/mystyles.css")  # a {color: red}
extract_contents_for_js("https://some.cdn/mystyles.css")  # document.head.innerHTML += `<style>a {color: red}</style>`
extract_contents_for_css(
    {'file': "https://some.cdn/assets/css/mystyles.css", 'scope': '#mydiv'})  # #mydiv a {color: red}

# bundling multiple files
from edwh_bundler_plugin import bundle_js, bundle_css

inline_js = """// should start with a comment
_ = _hyperscript
"""
bundle_js(["https://unpkg.com/hyperscript.org", inline_js, "_(`log 'inline _hs'`)"])  # returns a string by default
bundle_css(
    ["https://some.cdn/package.css", {'file': "./mystyles.css", 'scope': '#mydiv'}])  # returns a string by default
```

## License

`edwh-bundler-plugin` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## Changelog

[See CHANGELOG.md](CHANGELOG.md)