# CLAUDE.md — sb-plugins-entities

Guidance for Claude Code working in **this** repository.

## What this repository is

The source of the **Entities plugin** for Second Brain: Customers, Partners,
Affiliates and Opportunities — the discovery registry, customer resolution, and
Customer-based Expert matching in Cockpit, plus the Templates those entities use.

Installing this plugin gives a second brain a company-relationship model; an
install without it has none, which is the point.

## What this repository is not

- **Not the framework.** Second Brain is a **separate repository**. Its source
  never appears here, and this plugin may import only the Plugin API.
- **Not an install's own content.** The company Skills that maintain entities on a
  real vault belong to that install's repository (`sb-pss-agent`), not here.

## Layout

```
plugin.json          id, name, version, framework_api, requires
backend/registry.py  the Entities registry (Settings/Entities.md), served under /plugins/entities/
backend/customers.py the entities.customers service and Cockpit's customer enricher
backend/matching.py  Cockpit Expert matching by Customer
templates/           the customer, partner and opportunity Templates
ui/                  the Entities settings page and the Cockpit Customer row
tests/               this plugin's own tests; run on publish, never packaged
```

## Rules

- **The backend imports `app.plugin_api` and nothing else** from the framework;
  its own modules import each other relatively. The screens import only their own
  files, `src/pluginHost/`, and react / react-router.
- **`Settings/Entities.md` keeps its on-disk format.** The company Skills parse
  that file; a rendered file must stay byte-for-byte what they expect.
- **Templates are never overwritten on install.** An existing `customer`,
  `partner` or `opportunity` Template on an install is adopted as it is — it may
  carry the operator's edits.
- **Offer capability through the service**, so other plugins never import this
  one: `provide_service("entities.customers", ...)`.
- **Publish before believing anything.** `publish_plugin.py <repo> --dry-run` runs
  every gate: manifest, layout, import boundary, these tests, and a real build of
  the screens inside the framework.
- **Separate commits per logical change**, never skip hooks, never force-push.
  Update `CHANGELOG.md` and bump `version` for a change that ships.

## Tests

```bash
PYTHONPATH=<second-brain-checkout>/src/backend python -m pytest tests
```

They run against a stand-in for the Plugin API, so they need no install.
