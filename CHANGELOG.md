# CHANGELOG

All notable changes to the Entities plugin. The framework (Second Brain) is a separate
repository and is never copied in here.

## [Unreleased]

- docs: `CLAUDE.md` and `MEMORY.md` for this repository (framework `ADR-023`): a session opened here works on
  this plugin alone, with the Plugin API boundary, the on-disk format rule and the Templates rule.

## 1.0.0 — 2026-09-17

- feat: Entities extracted from the framework -- the discovery registry (`Settings/Entities.md`, format
  unchanged) served under `/plugins/entities/entities`, the `entities.customers` service and Cockpit customer
  enricher, Cockpit Expert matching by Customer, the People folders and seed data file registrations, the
  `customer`/`partner`/`opportunity` Templates, the Entities settings page and the Email Cockpit's Customer row.
