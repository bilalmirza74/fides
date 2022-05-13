# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/)

The types of changes are:

* `Added` for new features.
* `Changed` for changes in existing functionality.
* `Developer Experience` for changes in developer workflow or tooling.
* `Deprecated` for soon-to-be removed features.
* `Docs` for documentation only changes.
* `Removed` for now removed features.
* `Fixed` for any bug fixes.
* `Security` in case of vulnerabilities.

## [Unreleased](https://github.com/ethyca/fides/compare/1.6.0...main)

### Added

* Added dependabot to keep dependencies updated
* Include a warning for any orphan datasets as part of the `apply` command.

### Changed

* Comparing server and CLI versions ignores `.dirty` only differences, and is quiet on success when running general CLI commands
* Migrate all endpoints to be prefixed by `/api/v1` [#623](https://github.com/ethyca/fides/issues/623)

### Developer Experience

* Replaced `make` with `nox`
* Removed usage of `fideslang` module in favor of new [external package](https://github.com/ethyca/fideslang) shared across projects

### Docs

* Updated `Release Steps`
* Replaced all references to `make` with `nox` [#547](https://github.com/ethyca/fides/pull/547)
* Removed config/schemas page [#613](https://github.com/ethyca/fides/issues/613)

### Fixed

* Resolved a failure with populating applicable data subject rights to a data map
* Updated `fideslog` to v1.1.5, resolving an issue where some exceptions thrown by the SDK were not handled as expected
* Host static files via fidesapi [#621](https://github.com/ethyca/fides/pull/621)

## [1.6.0](https://github.com/ethyca/fides/compare/1.5.3...1.6.0) - 2022-05-02

### Added

* CHANGELOG.md file
* On API server startup, in-use config values are logged at the DEBUG level
* Send a usage analytics event upon execution of the `fidesctl init` command

### Developer Experience

* added isort as a CI check
* Include `tests/` in all static code checks (e.g. `mypy`, `pylint`)

### Changed

* Published Docker image does a clean install of Fidesctl
* `with_analytics` is now a decorator

### Fixed

* Third-Country formatting on Data Map
* Potential Duplication on Data Map
* Exceptions are no longer raised when sending `AnalyticsEvent`s on Windows
* Running `fidesctl init` now generates a `server_host` and `server_protocol`
  rather than `server_url`