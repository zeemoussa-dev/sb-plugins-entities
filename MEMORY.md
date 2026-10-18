# MEMORY

Standing rules for this repository — what an agent must know to change the
Entities plugin without breaking an install. Rules only: no history, no narrative.

**Scope.** This file covers **this plugin only**. Second Brain (the framework) is
a separate repository with its own memory, and an install's own company Skills
live in that install's repository; nothing about either's internals belongs here.
A capability this plugin needs and the Plugin API lacks is recorded here and
raised in the framework.

---

- **[2026-09-17] The Plugin API is the only way in.** The backend imports
  `app.plugin_api` and nothing else from the framework; the screens import only
  their own files, `src/pluginHost/`, and react / react-router. Publishing refuses
  anything else.
- **[2026-09-17] `Settings/Entities.md` keeps its on-disk format byte for byte.**
  The install's company Skills parse that file. Changing the rendering here breaks
  them silently; the format was ported unchanged from the framework for exactly
  that reason. Read and write it only through `api.data`, which reaches this
  plugin's registered files and nothing else.
- **[2026-09-17] A deleted entity is soft-deleted** (`Deleted: Yes`, plus
  `Ignore: Yes`). A hard delete drops its Domain from the "already tracked" set,
  so discovery rediscovers it on the next scan.
- **[2026-09-17] THE customer is never a Partner.** The hub-tag lookup holds both
  `customer/` and `partner/` tags, so resolution filters to `customer/` -- without
  it a Thread tagged `["partner/g42", "customer/mubadala"]` resolved to "G42".
- **[2026-09-17] Templates are adopted, never overwritten.** An install that
  already has `customer`, `partner` or `opportunity` keeps its own copy, which may
  carry the operator's edits; installing this plugin only adds what is missing.
- **[2026-09-17] Cockpit matching is advisory.** Return registered agent ids only;
  the framework ignores unknown ones, skips a matcher that raises, and recommends
  nobody when no plugin matches -- the framework itself knows no Customer.
- **[2026-09-17] Offer capability as a service** (`entities.customers`), so no
  other plugin ever imports this one. Plugin-to-plugin imports are refused.
- **[2026-10-16] This plugin is the only writer of Opportunity notes from code.**
  Another plugin uses `entities.opportunities` and never writes them itself: this
  plugin owns the `opportunity` Template, so one writer keeps the notes to it. The
  Plugin API has no vault write, so `backend/opportunities.py` writes files itself:
  every path comes from a hub found in `api.vault.entries()`, never from a stem a
  caller passed, a title must already be a valid file name, and every open goes
  through `_long()` for Windows' 260-character limit.
- **[2026-10-16] The service carries the Template's content as constants**
  (`KEY_ORDER`, `DEFAULTS`, `ENUMS`, `SECTIONS`, `CHILDREN`): an installed plugin has
  its backend but not its `templates/` folder. A test pins them to
  `templates/opportunity/Template.json`; change both together.
- **[2026-10-16] Template upgrades are lazy and per note, never a bulk migration.**
  The Marketplace never overwrites an installed Template, and a migration that
  rewrote every Opportunity note would touch operator-owned content all at once.
  So: reads tolerate an older note (missing fields read as empty), the first edit
  through the service adds what the newer Template has (v3: `billing_profile`,
  `consumption_start`, the `## Consumption Plan` table) and leaves every other line
  as it was, and the installed Template itself is the operator's to replace (README,
  "Upgrading the opportunity Template").
- **[2026-10-16] A Template section entry takes only `name`, `access`,
  `required_non_empty`, `allowed_callers`.** The framework parses a section with a
  strict dataclass; any other key makes the whole Template fail to load. Say a
  section's format in `frontmatter_rules` instead.
- **[2026-10-16] Opportunity notes are found on disk under their hub**
  (`<hub>/Opportunities/<T>/<T>.md`), not in the vault index: the index is rebuilt
  on its own schedule, and an opportunity created a moment ago must list at once.
