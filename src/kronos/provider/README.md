# KRONOS Provider Package

## Purpose

The Provider domain owns communication with external systems.

## Responsibilities

- Broker connectivity
- Market-data connectivity
- External API normalization

## Does NOT own

- Trading logic
- Validation
- Risk
- Portfolio
- Execution decisions

## Architecture

The Provider domain exposes approved contracts.

Business logic must never depend directly on SDK-specific objects.
