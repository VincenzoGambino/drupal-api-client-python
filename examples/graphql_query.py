"""Run a GraphQL query with GraphqlClient.

Requires a GraphQL endpoint on the Drupal site (e.g. the `graphql` +
`graphql_compose` modules, which publish a server at `/graphql`).

Run:
    python examples/graphql_query.py
"""

from __future__ import annotations

from _shared import base_url

from drupal_api_client import GraphqlClient


def main() -> None:
    with GraphqlClient(base_url()) as client:
        # A query with variables (the client sends {"query": ..., "variables": ...}).
        result = client.query(
            "query GetArticle($id: ID!) { nodeArticle(id: $id) { id title } }",
            variables={"id": "REPLACE-WITH-A-REAL-ARTICLE-UUID"},
        )

        # GraphQL returns 200 with an `errors` array for query-level errors;
        # like the JS client, query() returns the raw body for you to inspect.
        if result.get("errors"):
            print("GraphQL errors:", result["errors"])
            return

        article = result["data"]["nodeArticle"]
        print("Article:", article["title"], f"({article['id']})")


if __name__ == "__main__":
    main()