- **[2026-10-17] An affiliate made from code matches what the company Skill makes**
  (`create-companies-partners`, in the install's repository): the engine's
  `create()` from the `customer` Template plus that Skill's backfill -- the hub's
  own `customer/<slug>` tag on the hub and on both children, which the Template
  cannot express -- and the registry row set `Created: Yes`, or discovery makes the
  hub again. A row already discovered for that name is adopted, never duplicated.
  Affiliates nest one level under a top-level Customer here.
- **[2026-10-17] A Customer's signed commitment lives on its hub note**, as flat
  optional `macc_*` frontmatter (operator's decision: the note is the single source
  of truth, editable in Obsidian). Never in `frontmatter_defaults`: a Customer with
  no commitment carries none of the keys. Writes touch only those keys.
- **[2026-10-17] Optional frontmatter is not a Template version bump.** `version` is
  the sections contract a Skill pins with `requires:`; adding an optional key changes
  no section, and bumping would refuse every Skill pinned to the old number. An
  existing install needs nothing: the service writes the keys, and the installed
  Template's copy only lacks their documentation.
- **[2026-10-17] The Customers & Partners page writes two sections only:** the hub's
  `## Personal Notes` and its Captures note's `## Notes` (operator's decision). Every
  other section is Hermes' and is shown read-only; `## Captured` stays the pipeline's.
  A replace carries the text the page loaded and is refused (409) when the note no
  longer holds it -- the operator edits the same notes in Obsidian.
- **[2026-10-17] "Adding a note" to a Customer/Partner is a capture, not a new note
  kind** (operator's decision): a dated `- YYYY-MM-DD: text` under the Captures
  note's `## Notes`.
- **[2026-10-17] Another plugin's data reaches the hub page only through its service**
  (`azure-cost-manager.portfolio.for_entity(stem)`), asked at call time; absent or
  failing reads as no panel, never a failed page.
- **[2026-10-17] Affiliates nest deeper than one level** (`<P>/Affiliates/<A>/Affiliates/<B>`,
  seen on Partners). Hubs are found by walking `Work/Customers` and `Work/Partners`
  recursively off disk, never by a fixed path depth.
- **[2026-10-18] A stem-taking service method accepts a Customer or a Partner hub**
  (operator: Azure Cost Manager links to Partner notes too). `customers()` stays
  Customers only so its callers see no change; `hubs()` carries `kind`. A stem found
  under both kinds is refused as ambiguous, never guessed.
- **[2026-10-18] Never store a nested YAML block in a hub's frontmatter.** The
  framework's parser and the shared Hermes engine read frontmatter line by line and
  rewrite all of it from what they parsed, so a list of maps reads as "" and is wiped
  by the next Skill write to that note. One key per line, scalars or flow lists of
  strings -- as `macc_*`.
- **[2026-10-18] Structured data another plugin keeps about a hub goes in its own
  note beside it** (operator, for Core42 Insight): `<stem> - Insight.md`, flat
  frontmatter, the data as one fenced json block under `## Data`. No Skill writes it
  and nothing re-serialises a body, so it survives; the hub stays untouched. A json
  block that does not parse is an error, never "no data" -- or the next save would
  overwrite a hand edit.
- **[2026-10-18] Another plugin asks per customer, so stem resolution must be cheap.**
  Hub frontmatter is cached on (mtime, size), the hub list for `HUB_LIST_SECONDS`, and
  `_write_text` clears both -- every write to a vault note goes through it, or a write
  in the same file-clock tick would read back stale. Offer a bulk read
  (`commitments`, `insights`) for anything a report shows for every customer.
- **[2026-10-18] An empty vault index means "not loaded yet", never "no such hub".**
  The backend reloads whenever a backend file changes, and the index is empty for
  seconds after. The Work folder is found from the index, so a lookup then waits
  (`INDEX_WAIT_SECONDS`) and raises `VaultNotReady` (not a ValueError) if it never
  loads. `notes_in_kind` is no fallback: it lists only notes directly in `Work/<kind>/`.
- **[2026-09-17] Every change ships through publishing.** A published version is
  immutable, so a change means a new `version`.
