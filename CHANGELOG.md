# CHANGELOG

All notable changes to the Entities plugin. The framework (Second Brain) is a separate
repository and is never copied in here.

## [Unreleased]

- feat: a Customer's signed Azure commitment on its hub note (1.3.0, Plugin API 10). `entities.customers` gains
  `commitment(customer_stem) -> dict | None` and `set_commitment(customer_stem, commitment | None) -> dict | None`,
  for a Customer or an affiliate. The commitment is flat frontmatter -- `macc_type`, `macc_amount`, `macc_currency`,
  `macc_start`, `macc_end`, `macc_note`, `macc_includes_marketplace`, `macc_subtracts_credits` -- so Obsidian's
  Properties pane shows and edits it; writing touches only those keys, and `None` removes them all. A bad value is
  refused with `ValueError`; a hand-typed value is read as it stands. The `customer` Template documents the keys
  (`frontmatter_enums`, `frontmatter_rules`) and keeps version 2: no section changed, and the keys are optional, so an
  existing install needs nothing to start using them.

- feat: `entities.opportunities.create_affiliate(customer_stem, name, aliases=None)` (1.2.0) -- a new affiliate under
  a top-level Customer, made the way the company Skill makes one: the hub note at
  `Work/Customers/<Parent>/Affiliates/<Name>/<Name>.md` from the `customer` Template, its own `customer/<slug>` tag on it
  and on its History and Captures children, the link in the parent's `## Affiliates`, and the `Settings/Entities.md` row
  with `Affiliate of` and `Created: Yes`. A row discovery already registered is adopted, keeping its domain and aliases.
  Refuses (`ValueError`) a name already taken by a Customer, affiliate, alias or Partner, a soft-deleted or partner
  registry row, and an unknown or affiliate parent. `customers()` now also finds an affiliate on disk, so a new one
  lists before the next reindex. The registry gains `find_entity` and a `created` flag on create and update.

- feat: the `entities.opportunities` service (1.1.0, Plugin API 9) -- a Customer's sales pipeline as its Opportunity
  notes, its affiliates' included, for another plugin to list, create and edit without writing those notes itself
  (the Azure Cost Manager's Pipeline first). `customers()`, `list_for_customer(customer_stem, include_affiliates=True)`,
  `create(owner_stem, title, fields, plan)` and `update(opportunity_id, fields, plan=None)`. It writes what the Template
  says -- own folder, plain file name, frontmatter order, defaults and enums, the `kind/opportunity` and `customer/`
  tags, the link in the owner's `## Opportunities`, the History and Captures children -- and refuses a rule it would
  break with `ValueError`. `update` rewrites the Consumption Plan table and logs the change in the note's History.
  Notes are found on disk under their hub, so one created a moment ago lists before the next reindex; paths past
  Windows' 260-character limit are handled.

- feat: Opportunity Template v3. Frontmatter adds `billing_profile` (the enrollment or billing account number) and
  `consumption_start` (`YYYY-MM`); a `## Consumption Plan` section holds a `| Month | USD |` table, one row per month;
  `expected_monthly_usd` is that plan's last month. An install that already has the `opportunity` Template keeps it
  (the Marketplace never overwrites one): a v2 note still lists, with those fields empty, and is brought to v3 by its
  first edit through the service; the README gives the operator's steps for adopting the v3 Template itself.

- chore: built against Plugin API v9 (1.0.7). The host now also provides `openpyxl` to plugin backends (framework `ADR-040`), which moved the API to 9. No behaviour change; the republish is what keeps the plugin loading.

- chore: built against Plugin API v8 (1.0.6). The host now provides a charting library (`echarts` and `echarts-for-react`, including their subpaths, framework `ADR-039`), which moved the API to 8. No behaviour change; the host loads only plugins built for its exact API, so this republish is what keeps the plugin loading.

- chore: built against Plugin API v7 (1.0.5). No behaviour change; the host loads only plugins built for its
  exact `framework_api`.

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
