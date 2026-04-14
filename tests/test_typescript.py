from edwh_bundler_plugin.js import extract_contents_for_js, extract_contents_typescript, transpile_typescript


def test_transpile_typescript_supports_optional_chaining():
    ts_code = """
const x: number = 123;
x.test?.tost;
"""
    js_code = transpile_typescript(ts_code)
    assert "const x = 123;" in js_code
    assert "x.test?.tost" in js_code


def test_extract_contents_typescript_resolves_dependencies(tmp_path):
    main = tmp_path / "main.ts"
    shared = tmp_path / "shared.ts"
    main.write_text("import { value } from './shared'; console.log(value?.toString());")
    shared.write_text("export const value: number = 1;")

    output = extract_contents_typescript(main, {})

    assert "const System = {" in output
    assert "System.register('./shared'," in output
    assert "System.register('__main__'," in output
    assert "./shared" in output


def test_extract_contents_for_js_accepts_typescript_file(tmp_path):
    path = tmp_path / "entry.ts"
    path.write_text("export const v: number = 1;")

    output = extract_contents_for_js(str(path), settings={}, minify=False)

    assert "System.register('__main__'" in output
    assert 'exports_1("v", v = 1);' in output
