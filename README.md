# Entities — a Second Brain plugin

Customers, Partners, Affiliates and Opportunities. Installing this plugin gives
a second brain its company-relationship model; a second brain without it (a
CFO's, say) has none.

| Part | Holds |
|---|---|
| `plugin.json` | id `entities`, version, the framework API it is built for |
| `backend/registry.py` | the Entities discovery registry, `Settings/Entities.md`, served under `/plugins/entities/entities` |
| `backend/customers.py` | the `entities.customers` service and Cockpit's customer enricher |
| `backend/opportunities.py` | the `entities.opportunities` service: a Customer's pipeline (its Opportunity notes and its affiliates'), listed, created and edited for another plugin |
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

## The `entities.opportunities` service

Asked for at call time with `api.get_service("entities.opportunities")`:

| Method | Returns |
|---|---|
| `customers()` | `[{name, stem, tag, affiliates: [{name, stem, tag}]}]`, every top-level Customer hub |
| `create_affiliate(customer_stem, name, aliases=None)` | `{name, stem, tag}` of the new affiliate hub under a top-level Customer: hub note from the `customer` Template, its History/Captures, the parent's `## Affiliates` link, and the registry row (an existing discovered row is adopted, its domain kept) |
| `list_for_customer(customer_stem, include_affiliates=True)` | `[opportunity]`, the Customer's own first, then each affiliate's |
| `create(owner_stem, title, fields, plan)` | the new `opportunity`; `owner_stem` is a Customer's or an affiliate's hub |
| `update(opportunity_id, fields, plan=None)` | the `opportunity` as it now stands; `plan` given replaces the Consumption Plan |

An `opportunity` is `{id, title, stem, customer, affiliate, status, stage, product, route, partner,
billing_profile, consumption_start, expected_monthly_usd, plan: [{month, usd}], updated}` --
`affiliate` is the affiliate's name or `None`, `expected_monthly_usd` an int or `None`.
`fields` may set `status`, `stage`, `product`, `route`, `draws_against`, `partner`,
`technologies`, `billing_profile`, `consumption_start`, `expected_consumption` and
`expected_monthly_usd`. A broken rule raises `ValueError` (`OpportunityError`; an unknown
hub or id is its subclass `OpportunityNotFound`).

## Upgrading the `opportunity` Template

The Marketplace installs a Template only where the install has none, so an install
that had Entities before 1.1 keeps its v2 `opportunity` Template. Nothing breaks: the
service reads a v2 note (its new fields read as empty) and brings it to v3 on its first
edit. To adopt v3 itself, the operator:

1. Opens the install's copy, `<SECOND_BRAIN_DATA_PATH>/data/Templates/opportunity/Template.json`.
2. Carries any of their own edits into this repository's `templates/opportunity/Template.json`,
   and replaces the install's copy with the result. It takes effect on the next read.
3. Moves any Skill whose `writes:` declares `requires: 2` against `opportunity` to `requires: 3`
   in the install's own repository; deploying one that still says 2 is refused.

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
