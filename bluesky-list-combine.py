import os
import requests
from datetime import datetime


class BlueskyAPI:
    def __init__(
        self, handle=None, app_password=None, api_uri="https://bsky.social/xrpc/"
    ):
        self.api_uri = api_uri
        self.account_did = None
        self.api_key = None
        if handle and app_password:
            self.login(handle, app_password)

    def login(self, handle, app_password):
        """Login to BSky to get DID and API Key."""
        data = {
            "identifier": handle,
            "password": app_password,
        }
        response = self.request("POST", "com.atproto.server.createSession", json=data)
        self.account_did = response.get("did")
        self.api_key = response.get("accessJwt")

    def request(self, method, endpoint, params=None, json=None):
        """Send an HTTP request to the BSky API."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if json is not None:
            headers["Content-Type"] = "application/json"
        url = f"{self.api_uri}{endpoint}"
        response = requests.request(
            method, url, params=params, json=json, headers=headers
        )
        response.raise_for_status()
        return response.json()

    def get_list_items(self, list_uri):
        """Retrieve all items from a source list."""
        items = []
        cursor = None
        while True:
            params = {"list": list_uri, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            response = self.request("GET", "app.bsky.graph.getList", params=params)
            items.extend(response.get("items", []))
            cursor = response.get("cursor")
            if not cursor:
                break
        return items

    def add_to_target_list(self, target_list, items):
        """Add items to the target list."""
        for item in items:
            record = {
                "collection": "app.bsky.graph.listitem",
                "repo": self.account_did,
                "record": {
                    "createdAt": datetime.utcnow().isoformat(),
                    "$type": "app.bsky.graph.listitem",
                    "subject": item["subject"]["did"],
                    "list": target_list,
                },
            }
            self.request("POST", "com.atproto.repo.createRecord", json=record)

    def resolve_list_uri(self, user_handle, list_id):
        """Resolve a list URI for a given handle and list ID."""
        params = {"actor": user_handle, "limit": 100}
        response = self.request("GET", "app.bsky.graph.getLists", params=params)
        for list_entry in response.get("lists", []):
            uri = list_entry["uri"]
            uri_list_id = uri.split("/")[-1]
            if uri_list_id == list_id:
                return uri
        raise ValueError(f"List with ID {list_id} not found for user {user_handle}.")


def import_list_to_target(source_url, target_url):
    """Main function to import one list into another."""
    # Parse the source and target list URLs
    source_parts = source_url.rstrip("/").split("/")
    target_parts = target_url.rstrip("/").split("/")

    source_user_handle = source_parts[-3]
    source_list_id = source_parts[-1]
    target_user_handle = target_parts[-3]
    target_list_id = target_parts[-1]

    # Initialize the BSky API client
    handle = os.environ.get("BSKY_HANDLE")
    app_password = os.environ.get("BSKY_APP_PASSWORD")
    if not handle or not app_password:
        raise EnvironmentError(
            "Please set BSKY_HANDLE and BSKY_APP_PASSWORD as environment variables."
        )

    bsky = BlueskyAPI(handle, app_password)

    # Resolve list URIs
    source_list_uri = bsky.resolve_list_uri(source_user_handle, source_list_id)
    target_list_uri = bsky.resolve_list_uri(target_user_handle, target_list_id)

    # Get items from the source list
    source_items = bsky.get_list_items(source_list_uri)

    # Add items to the target list
    bsky.add_to_target_list(target_list_uri, source_items)
    print("Import complete.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python script.py <source_list_url> <target_list_url>")
        sys.exit(1)

    source_url = sys.argv[1]
    target_url = sys.argv[2]

    import_list_to_target(source_url, target_url)
