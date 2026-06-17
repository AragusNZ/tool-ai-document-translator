# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Docker CI no longer pushes to GHCR on every `main` commit; image publish runs on `v*` tags only, with smoke tests on PRs and `main`

## [0.1.0] - 2026-06-17

Initial Release