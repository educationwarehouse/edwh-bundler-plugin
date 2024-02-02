import textwrap

import sass

from src.edwh_bundler_plugin.css import convert_to_sass_variables


def test_converter():
    scss_code = convert_to_sass_variables(
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

    sass_code = convert_to_sass_variables(
        font=["Arial", "sans-serif"],
        color="#8504bd",
        font_size=16,
        nothing=None,
        maybe=False,
        mapping={
            "primary-color": "rgba(255, 0, 0, 0.5)",
            "secondary-color": "hsl(121, 100%, 50%)",
        },
        _language="sass",
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

    css = sass.compile(string=scss_code, output_style="expanded")

    print(css)

    assert css
    assert "display: none" not in css

    css2 = sass.compile(string=sass_code, output_style="expanded", indented=True)

    assert css == css2
