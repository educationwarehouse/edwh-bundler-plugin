import os

from src.edwh_bundler_plugin.bundler_plugin import replace_placeholders


def test_replace_placeholders_env():
    os.environ["EXAMPLE"] = "yay"

    assert (
        replace_placeholders("1 ${EXAMPLE:-no} ${TWOXAMPLE:-yes} ${exclude} $exclude")
        == replace_placeholders("1 $EXAMPLE ${TWOXAMPLE-yes} ${exclude} $exclude")
        == "1 yay yes ${exclude} $exclude"
    )


def test_replace_placeholders_js():
    os.environ["EXAMPLE"] = "yay"

    js_str = """
    const x = '${EXAMPLE:-no}'
    const y = `${x}`
    """

    assert (
        replace_placeholders(js_str)
        == """
    const x = 'yay'
    const y = `${x}`
    """
    )
