# Plan — Customers & Partners screens (Entities 1.4.0)

Operator's ask (2026-10-17): "a Place to Display Partners and Customers with their Data".

## Decided with the operator

| Question | Answer |
|---|---|
| New plugin or extend Entities? | **Extend Entities** — it owns the hub notes, their Templates and services |
| What data? | The hub note's fields and sections; Opportunities; People; activity carrying the hub's tag; Azure Cost Manager data |
| Screens | A list, and an **editable** detail page per Customer/Partner |
| What is editable? | The hub's **Personal Notes** section, and the **Captures** note's own `## Notes` section |
| Adding notes ("enrichments") | **Append to Captures**: a dated entry under the Captures note's `## Notes`, no new note kind |
| Cost data | Through a **Cost Manager service**, not its HTTP routes |

## Screens

- `/entities` — **Customers & Partners** (sidebar entry). Two groups, Customers and
  Partners; affiliates nested under their parent; search box; per row: domain,
  affiliate count, opportunity count, people count, a signed-commitment badge.
  Filter and search live in the URL (`pluginHost/state`).
- `/entities/<kind>/<stem>` — one Customer or Partner. Trail (`pluginHost/breadcrumbs`):
  Customers & Partners › parent (for an affiliate) › this one. Sections:
  - header: name, description, domain, aliases, tags, parent / affiliates
  - **Signed commitment** (Customers) — read-only here; it stays editable in Cost Manager and Obsidian
  - **Azure consumption** (Customers, when Cost Manager offers its service and the
    customer is linked) — signed, consumed %, term elapsed %, last month, recent
    sparkline, status; link to Cost Manager's own page
  - **Opportunities** — a Customer's own and its affiliates' (`entities.opportunities`);
    a Partner's are every opportunity naming it in `partner`
  - **Personal Notes** — rendered with `NoteText`; Edit → textarea → Save
  - **Captures** — an "add a capture" box (appends `- YYYY-MM-DD: text` under `## Notes`),
    the `## Notes` section editable as a whole, and `## Captured` (automated) read-only
  - **People** — Person notes under the hub folder's `People/` or carrying its tag
  - **Activity** — Meetings and Threads carrying the hub's tag, newest first (Threads
    are read off disk: they are excluded from the vault index by design)
  - **Other sections** of the hub note (Summary, Actions, Related, Affiliates, body
    text) rendered read-only; machine-written sections stay Hermes'.
  - **News** — the `<stem>-news` child note, rendered read-only, when it exists

## Backend

`backend/accounts.py` (`Accounts`), routes under `/plugins/entities/accounts`:

| Route | Does |
|---|---|
| `GET /accounts` | the list |
| `GET /accounts/{kind}/{stem}` | one hub's detail |
| `PUT /accounts/{kind}/{stem}/personal-notes` | `{text, previous}` → replaces `## Personal Notes` |
| `PUT /accounts/{kind}/{stem}/capture-notes` | `{text, previous}` → replaces the Captures note's `## Notes` |
| `POST /accounts/{kind}/{stem}/captures` | `{text}` → appends a dated line under `## Notes` |

- Hubs are found among notes that exist (`Work/Customers|Partners/<H>/<H>.md`, affiliates
  at `.../<H>/Affiliates/<A>/<A>.md`); nothing a caller passes becomes a path.
- A replace sends the text the page loaded (`previous`); if the note changed since
  (Obsidian, Hermes) the write is refused with 409 rather than overwriting it.
- Only the named section changes; every other byte of the note stays.
- A missing Captures note is created the way the Template's child is.

## Cost Manager (other repo, other session)

Requested in the shared notes: `azure-cost-manager.portfolio.for_entity(stem)` → its
portfolio row (+ `route`) or None. Entities asks at call time; absent → no panel.

## Done

Tests in `tests/test_accounts.py`; `publish_plugin.py --dry-run` passes; installed
from this folder; both screens checked in the browser on the operator's vault.
