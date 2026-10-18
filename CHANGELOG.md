# CHANGELOG

All notable changes to the Entities plugin. The framework (Second Brain) is a separate
repository and is never copied in here.

## [Unreleased]

- feat: **`macc_affiliates` on a Customer's commitment** (1.8.0; operator, 2026-10-18). It says how a parent's
  affiliates relate to its MACC. With `roll up` (the default, as DGE), they sign none of their own, so their
  consumption burns the parent's. With `own` (as Mubadala), each signed its own, so only the parent's own
  enrollments burn it. A hand-typed value other than `own` reads as `roll up`. The account page shows it, and
  `entities.customers.COMMITMENT_FIELDS` names the fields `set_commitment` accepts, so a caller can leave out one
  an older Entities does not know. Read by Azure Cost Manager and Core42 Insight.

- fix: a hub looked up while the vault index is still loading -- seconds after every backend reload -- no longer
  reads as "not found" (1.7.1). Entities waits for the index (up to 20 s), then raises `VaultNotReady` (a
  RuntimeError, deliberately not a ValueError; HTTP 503), so a caller never shows a customer with saved Insight terms
  as having none. The Customers & Partners page shares the same lookup.

- perf: resolving a hub stem no longer re-reads every hub note (1.7.0). A hub's frontmatter is cached on its file's
  mtime and size, and the hub list for 2 seconds; this plugin's own writes clear both at once. 53 `commitment()`
  calls on a real vault: 5.8 s -> 0.01 s. New bulk reads for a page that shows every customer:
  `entities.customers.commitments(stems=None)` and `insights(stems=None)` -> `{stem: value or None}`, unknown or
  ambiguous stems left out.

- feat: the Insight note lists an upfront term's `payments` (instalments, Insight 0.4.0) under the Terms table, so
  they read in Obsidian (1.6.2). The json was already kept as sent.

- change: the Insight note carries `{terms, note}` only (1.6.1) -- the operator dropped Insight targets. A
  `targets` key is now refused as unknown, and the note no longer has a Targets table.

- feat: `entities.customers.insight(stem)` / `set_insight(stem, value | None)` (1.6.0), for the Core42 Insight
  plugin: `{terms: [{model, start, end?, percent?, amount?, include_marketplace?, subtract_credits?, ...}],
  targets: {"YYYY": amount}, note}`, or None. Kept in a note of its own beside the hub,
  `<stem> - Insight.md` -- flat frontmatter, the data as one fenced json block under `## Data`, and a readable
  table regenerated on every save. The hub is never touched; None deletes the note. Shape is checked here
  (dates, numbers, a `model` and `start` per term; unknown keys and models kept), meaning in Insight. A hand-broken
  json block is reported, never read as empty.

- feat: Partner hubs alongside Customer hubs (1.5.0), so an Azure Cost Manager customer may link to a Partner note.
  `entities.opportunities.hubs()` lists every top-level Customer and Partner hub with `kind`, affiliates nested at any
  depth; `customers()` is unchanged (Customers only). Every stem-taking method -- `entities.customers.commitment` /
  `set_commitment`, `list_for_customer`, `create` -- now accepts a Partner's or a partner affiliate's stem, and a stem
  found under both kinds is refused as ambiguous. `list_for_customer` takes in affiliates at every depth. The
  Customers & Partners page shows a Partner's commitment and, when linked, its Azure consumption.
- feat: `entities.opportunities.create_customer(name, aliases=None)` and `POST /plugins/entities/accounts/customer`
  (1.5.0): a top-level Customer hub made at once -- the note, its History and Captures, its own tag, the registry
  row marked Created -- instead of a registry row waiting for discovery and the company Skill.

- feat: Customers & Partners screens (1.4.0, Plugin API 11). `/entities` lists every Customer and Partner hub,
  affiliates nested under their parent at any depth, with search. `/entities/<kind>/<stem>` shows one hub: its fields,
  signed commitment, Azure consumption (from Cost Manager's `azure-cost-manager.portfolio` service when installed),
  its sections and News, Opportunities (a Partner's are those naming it), People, and Meetings/Threads carrying its
  tag. Editable: the hub's `## Personal Notes` and its Captures note's `## Notes`, plus "add a capture" (a dated line
  under `## Notes`). A save carrying text that no longer matches the note is refused (409), never overwritten.
  Backend: `backend/accounts.py`, routes under `/plugins/entities/accounts`.

- feat: a Customer's signed Azure commitment on its hub note (1.3.0, Plugin API 11). `entities.customers` gains
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
