# Changelog

<!--next-version-placeholder-->

## v1.1.0 (2024-07-04)

### Feature

* Started on TypeScript support via dukpy (+ custom loader for browser and buildtime import resolver) ([`a8ab5cd`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/a8ab5cda1030c16ac3e2faa67c5485e5a873dd80))

### Fix

* Minor tweaks in TS loading: ([`9366383`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/93663835cfd6fab2f17db4d66c3018c589288d3e))

### Documentation

* Added docstrings to new TS parts and updated README ([`ce0d8b2`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/ce0d8b24175b6607442cd2b79f2a10a75b270eb0))

## v1.0.6 (2024-04-22)

### Fix

* Also work with Path for should_publish ([`f58efe5`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/f58efe5dbf9057e68256af8e3621cd974d93e19b))

## v1.0.5 (2024-04-22)

### Fix

* Don't crash if 'setting' is not a str (e.g. Path) ([`9d817fe`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/9d817fe1ea04affd9e8d178fda5b50631a1b2a2c))

## v1.0.4 (2024-04-12)

### Fix

* Require_sudo before chmod ([`c50193a`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/c50193a8b5112e514a46b72d98cdaccedb1ad881))

## v1.0.3 (2024-02-02)
### Fix
* **pyproject:** Pyproject.toml can now be used via -c option (instead of as fallback only) ([`cfc0cf0`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/cfc0cf046409c63e74ae9394ccd5d8fc7f2c2f45))

## v1.0.2 (2024-01-16)
### Fix
* Database-based build now works via pathlib + auto creates tmp folders (incl. parents) ([`2eb06fa`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/2eb06fa4b74ca1cb67b816f33f6cbcc025877bcf))

## v1.0.1 (2024-01-16)
### Fix
* Better .toml loading + verbose logging ([`b01c6d7`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/b01c6d7733962a733d1217e5b0841a0d4b5ee87b))

### Documentation
* **config:** Explained more about the bundle.yaml file ([`f945ca4`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/f945ca478b8c1ebf22e656e398742835aab3ea10))

## v1.0.0 (2023-09-26)
### Feature
* Bundler can now load extra scss variables from yaml/toml/json/... ([`37e5707`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/37e57075d6c49168b759e292223abdae020145da))
* **scss:** WIP to load variables from file or url instead of yaml only ([`3d6ef99`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/3d6ef9904aa01a6110def2faf39e4260deed3aeb))
* **scss:** Scss variables can now be injected via Python ([`b73ebb0`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/b73ebb0d0b17bb3166e9cf41c2ee948008a175f0))

## v0.2.5 (2023-09-20)
### Fix
* Include the scss path so imports are resolved properly ([`427ff92`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/427ff92ae5479c5585733d05ec2acfa66f52a952))

## v0.2.4 (2023-09-20)
### Fix
* **sass:** Actually support sass next to scss ([`1e5cd99`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/1e5cd9985c8a9fee45bce46c64b1fa9b0b019c57))

## v0.2.3 (2023-09-20)
### Fix
* Inline multiline scss can now also be converted ([`964d28d`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/964d28d701782913be46b4f6b41b2a045873c99d))

### Documentation
* Copied README from previous repo ([`6464165`](https://github.com/educationwarehouse/edwh-bundler-plugin/commit/64641658cca6be8b957eb49afe706487a3a28ca0))

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
