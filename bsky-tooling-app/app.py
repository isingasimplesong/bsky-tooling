from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"


class BlueskyApi:
    def __init__(
        self, handle=None, app_password=None, api_uri="https://bsky.social/xrpc/"
    ):
        self.api_uri = api_uri
        self.account_did = None
        self.api_key = None

        if handle and app_password:
            # Authenticate and fetch DID + API Key
            payload = {"identifier": handle, "password": app_password}
            response = self._request(
                "POST", "com.atproto.server.createSession", payload
            )
            self.account_did = response.get("did")
            self.api_key = response.get("accessJwt")

    def _request(self, method, endpoint, payload=None):
        """Internal HTTP request function."""
        url = self.api_uri + endpoint
        headers = {}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if method == "POST":
            headers["Content-Type"] = "application/json"
            response = requests.post(url, headers=headers, json=payload)
        elif method == "GET":
            response = requests.get(url, headers=headers, params=payload)
        else:
            raise ValueError("Unsupported HTTP Method")

        response.raise_for_status()  # Raise exceptions for HTTP errors
        return response.json()

    def fetch_list_uri(self, handle, starter_pack_id):
        """Fetch the `list` URI for a given starter pack."""
        payload = {"actor": handle}
        data = self._request("GET", "app.bsky.graph.getActorStarterPacks", payload)

        for pack in data.get("starterPacks", []):
            if pack.get("uri", "").endswith(starter_pack_id):
                pack_details = self._request(
                    "GET", "app.bsky.graph.getStarterPack", {"starterPack": pack["uri"]}
                )
                return pack_details.get("starterPack", {}).get("list", {}).get("uri")
        return None

    def merge_starter_pack(self, target_pack_uri, source_list_uri):
        """Merge accounts from a source list into a target starter pack."""
        # Fetch all accounts in the source list
        cursor = ""
        source_items = []

        while True:
            payload = {"list": source_list_uri, "limit": 100, "cursor": cursor}
            data = self._request("GET", "app.bsky.graph.getList", payload)
            source_items.extend(data.get("items", []))
            cursor = data.get("cursor")
            if not cursor:
                break

        # Add accounts to the target starter pack
        if source_items:
            for item in source_items:
                payload = {
                    "collection": "app.bsky.graph.listitem",
                    "repo": self.account_did,
                    "record": {
                        "$type": "app.bsky.graph.listitem",
                        "createdAt": datetime.utcnow().isoformat()
                        + "Z",  # ISO 8601 format
                        "subject": item["subject"]["did"],
                        "list": target_pack_uri,
                    },
                }
                self._request("POST", "com.atproto.repo.createRecord", payload)
        else:
            raise ValueError("Source list is empty or invalid.")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        handle = request.form["handle"]
        app_password = request.form["apppassword"]
        target_pack_url = request.form["packurl"]
        source_pack_url = request.form["packsrcurl"]

        # Extract handle and ID from URLs
        try:
            target_user, target_id = target_pack_url.strip("/").split("/")[-2:]
            source_user, source_id = source_pack_url.strip("/").split("/")[-2:]

            # Initialize Bluesky API
            bsky = BlueskyApi(handle, app_password)

            # Fetch `at` URIs for both starter packs
            target_pack_uri = bsky.fetch_list_uri(target_user, target_id)
            source_list_uri = bsky.fetch_list_uri(source_user, source_id)

            if not target_pack_uri or not source_list_uri:
                flash(
                    "Error: Unable to find one of the specified starter packs or lists.",
                    "danger",
                )
                return redirect(url_for("index"))

            # Merge the packs
            bsky.merge_starter_pack(target_pack_uri, source_list_uri)
            flash("Successfully merged the starter packs!", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

        return redirect(url_for("index"))

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
