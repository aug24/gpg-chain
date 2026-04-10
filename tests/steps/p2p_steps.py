"""Step definitions for p2p-peers.feature (basic peer registration)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from behave import given, when, then
from fastapi.testclient import TestClient

from gpgchain.api.app import create_app
from tests.steps.key_steps import _ensure_keys

_PROJECT_TMP = Path(__file__).parent.parent.parent / "tmp"
_PROJECT_TMP.mkdir(parents=True, exist_ok=True)

# Fake URLs used for in-process peer tests (not real loopback checks)
_NODE_A_URL = "http://node-a.gpgchain.test"
_NODE_B_URL = "http://node-b.gpgchain.test"


class _InProcessClient:
    """Wraps a FastAPI TestClient for peer-endpoint use."""

    def __init__(self, tc: TestClient):
        self._tc = tc
        self.last_response = None

    def add_peer(self, addr: str):
        self.last_response = self._tc.post("/peers", json={"addr": addr})
        return self.last_response

    def get_peers(self):
        self.last_response = self._tc.get("/peers")
        return self.last_response

    def add_block(self, armored_key, self_sig, submit_timestamp=None):
        body = {"armored_key": armored_key, "self_sig": self_sig}
        if submit_timestamp is not None:
            body["submit_timestamp"] = submit_timestamp
        self.last_response = self._tc.post("/block", json=body)
        return self.last_response

    def get_block(self, fp):
        self.last_response = self._tc.get(f"/block/{fp}")
        return self.last_response

    def get_blocks(self):
        self.last_response = self._tc.get("/blocks")
        return self.last_response

    def search(self, query):
        self.last_response = self._tc.get("/search", params={"q": query})
        return self.last_response

    def sign_block(self, fingerprint, signer_fingerprint, sig,
                   timestamp=None, signer_armored_key="", source_node=""):
        body = {"signer_fingerprint": signer_fingerprint, "sig": sig}
        if timestamp is not None:
            body["timestamp"] = timestamp
        if signer_armored_key:
            body["signer_armored_key"] = signer_armored_key
        if source_node:
            body["source_node"] = source_node
        self.last_response = self._tc.post(f"/block/{fingerprint}/sign", json=body)
        return self.last_response

    def revoke_block(self, fingerprint, sig):
        self.last_response = self._tc.post(f"/block/{fingerprint}/revoke", json={"sig": sig})
        return self.last_response


def _make_peer_clients():
    """Create two in-process nodes that can register as peers via mocked httpx."""
    dir_a = tempfile.mkdtemp(dir=_PROJECT_TMP)
    dir_b = tempfile.mkdtemp(dir=_PROJECT_TMP)
    app_a = create_app(store_dir=dir_a, allow_all_domains=True, node_url=_NODE_A_URL)
    app_b = create_app(store_dir=dir_b, allow_all_domains=True, node_url=_NODE_B_URL)
    tc_a = TestClient(app_a, raise_server_exceptions=False)
    tc_b = TestClient(app_b, raise_server_exceptions=False)
    return _InProcessClient(tc_a), _InProcessClient(tc_b)


def _add_peer_in_process(client_a: _InProcessClient, client_b: _InProcessClient, url_b: str):
    """Register url_b as a peer of client_a, mocking the reachability check and IP validation."""
    with patch("gpgchain.api.routes.socket.getaddrinfo") as mock_getaddrinfo, \
         patch("gpgchain.api.routes.httpx.get") as mock_httpx_get:
        # Bypass IP resolution check — pretend hostname resolves to a public IP
        mock_getaddrinfo.return_value = [
            (None, None, None, None, ("93.184.216.34", None))  # public IP
        ]
        # Serve the reachability check from client_b
        peers_resp = client_b._tc.get("/peers")

        class _MockResponse:
            status_code = peers_resp.status_code

        mock_httpx_get.return_value = _MockResponse()
        result = client_a.add_peer(url_b)
    return result


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------

@given("two nodes A and B are running")
def step_two_nodes_running(context):
    client_a, client_b = _make_peer_clients()
    context._node_a = client_a
    context._node_b = client_b
    context.node_b_url = _NODE_B_URL
    context._saved_client = context.client
    context.client = client_a


@given("the node's peer list is full")
def step_peer_list_full(context):
    # Fill the live node's peer list directly (skipped — use in-process)
    context.peer_list_assumed_full = True


@given("node B is already in node A's peer list")
def step_node_b_in_peer_list(context):
    client_a, client_b = _make_peer_clients()
    context._node_a = client_a
    context._node_b = client_b
    context.node_b_url = _NODE_B_URL
    context._saved_client = context.client
    context.client = client_a
    # Register node B with node A
    _add_peer_in_process(client_a, client_b, _NODE_B_URL)


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------

@when("node A registers node B as a peer")
def step_node_a_registers_b(context):
    client_a = getattr(context, "_node_a", None)
    client_b = getattr(context, "_node_b", None)
    if client_a and client_b:
        _add_peer_in_process(client_a, client_b, context.node_b_url)
    else:
        context.client.add_peer(context.node_b_url)


@when("a node attempts to register an unreachable URL as a peer")
def step_register_unreachable(context):
    context.client.add_peer("http://unreachable.invalid:9999")


@when('a node attempts to register "{addr}" as a peer')
def step_register_private_ip(context, addr):
    context.client.add_peer(addr)


@when("a new peer attempts to register")
def step_new_peer_registers(context):
    if getattr(context, "peer_list_assumed_full", False):
        # Use an in-process node with a full peer list
        from gpgchain.api.routes import MAX_PEERS
        tmpdir = tempfile.mkdtemp(dir=_PROJECT_TMP)
        app = create_app(store_dir=tmpdir, allow_all_domains=True)
        # Directly fill the peer list
        app.state.peer_list = [f"http://peer{i}.example.com" for i in range(MAX_PEERS)]
        tc = TestClient(app, raise_server_exceptions=False)
        client = _InProcessClient(tc)
        context._saved_client = context.client
        context.client = client
        # Capacity check happens before IP check and reachability — no mocking needed
        context.client.add_peer("http://new-peer.example.com:8080")
    else:
        context.client.add_peer("http://new-peer.example.com:8080")


@when("node B registers with node A again")
def step_node_b_registers_again(context):
    client_a = getattr(context, "_node_a", None)
    client_b = getattr(context, "_node_b", None)
    if client_a and client_b:
        _add_peer_in_process(client_a, client_b, context.node_b_url)
    else:
        context.client.add_peer(context.node_b_url)


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------

@then("node A lists node B in its peer list")
def step_node_a_lists_b(context):
    client_a = getattr(context, "_node_a", context.client)
    resp = client_a.get_peers()
    assert resp.status_code == 200, f"GET /peers failed: {resp.status_code}"
    body = resp.json()
    peers = body if isinstance(body, list) else body.get("peers", [])
    assert context.node_b_url in peers, (
        f"Node B ({context.node_b_url}) not in peer list: {peers}"
    )


@then("node B appears only once in node A's peer list")
def step_node_b_appears_once(context):
    client_a = getattr(context, "_node_a", context.client)
    resp = client_a.get_peers()
    assert resp.status_code == 200
    body = resp.json()
    peers = body if isinstance(body, list) else body.get("peers", [])
    count = peers.count(context.node_b_url)
    assert count == 1, (
        f"Node B appears {count} times in peer list, expected exactly 1: {peers}"
    )
