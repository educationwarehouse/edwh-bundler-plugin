from pathlib import Path

import quickjs

from edwh_bundler_plugin import bundle_js


def test_typescript_loader_is_safe_to_load_from_multiple_bundles(tmp_path: Path) -> None:
    """Two independently built TypeScript bundles can share a page."""
    first_source = tmp_path / "first.ts"
    first_source.write_text("export const first = 'first';")
    second_source = tmp_path / "second.ts"
    second_source.write_text("export const second = 'second';")

    first_bundle = bundle_js([str(first_source)], use_cache=False)
    second_bundle = bundle_js([str(second_source)], use_cache=False)

    page_javascript = first_bundle + second_bundle

    browser = quickjs.Context()
    browser.eval("var window = {};")
    browser.eval(page_javascript)

    assert browser.eval("window.first") == "first"
    assert browser.eval("window.second") == "second"
