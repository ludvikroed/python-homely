# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

## [0.1.1] - 2026-03-17

### Changed

- Reduced log noise and shortened identifiers in websocket and client logging.
- Improved error classification so auth failures surface as auth errors in more SDK methods.

### Fixed

- Malformed successful API responses now raise SDK response errors instead of raw Python exceptions.

## [0.1.0] - 2026-03-16

### Added

- Async Homely API client.
- Token authentication and refresh helpers.
- Location and home-data fetch helpers.
- Realtime websocket client with reconnect loop.
- Typed exceptions and token response model.
