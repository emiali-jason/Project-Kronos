# KRONOS Configuration Package

## Purpose

The Configuration domain owns runtime configuration.

## Responsibilities

- Read environment variables
- Load local `.env` when present
- Validate required configuration
- Expose configuration to other domains

## Does NOT own

- Authentication
- Broker communication
- Trading logic
- Validation
- Risk
- Portfolio
- Execution

## Architecture Principle

Configuration owns secrets.

Provider consumes configuration.

Secrets must never be hardcoded.
