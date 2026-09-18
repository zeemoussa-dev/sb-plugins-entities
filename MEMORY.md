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
- **[2026-09-17] Every change ships through publishing.** A published version is
  immutable, so a change means a new `version`.
