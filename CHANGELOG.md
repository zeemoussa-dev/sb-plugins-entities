# CHANGELOG

All notable changes to the Entities plugin. The framework (Second Brain) is a separate
repository and is never copied in here.

## [Unreleased]

- chore: built against Plugin API v6 (1.0.3 -> 1.0.4). No behaviour change; the host loads only plugins built for
  its exact `framework_api`.

- fix: a hub note whose name is taken by another note still resolves its Customer (1.0.3, framework API v5,
  framework `BUG-076`). `name_by_tag` swept the framework's by-name index, which holds one note per file name, so
  a Customer hub sharing its name with another note was absent and every Thread tagged with it showed no customer.
  It sweeps `api.vault.entries()` now. Needs framework API v5, so this version will not load on an older host.

- chore: 1.0.1 -- built for framework API v3 (framework `ADR-025`, which lets a plugin contribute a Cockpit tab). Nothing in this plugin changed; the host loads only plugins built for its exact API version, so a republish is what keeps Entities loadable after that bump.

- docs: `CLAUDE.md` and `MEMORY.md` for this repository (framework `ADR-023`): a session opened here works on
  this plugin alone, with the Plugin API boundary, the on-disk format rule and the Templates rule.

## 1.0.0 — 2026-09-17

- feat: Entities extracted from the framework -- the discovery registry (`Settings/Entities.md`, format
  unchanged) served under `/plugins/entities/entities`, the `entities.customers` service and Cockpit customer
  enricher, Cockpit Expert matching by Customer, the People folders and seed data file registrations, the
  `customer`/`partner`/`opportunity` Templates, the Entities settings page and the Email Cockpit's Customer row.
