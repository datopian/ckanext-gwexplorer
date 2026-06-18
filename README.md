[![Tests](https://github.com/sagargg/ckanext-gwexplorer/workflows/Tests/badge.svg?branch=main)](https://github.com/sagargg/ckanext-gwexplorer/actions)

# ckanext-gwexplorer

A CKAN resource view that turns any tabular resource into an interactive
**data explorer** powered by [Graphic Walker](https://github.com/Kanaries/graphic-walker).

It gives you two things:

- **Publishers** get a drag-and-drop chart builder in the CKAN view editor. The
  chart(s) they build are saved with the view as a *preset*.
- **End users** see those preset charts on the dataset page — a clean Data tab
  plus one tab per chart — and can click **Explore yourself** to open the full
  editor and play with the data ad hoc.

If a view has no preset, the explorer **auto-generates a default chart** from the
resource's column types (geographic point map, time-series line, categorical
bar, scatter, …).

Data is queried live from the CKAN **DataStore** (Postgres) via a small DSL API,
so charts work against the full table, not a sampled download.

---

## Features

- 📊 Interactive Graphic Walker explorer as a CKAN resource view (`gwexplorer`).
- 🧑‍🎨 **Publisher presets** — build one or more charts in the view editor; they
  save automatically with the view (no separate "save chart" step).
- 👀 **Read-only presentation** on the dataset page (chart tabs + Data table, no
  editing panels), with an **Explore yourself** button for ad-hoc analysis.
- 🤖 **Format-based default charts** when no preset exists, chosen from field
  types (geo / temporal / categorical / numeric).
- 🛢️ Queries the DataStore directly through [pygwalker](https://github.com/Kanaries/pygwalker)'s
  DSL, so aggregation/filtering happen in Postgres.
- 🔌 Embeddable same-origin (CKAN templates) **or** cross-origin (other apps) via
  an API token.

---

## How it works

```
┌──────────────────────────┐         ┌─────────────────────────────────────────┐
│  CKAN browser page        │         │  ckanext-gwexplorer (this repo, Python)  │
│  ┌────────────────────┐   │  HTTP   │                                          │
│  │ Graphic Walker JS  │◄──┼─────────┤  Action API:                             │
│  │ (bundled React app)│   │         │   • show_dsl_metadata   (field schema)   │
│  └────────────────────┘   │         │   • dsl_query_data      (DSL data query) │
│   #gw-dataexplorer        │         │   • gwexplorer_default_spec (defaults)   │
└──────────────────────────┘         │                                          │
                                      │  IResourceView "gwexplorer":             │
                                      │   • view_template / form_template        │
                                      │   • gw_spec (preset IChart[] in config)  │
                                      └───────────────────┬──────────────────────┘
                                                          │ reads
                                                ┌─────────▼─────────┐
                                                │ CKAN DataStore     │
                                                │ (Postgres replica) │
                                                └────────────────────┘
```

The React front end is maintained in a separate repo,
[**ckan-gw-explorer**](https://github.com/datopian/ckan-gw-explorer), and shipped
here as a prebuilt bundle under [`ckanext/gwexplorer/assets/js/`](ckanext/gwexplorer/assets/js/).
See [Rebuilding the front-end bundle](#rebuilding-the-front-end-bundle).

---

## Requirements

| | |
|---|---|
| CKAN | 2.11 (tested) |
| DataStore | **required** — the resource must be datastore-active |
| Python deps | `pygwalker==0.4.8.8`, `psycopg2` (installed via `setup.cfg`) |

Compatibility:

| CKAN version | Compatible? |
| ------------ | ----------- |
| 2.11         | ✅ yes       |
| < 2.11       | not tested   |

---

## Installation

```bash
# in your CKAN virtualenv
git clone https://github.com/datopian/ckanext-gwexplorer.git
cd ckanext-gwexplorer
pip install -e .
pip install -r requirements.txt
```

Add `gwexplorer` to `ckan.plugins` in your CKAN config (it must be loaded
**after** `datastore`):

```ini
ckan.plugins = ... datastore gwexplorer
```

Then restart CKAN.

---

## Configuration

The only required setting is the DataStore read URL (CKAN sets this when the
DataStore is configured):

```ini
ckan.datastore.read_url = postgresql://datastore_ro:pass@localhost/datastore
```

Optional SQLAlchemy connection-pool tuning (defaults shown):

```ini
ckanext.odn.dsl.pool_size    = 15
ckanext.odn.dsl.max_overflow = 100
ckanext.odn.dsl.pool_recycle = 3600
ckanext.odn.dsl.echo         = false
ckanext.odn.dsl.echo_pool    = false
```

The `gwexplorer` view can be added to any resource whose format is `csv`,
`xls`, `xlsx`, or `tsv`, or that is datastore-active.

---

## Usage

### Publisher: create a preset view

1. On a resource, go to **Manage → Views → Add view → Data Explorer**.
2. Build one or more charts in the embedded Graphic Walker (each chart is a tab).
3. Click **Add / Update**. The chart specs are captured automatically and stored
   with the view — no separate save action.

Leave the builder empty to let the dataset page auto-generate a default chart.

### End user: the dataset page

The view renders the preset charts read-only — a **Data** tab and one tab per
chart — with an **Explore yourself** button that opens the full editable
explorer (changes there are not persisted).

---

## Action API

All three actions are `side_effect_free` (callable via GET or POST) and check
`resource_show` access.

| Action | Method | Purpose |
| ------ | ------ | ------- |
| `show_dsl_metadata` | GET | Field schema (types) for a resource: `?resourceID=<id>&sort=true` |
| `dsl_query_data` | POST | Run a Graphic Walker DSL payload against the DataStore table |
| `gwexplorer_default_spec` | GET | Suggest default chart spec(s) from field types: `?resourceID=<id>` |

Example:

```bash
curl 'https://ckan.example.org/api/3/action/show_dsl_metadata?resourceID=<RES_ID>'
```

> **CSRF / POST note (CKAN 2.11):** browser POSTs are CSRF-protected. The bundled
> front end sends the `X-CSRFToken` from the page meta tags automatically for
> same-origin use. For cross-origin embedding, authenticate with an
> `Authorization` token instead (CKAN exempts token-authenticated requests from
> CSRF). See the front-end README's `apiToken` / `credentials` props.

---

## Stored view config

The preset is stored on the resource view as a single JSON field, `gw_spec`,
declared in the view schema and validated by
[`gwexplorer_valid_spec`](ckanext/gwexplorer/validators.py). It holds a Graphic
Walker `IChart[]` (the full chart specs). The view is rendered **inline**
(`iframed: False`) so the spec is never crammed into a preview iframe URL, and
uses CKAN's **full-page edit** layout so the builder gets the full width.

---

## Rebuilding the front-end bundle

The JavaScript is built in the
[ckan-gw-explorer](https://github.com/datopian/ckan-gw-explorer) repo and copied
here as a hashed bundle:

```bash
# in the ckan-gw-explorer repo
CI=false npm run build:example
# then copy the produced bundle into this extension:
cp example/build/static/js/main.<hash>.js \
   ../ckanext-gwexplorer/ckanext/gwexplorer/assets/js/
```

Update the filename in
[`ckanext/gwexplorer/assets/webassets.yml`](ckanext/gwexplorer/assets/webassets.yml)
to match the new hash, remove the old bundle, and **restart CKAN** (the asset
filename changes on every build, so a restart is required to re-register it).

---

## Development

```bash
pip install -e .
pip install -r dev-requirements.txt
```

Run the tests (pure unit tests need no database; the plugin-load test uses
`pytest-ckan`):

```bash
# unit tests only (no DB)
pytest ckanext/gwexplorer/tests/test_actions.py \
       ckanext/gwexplorer/tests/test_validators.py

# full suite against a test CKAN
pytest --ckan-ini=test.ini ckanext/gwexplorer/tests
```

Project layout:

```
ckanext/gwexplorer/
├── plugin.py          # IResourceView / IActions / IValidators registration
├── actions.py         # DSLService + default-spec heuristic + action endpoints
├── validators.py      # gw_spec JSON validator
├── assets/            # built JS/CSS bundle + webassets.yml
├── templates/
│   ├── gwexplorer.html        # consumer view (inline fragment)
│   └── gwexplorer_form.html   # publisher builder form
└── tests/
```

---

## License

MIT
