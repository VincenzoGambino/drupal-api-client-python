"""Live integration tests against a real Drupal site.

Unlike the rest of the suite (mocked via ``respx``), these tests exercise
the client against an actual running Drupal instance. They are skipped
unless ``DRUPAL_API_CLIENT_LIVE_BASE_URL`` is set, e.g.::

    DRUPAL_API_CLIENT_LIVE_BASE_URL=https://drupal-headless.ddev.site \\
        pytest -m live

The target site is expected to have: the ``jsonapi`` core module, the
``decoupled_router`` contrib module enabled, and the Umami demo content
(see ``drupal-headless/`` — this suite was developed against it and
references its recipe/article content by real path alias).

GraphQL tests (``TestLiveGraphql``) additionally need ``graphql`` +
``graphql_compose`` with the article node type exposed and the anonymous
role granted the "execute ... arbitrary graphql requests" permission, so
that ``POST /graphql`` answers ``nodeArticle(id: ...)``. On a ddev Umami
site::

    ddev composer require drupal/graphql_compose  # 3.x-alpha for graphql 5.x
    ddev drush en graphql_compose graphql_compose_edges -y
    # expose node:article + its title field on the "graphql_compose_server"
    # config (graphql_compose.settings.graphql_compose_server), then:
    ddev drush role:perm:add anonymous \
        "execute graphql_compose_server arbitrary graphql requests"
    ddev drush cr

Write tests (``TestLiveWrites``) additionally require credentials, supplied
via ``DRUPAL_API_CLIENT_LIVE_USERNAME`` / ``DRUPAL_API_CLIENT_LIVE_PASSWORD``,
for a user permitted to create/edit/delete article content **and** use the
editorial ``create_new_draft`` transition (Umami puts articles under content
moderation). On a ddev Umami site you can provision one with::

    ddev drush user:create apitest --mail=apitest@example.com --password=PW
    ddev drush role:create api_test
    ddev drush role:perm:add api_test "access content,create article content,\
edit any article content,delete any article content,\
use editorial transition create_new_draft,use editorial transition publish"
    ddev drush user:role:add api_test apitest

OAuth tests (``TestLiveOAuth``) require Simple OAuth 6.x + Consumers, a key
pair, a scope and a confidential consumer using the ``client_credentials``
grant. Supply the consumer via ``DRUPAL_API_CLIENT_LIVE_CLIENT_ID`` /
``DRUPAL_API_CLIENT_LIVE_CLIENT_SECRET``. On a ddev site::

    ddev composer require drupal/simple_oauth  # pulls drupal/consumers
    ddev drush en simple_oauth consumers -y

    # 1. Key pair, OUTSIDE the webroot (web/ is the docroot):
    ddev exec 'mkdir -p /var/www/html/keys \
        && openssl genrsa -out /var/www/html/keys/private.key 2048 \
        && openssl rsa -in /var/www/html/keys/private.key -pubout \
             -out /var/www/html/keys/public.key \
        && chmod 600 /var/www/html/keys/private.key'
    ddev drush config:set simple_oauth.settings \
        public_key /var/www/html/keys/public.key -y
    ddev drush config:set simple_oauth.settings \
        private_key /var/www/html/keys/private.key -y

    # 2. A role, an oauth2_scope bound to it, and a consumer acting as a
    #    user holding that role. Simple OAuth 6.x models scopes as config
    #    entities with a granularity plugin (role or permission) - the 5.x
    #    "pick roles on the consumer" UI is gone.
    #    See the drush ev snippet in the project's CHANGELOG for 0.3.0.

    ddev drush cr

.. note::

   Simple OAuth **6.x removed the ``password`` grant** (only
   AuthorizationCode / ClientCredentials / RefreshToken plugins ship). The
   client still supports it for 5.x sites and other OAuth2 servers, but it
   cannot be covered by these live tests against a 6.x target - it stays
   mock-only in ``test_oauth.py``.

Then run, e.g.::

    DRUPAL_API_CLIENT_LIVE_BASE_URL=https://drupal-headless.ddev.site \\
    DRUPAL_API_CLIENT_LIVE_USERNAME=apitest \\
    DRUPAL_API_CLIENT_LIVE_PASSWORD=PW \\
    DRUPAL_API_CLIENT_LIVE_CLIENT_ID=my_consumer \\
    DRUPAL_API_CLIENT_LIVE_CLIENT_SECRET=my_secret \\
        pytest -m live

These tests exist because the mocked suite uses fixtures that can
silently drift from what the real API actually returns (see the
ResolvedPath.resolved fix in the CHANGELOG, which mocked tests never
caught). Prefer adding a case here whenever a fixture is suspect.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

from drupal_api_client import (
    AsyncJsonApiClient,
    BasicAuth,
    DefaultSerializer,
    GraphqlClient,
    JsonApiClient,
    OAuthAuth,
    Resource,
    ResolvedPath,
    ResourceCollection,
    ResourceNotFoundError,
    UnresolvedPath,
)

LIVE_BASE_URL = os.environ.get("DRUPAL_API_CLIENT_LIVE_BASE_URL")
LIVE_USERNAME = os.environ.get("DRUPAL_API_CLIENT_LIVE_USERNAME")
LIVE_PASSWORD = os.environ.get("DRUPAL_API_CLIENT_LIVE_PASSWORD")
LIVE_CLIENT_ID = os.environ.get("DRUPAL_API_CLIENT_LIVE_CLIENT_ID")
LIVE_CLIENT_SECRET = os.environ.get("DRUPAL_API_CLIENT_LIVE_CLIENT_SECRET")

# OAuth tests need Simple OAuth 6.x configured with a confidential consumer
# using the client_credentials grant. See the module docstring.
requires_oauth_credentials = pytest.mark.skipif(
    not (LIVE_BASE_URL and LIVE_CLIENT_ID and LIVE_CLIENT_SECRET),
    reason=(
        "Set DRUPAL_API_CLIENT_LIVE_CLIENT_ID/_CLIENT_SECRET (plus _BASE_URL) "
        "to a Simple OAuth consumer to run live OAuth tests."
    ),
)

# Write tests additionally require credentials for a user permitted to
# create/edit/delete article content (and, with Umami's editorial workflow,
# to use the create_new_draft transition).
requires_write_credentials = pytest.mark.skipif(
    not (LIVE_BASE_URL and LIVE_USERNAME and LIVE_PASSWORD),
    reason=(
        "Set DRUPAL_API_CLIENT_LIVE_USERNAME/_PASSWORD (plus _BASE_URL) to a "
        "user with article CRUD + editorial-transition permissions to run "
        "live write tests."
    ),
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not LIVE_BASE_URL,
        reason=(
            "Set DRUPAL_API_CLIENT_LIVE_BASE_URL to run live integration "
            "tests against a real Drupal site."
        ),
    ),
]


@pytest.fixture
def client():
    # ddev serves a locally-trusted (mkcert) cert that isn't necessarily
    # in the system/Python trust store; verify=False is fine for local
    # ddev testing only - never do this against a real remote site.
    http_client = httpx.Client(verify=False)
    with JsonApiClient(LIVE_BASE_URL, http_client=http_client) as c:
        yield c


@pytest.fixture
def index_lookup_client():
    http_client = httpx.Client(verify=False)
    with JsonApiClient(
        LIVE_BASE_URL, http_client=http_client, index_lookup=True
    ) as c:
        yield c


@pytest.fixture
def serializer_client():
    http_client = httpx.Client(verify=False)
    with JsonApiClient(
        LIVE_BASE_URL, http_client=http_client, serializer=DefaultSerializer()
    ) as c:
        yield c


class TestLiveGetCollection:
    def test_get_recipe_collection(self, client: JsonApiClient) -> None:
        result = client.get_collection(
            "node--recipe", query_string="page[limit]=1"
        )
        assert isinstance(result, dict)
        assert len(result["data"]) == 1
        assert result["data"][0]["type"] == "node--recipe"


class TestLiveGetResource:
    def test_get_resource_by_uuid(self, client: JsonApiClient) -> None:
        collection = client.get_collection(
            "node--recipe", query_string="page[limit]=1"
        )
        resource_id = collection["data"][0]["id"]

        result = client.get_resource("node--recipe", resource_id)
        assert result["data"]["id"] == resource_id
        assert "title" in result["data"]["attributes"]


class TestLiveGetResourceByPath:
    def test_resolves_real_recipe_alias(self, client: JsonApiClient) -> None:
        result = client.get_resource_by_path(
            "/recipes/borscht-with-pork-ribs"
        )
        assert result["data"]["type"] == "node--recipe"
        assert (
            result["data"]["attributes"]["title"] == "Borscht with pork ribs"
        )

    def test_raises_on_unresolvable_path(self, client: JsonApiClient) -> None:
        with pytest.raises(ResourceNotFoundError):
            client.get_resource_by_path("/this-path-does-not-exist-xyz")


class TestLiveDecoupledRouter:
    def test_resolved_path_resolved_field_is_url_string(
        self, client: JsonApiClient
    ) -> None:
        # Regression test for the ResolvedPath.resolved type fix: the
        # real Decoupled Router response's `resolved` field is the
        # canonical URL, not a boolean (see CHANGELOG). This is exactly
        # the mismatch the mocked test suite could not catch, since its
        # fixtures were hand-written rather than captured from a real
        # response.
        router_response = client.router.translate_path(
            "/recipes/borscht-with-pork-ribs"
        )
        assert isinstance(router_response, ResolvedPath)
        assert isinstance(router_response.resolved, str)
        assert router_response.resolved.startswith("http")
        assert router_response.entity["bundle"] == "recipe"

    def test_unresolved_path_returns_dataclass(
        self, client: JsonApiClient
    ) -> None:
        router_response = client.router.translate_path(
            "/this-path-does-not-exist-xyz"
        )
        assert isinstance(router_response, UnresolvedPath)
        assert router_response.message is not None


class TestLiveIndexLookupPerLocale:
    """Regression test for the locale-blind index cache fix (see
    CHANGELOG): the real Umami demo content has an 'es' translation for
    the recipe used elsewhere in this module, with a distinct title and
    an /es/jsonapi/... self link.
    """

    def test_locale_affects_index_resolved_content(
        self, index_lookup_client: JsonApiClient
    ) -> None:
        client = index_lookup_client
        en_result = client.get_collection(
            "node--recipe", query_string="page[limit]=1"
        )
        es_result = client.get_collection(
            "node--recipe", locale="es", query_string="page[limit]=1"
        )

        assert set(client._index_cache.keys()) == {None, "es"}
        en_title = en_result["data"][0]["attributes"]["title"]
        es_title = es_result["data"][0]["attributes"]["title"]
        assert en_title != es_title
        assert "/es/jsonapi/" in es_result["data"][0]["links"]["self"]["href"]


class TestLiveDefaultSerializer:
    """Exercises DefaultSerializer against real Umami JSON:API documents,
    including relationship inlining from `included` — the case fixtures are
    least likely to capture faithfully."""

    def test_collection_flattens_and_exposes_links(
        self, serializer_client: JsonApiClient
    ) -> None:
        result = serializer_client.get_collection(
            "node--recipe", query_string="page[limit]=1"
        )
        assert isinstance(result, ResourceCollection)
        recipe = result[0]
        assert isinstance(recipe, Resource)
        # Attributes hoisted; no JSON:API `attributes` wrapper.
        assert "title" in recipe
        assert "attributes" not in recipe
        # Collection carries document-level links (self/next/...).
        assert result.get_links() is not None

    def test_included_relationship_is_inlined(
        self, serializer_client: JsonApiClient
    ) -> None:
        # Fetch one recipe with its media image included, so the serializer
        # can resolve the relationship from `included` into a nested Resource.
        collection = serializer_client.get_collection(
            "node--recipe", query_string="page[limit]=1"
        )
        uuid = collection[0]["id"]
        recipe = serializer_client.get_resource(
            "node--recipe",
            uuid,
            query_string="include=field_media_image",
        )
        assert isinstance(recipe, Resource)
        media = recipe["field_media_image"]
        # Included → resolved to a flattened Resource (not a bare
        # {"type","id"} identifier).
        assert isinstance(media, Resource)
        assert media["type"].startswith("media--")


class TestLiveAsync:
    """The async clients against the real site (same endpoints as sync)."""

    async def test_async_get_collection(self) -> None:
        http_client = httpx.AsyncClient(verify=False)
        async with AsyncJsonApiClient(
            LIVE_BASE_URL, http_client=http_client
        ) as client:
            result = await client.get_collection(
                "node--recipe", query_string="page[limit]=1"
            )
        assert result["data"][0]["type"] == "node--recipe"
        await http_client.aclose()

    async def test_async_get_resource_by_path(self) -> None:
        http_client = httpx.AsyncClient(verify=False)
        async with AsyncJsonApiClient(
            LIVE_BASE_URL, http_client=http_client
        ) as client:
            result = await client.get_resource_by_path(
                "/recipes/borscht-with-pork-ribs"
            )
        assert result["data"]["attributes"]["title"] == "Borscht with pork ribs"
        await http_client.aclose()

    async def test_async_unresolved_path_raises(self) -> None:
        http_client = httpx.AsyncClient(verify=False)
        async with AsyncJsonApiClient(
            LIVE_BASE_URL, http_client=http_client
        ) as client:
            with pytest.raises(ResourceNotFoundError):
                await client.get_resource_by_path("/this-path-does-not-exist-xyz")
        await http_client.aclose()


class TestLiveGraphql:
    """GraphqlClient against the real GraphQL Compose endpoint (/graphql).

    Requires the ``graphql`` + ``graphql_compose`` modules with the article
    node type exposed and anonymous granted "execute ... arbitrary graphql
    requests". Skipped with the rest of the live suite when
    DRUPAL_API_CLIENT_LIVE_BASE_URL is unset.
    """

    @pytest.fixture
    def article_uuid(self, client: JsonApiClient) -> str:
        collection = client.get_collection(
            "node--article", query_string="page[limit]=1"
        )
        return collection["data"][0]["id"]

    def test_query_article_by_id(self, article_uuid: str) -> None:
        http_client = httpx.Client(verify=False)
        with GraphqlClient(LIVE_BASE_URL, http_client=http_client) as gql:
            result = gql.query(
                '{ nodeArticle(id: "%s") { id title } }' % article_uuid
            )
        http_client.close()
        assert result["data"]["nodeArticle"]["id"] == article_uuid
        assert result["data"]["nodeArticle"]["title"]

    def test_query_with_variables(self, article_uuid: str) -> None:
        # Exercises the client's variables= (a superset over the JS client).
        http_client = httpx.Client(verify=False)
        with GraphqlClient(LIVE_BASE_URL, http_client=http_client) as gql:
            result = gql.query(
                "query GetArticle($id: ID!) { nodeArticle(id: $id) { title } }",
                variables={"id": article_uuid},
            )
        http_client.close()
        assert result["data"]["nodeArticle"]["title"]


@requires_write_credentials
class TestLiveWrites:
    """Full create → update → delete lifecycle against the real site using
    Basic auth. Requires the credential env vars (see module docstring)."""

    @pytest.fixture
    def authed_client(self):
        http_client = httpx.Client(verify=False)
        with JsonApiClient(
            LIVE_BASE_URL,
            http_client=http_client,
            authentication=BasicAuth(
                username=LIVE_USERNAME, password=LIVE_PASSWORD
            ),
        ) as c:
            yield c

    def test_create_update_delete_lifecycle(
        self, authed_client: JsonApiClient
    ) -> None:
        client = authed_client
        # `moderation_state: draft` is required by Umami's editorial workflow.
        create_body = {
            "data": {
                "type": "node--article",
                "attributes": {
                    "title": "drupal-api-client live write test",
                    "moderation_state": "draft",
                },
            }
        }
        created = client.create_resource(
            "node--article", create_body, raw_response=True
        )
        assert created.response.status_code == 201
        uuid = created.json["data"]["id"]

        try:
            assert (
                created.json["data"]["attributes"]["title"]
                == "drupal-api-client live write test"
            )

            update_body = {
                "data": {
                    "type": "node--article",
                    "id": uuid,
                    "attributes": {"title": "edited by live write test"},
                }
            }
            updated = client.update_resource(
                "node--article", uuid, update_body, raw_response=True
            )
            assert updated.response.status_code == 200
            assert (
                updated.json["data"]["attributes"]["title"]
                == "edited by live write test"
            )
        finally:
            # Always clean up the node, even if an assertion above failed.
            deleted = client.delete_resource(
                "node--article", uuid, raw_response=True
            )
            assert deleted.response.status_code == 204

        # After a successful delete, the resource is gone (404).
        gone = client.get_resource(
            "node--article", uuid, raw_response=True
        )
        assert gone.response.status_code == 404


@requires_oauth_credentials
class TestLiveOAuth:
    """OAuth2 client_credentials against a real Simple OAuth 6.x install.

    The mocked OAuth suite (`test_oauth.py`) asserts against a hand-written
    token response. This class is what proves that response shape is real:
    `_get_access_token` reads `access_token`, `expires_in` and `token_type`
    with unguarded subscripts, so a server that named them differently would
    raise KeyError in production while every mocked test stayed green.

    Note: Simple OAuth 6.x removed the `password` grant (only
    AuthorizationCode/ClientCredentials/RefreshToken plugins ship), so the
    client's password-grant path cannot be covered here. It remains
    mock-only against a 6.x site.
    """

    @pytest.fixture
    def oauth_client(self):
        http_client = httpx.Client(verify=False)
        with JsonApiClient(
            LIVE_BASE_URL,
            http_client=http_client,
            authentication=OAuthAuth(
                client_id=LIVE_CLIENT_ID,
                client_secret=LIVE_CLIENT_SECRET,
                grant_type="client_credentials",
            ),
        ) as c:
            yield c

    def test_token_response_shape_is_what_the_client_assumes(
        self, oauth_client: JsonApiClient
    ) -> None:
        oauth_client.get_collection("node--article")

        token = oauth_client._oauth_token_response
        assert token is not None
        # The three keys _get_access_token subscripts without a guard.
        assert token.access_token
        assert token.token_type == "Bearer"
        # expires_in is seconds, so valid_until must be a near-future epoch
        # in seconds - not milliseconds (the JS client uses ms).
        now = time.time()
        assert now < token.valid_until < now + 86400

    def test_authorization_header_is_bearer(
        self, oauth_client: JsonApiClient
    ) -> None:
        oauth_client.get_collection("node--article")
        headers = oauth_client.add_authorization_header({})
        assert headers["Authorization"].startswith("Bearer ")

    def test_token_is_reused_across_requests(
        self, oauth_client: JsonApiClient
    ) -> None:
        oauth_client.get_collection("node--article")
        first = oauth_client._oauth_token_response.access_token
        oauth_client.get_collection("node--article", disable_cache=True)
        assert oauth_client._oauth_token_response.access_token == first

    def test_oauth_write_lifecycle(self, oauth_client: JsonApiClient) -> None:
        """create -> update -> delete authenticated purely by OAuth."""
        client = oauth_client
        created = client.create_resource(
            "node--article",
            {
                "data": {
                    "type": "node--article",
                    "attributes": {
                        "title": "drupal-api-client live oauth test",
                        "moderation_state": "draft",
                    },
                }
            },
            raw_response=True,
        )
        assert created.response.status_code == 201
        uuid = created.json["data"]["id"]

        try:
            updated = client.update_resource(
                "node--article",
                uuid,
                {
                    "data": {
                        "type": "node--article",
                        "id": uuid,
                        "attributes": {"title": "edited by live oauth test"},
                    }
                },
                raw_response=True,
            )
            assert updated.response.status_code == 200
            assert (
                updated.json["data"]["attributes"]["title"]
                == "edited by live oauth test"
            )
        finally:
            deleted = client.delete_resource(
                "node--article", uuid, raw_response=True
            )
            assert deleted.response.status_code == 204
