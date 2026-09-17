# Entities — a Second Brain plugin

Customers, Partners, Affiliates and Opportunities. Installing this plugin gives
a second brain its company-relationship model; a second brain without it (a
CFO's, say) has none.

| Part | Holds |
|---|---|
| `plugin.json` | id `entities`, version, the framework API it is built for |
| `backend/registry.py` | the Entities discovery registry, `Settings/Entities.md`, served under `/plugins/entities/entities` |
| `backend/customers.py` | the `entities.customers` service and Cockpit's customer enricher |
| `backend/matching.py` | Cockpit Expert matching by Customer: the `<slug>-expert` in the Customer Section, else that Section's fallback agent |
| `templates/` | the `customer`, `partner` and `opportunity` Templates |
| `ui/` | the Entities settings page (Settings → Plugins → Entities) and the Customer row in the Email Cockpit |
| `tests/` | the plugin's own tests; run on publish, never packaged |

It also tells the framework where People are filed (`Work/Customers`,
`Work/Partners`) and that `Settings/Entities.md` is its seed data file.

The company Skills (`create-companies-partners`, `track-opportunities`,
`new-company-discovery`, `entity-domain-extraction`) stay agent-owned in the
agent repositories; this plugin carries no Hermes layer.

The plugin talks to the framework only through the Plugin API: `app.plugin_api`
in the backend and `src/pluginHost/` in the screens.

## Publish

From a Second Brain checkout:

```bash
src/backend/.venv/Scripts/python.exe src/backend/scripts/publish_plugin.py <path-to-this-repo>
```

Then install it from Settings → Marketplace and restart the backend.

## Tests

```bash
PYTHONPATH=<second-brain>/src/backend python -m pytest tests
```
