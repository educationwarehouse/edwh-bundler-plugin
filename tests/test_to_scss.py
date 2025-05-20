import textwrap

import sassquatch

from src.edwh_bundler_plugin.css import convert_to_css_variables


def test_converter():
    assert convert_to_css_variables("css") == ""

    css_code = convert_to_css_variables(
        "css",
        font=["Arial", "sans-serif"],
        color="#8504bd",
        font_size=16,
        nothing=None,
        maybe=False,
        mapping={
            "primary-color": "rgba(255, 0, 0, 0.5)",
            "secondary-color": "hsl(121, 100%, 50%)",
        },
    )

    assert ":root {" in css_code
    assert "--color: #8504bd" in css_code
    assert "mapping" not in css_code

    scss_code = convert_to_css_variables(
        "scss",
        font=["Arial", "sans-serif"],
        color="#8504bd",
        font_size=16,
        nothing=None,
        maybe=False,
        mapping={
            "primary-color": "rgba(255, 0, 0, 0.5)",
            "secondary-color": "hsl(121, 100%, 50%)",
        },
    )

    sass_code = convert_to_css_variables(
        "sass",
        font=["Arial", "sans-serif"],
        color="#8504bd",
        font_size=16,
        nothing=None,
        maybe=False,
        mapping={
            "primary-color": "rgba(255, 0, 0, 0.5)",
            "secondary-color": "hsl(121, 100%, 50%)",
        },
    )

    scss_code += """
            h1 {
              font-family: $font;
              color: $color;
              font-size: $font-size;
              margin: $nothing;

              @if $maybe {
                display: none;
              }

              // map
              @each $key, $value in $mapping { // Corrected variable name to $mapping
                &.#{$key}-container {
                  .#{$key} {
                    background-color: $value;
                  }
                }
              }
            }
        """

    sass_code += textwrap.dedent(
        """
            h1
              font-family: $font
              color: $color
              font-size: $font-size
              margin: $nothing

              @if $maybe
                display: none

              // map
              @each $key, $value in $mapping
                &.#{$key}-container
                  .#{$key}
                    background-color: $value
        """
    )

    css = sassquatch.compile(string=scss_code, style="expanded")

    print(css)

    assert css
    assert "display: none" not in css

    css2 = sassquatch.compile(string=sass_code, style="expanded", indented=True)
    assert "\n" in css2.strip()

    assert css == css2

    css_min = sassquatch.compile(string=scss_code, style="compressed")
    assert "\n" not in css_min.strip()
