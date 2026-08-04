# Examples

Small, runnable programs that demonstrate the Python client. They mirror the
intent of the JS repo's `examples/` (a JSON:API example, a path-resolution
example, an authenticated example) without the JS build tooling.

## Setup

Install the package (from the repo root):

```bash
pip install -e .
```

Point the examples at a Drupal site. Copy the env template and edit it, or export
the variables directly:

```bash
cp examples/.env.example examples/.env
# then edit examples/.env
```

The examples read these variables:

| Variable | Used by | Meaning |
|---|---|---|
| `DRUPAL_BASE_URL` | all | Base URL of the Drupal site, e.g. `https://drupal.ddev.site`. |
| `DRUPAL_USERNAME` | `authenticated_and_cached.py` | Basic-auth username. |
| `DRUPAL_PASSWORD` | `authenticated_and_cached.py` | Basic-auth password. |

You can stand up a local Drupal with the JS repo's DDEV scripts
(`../js_api_client/scripts/init-drupal.sh`) and point `DRUPAL_BASE_URL` at it.

> The examples load `examples/.env` automatically if `python-dotenv` is installed;
> otherwise just export the variables in your shell.

## Running

```bash
python examples/get_collection.py
python examples/get_resource_by_path.py
python examples/authenticated_and_cached.py
python examples/async_reads.py
python examples/graphql_query.py
```

| Example | Shows |
|---|---|
| [`get_collection.py`](./get_collection.py) | Instantiate `JsonApiClient`, fetch a collection, iterate results; raw-response access. |
| [`get_resource_by_path.py`](./get_resource_by_path.py) | Resolve a front-end path to a resource via the Decoupled Router; handle the not-found case. |
| [`authenticated_and_cached.py`](./authenticated_and_cached.py) | Basic auth, an injected `InMemoryCache` (second call served from cache), and a custom logger. |
| [`async_reads.py`](./async_reads.py) | `AsyncJsonApiClient` via `async with` / `await` — collection + path resolution. |
| [`graphql_query.py`](./graphql_query.py) | `GraphqlClient.query()` with variables against a `/graphql` endpoint. |
