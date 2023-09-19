# Changelog

<!--next-version-placeholder-->

## v0.2.2 (2023-09-19)
### Performance
* **sass:** Re-introduced JIT imports to slightly speed up plugin ([`4433ae9`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/4433ae9cb3075e0ceb8b06ca7b09845b960aac89))

## v0.2.1 (2023-09-19)
### Performance
* **httpx:** Replaced httpx with requests because the import was very slow (150ms) ([`f51d1e9`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/f51d1e9dfe89bd6caa4ac782f09414d63beaa151))

## v0.2.0 (2023-07-11)
### Feature
* Support .toml and pyproject.toml with key tool.edwh.bundle ([`2ef6196`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/2ef6196264b7703cb73c28ce0bb56ce4bb498447))
* Allow `hash (bool)` option in config to store a .hash file of generated bundles ([`81d7720`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/81d7720ef6b50626542730ba511ecd3463e477ef))
* Made config a little more flexible by allowing '-' as well as '_' as a word seperator in keys ([`8a20fd8`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/8a20fd83e02e11153d36c623d8b214e0aa5f95b1))

## v0.1.7 (2023-06-29)
### Fix
* Don't crash if the output folder doesn't exist yet ([`630342d`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/630342dd149a0120cd003c6c09d7f1238797d3a5))

## v0.1.6 (2023-05-31)


## v0.1.5 (2023-04-17)


## v0.1.4 (2023-04-17)
### Fix
* **project:** Remove theoretical support for Python versions below 3.10 since that has never worked ([`daa3e39`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/daa3e39abe7627a09c93ccfeb42e164612c14b6c))

## v0.1.3 (2023-04-17)
### Fix
* **publish:** .db file moved to tmp ([`11613ca`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/11613caab17da02526358c5291a3f737c6d4b859))

## v0.1.2 (2023-04-11)
### Documentation
* **changelog:** Manual fix changelog for missing version ([`68a71ed`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/68a71ed76ae53d758f45aca70fa2a61bbbff5a9d))
### Refactor
* Changed dynamic imports to normal dependencies ([`5b0095f`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/5b0095f9121a92e1573415e08461561a8bd0e023))

## v0.1.1 (2023-04-11)
### Feature
* initial version of the bundler plugin. ([`adc7792`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/adc7792b8bbe2ee2e9326377f54f4010aa94d69c))
