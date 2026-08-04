# Shared golden fixtures

These JSON files are copied **verbatim** from the JavaScript source-of-truth
client's test corpus:

- `js_api_client/packages/json-api-client/tests/mocks/data/`
- `js_api_client/packages/decoupled-router-client/tests/mocks/data/`

They exist so the Python client is exercised against **byte-identical** server
payloads to the JS client. Testing both ports against the same golden data is how
we catch silent cross-language drift (a mistyped field, a wrong response shape).
See the porting guide's `05-testing.md` in the JS repo.

## Do not hand-edit

Treat these as read-only. If the upstream JS fixtures change, re-copy them rather
than editing here, so the two corpora stay in sync.

## What was and wasn't copied

Copied: the **raw** JSON:API request/response fixtures a passthrough client
consumes — collections, single resources, views, create/update request+response
pairs, the JSON:API index, error bodies, and the Decoupled Router
resolved/unresolved responses.

Also copied: `get-articles.json` (GraphQL), used by `test_graphql.py` /
`test_async.py`.

**Not** copied: the JS-serializer-specific outputs
(`*-deserialize-jsona.json`, `*-deserialize-jsonapi-serializer.json`,
`*-reserialize-jsona.json`). Those are outputs of the JS `DefaultSerializer` /
`jsona` flattening; the Python `DefaultSerializer` follows the JSON:API spec
generically rather than reproducing every `jsona` quirk byte-for-byte, so its
tests assert structural equivalence (see `test_serializer.py`) rather than
matching those exact files.

## Loading

Use the `load_fixture` helper / `fixture` pytest fixture from
`tests/conftest.py`:

```python
def test_something(fixture):
    body = fixture("node-recipe.json")
```
