# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Plugin skeleton: `herdr-plugin.toml`, the `bin/my-herdr` dispatcher and the
  `myherdr` package (herdr CLI wrapper, invocation context, error type).
- `my-herdr.ping` action: writes the plugin environment and invocation context
  to the plugin log. Read-only, for verifying an install.
- Test harness: `unittest` suite with a fake `herdr` CLI, manifest validation,
  and GitHub Actions CI.

[Unreleased]: https://github.com/gysi/my-herdr/commits/main
