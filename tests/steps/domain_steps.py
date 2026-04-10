"""Step definitions for domain-allowlist.feature.

Each scenario that requires a specific server config spins up an in-process
FastAPI TestClient with the right settings rather than relying on the live server.
"""
import tempfile
import time
from pathlib import Path

from behave import given, when, then
from fastapi.testclient import TestClient

from gpgchain.api.app import create_app
from tests.steps.key_steps import _ensure_keys, _name_from_uid, _submit_key

_PROJECT_TMP = Path(__file__).parent.parent.parent / "tmp"
_PROJECT_TMP.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# In-process client wrapper (mirrors APIClient interface)
# ---------------------------------------------------------------------------

class _InProcessClient:
    """Wraps a FastAPI TestClient to look like APIClient."""

    def __init__(self, tc: TestClient):
        self._tc = tc
        self.last_response = None

    def add_block(self, armored_key: str, self_sig: str, submit_timestamp: int = None):
        body = {"armored_key": armored_key, "self_sig": self_sig}
        if submit_timestamp is not None:
            body["submit_timestamp"] = submit_timestamp
        self.last_response = self._tc.post("/block", json=body)
        return self.last_response

    def get_block(self, fingerprint: str):
        self.last_response = self._tc.get(f"/block/{fingerprint}")
        return self.last_response

    def get_blocks(self):
        self.last_response = self._tc.get("/blocks")
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

    def search(self, query):
        self.last_response = self._tc.get("/search", params={"q": query})
        return self.last_response


def _make_in_process_client(domains=None, allow_all=False):
    tmpdir = tempfile.mkdtemp(dir=_PROJECT_TMP)
    app = create_app(
        store_dir=tmpdir,
        domains=domains or [],
        allow_all_domains=allow_all,
    )
    tc = TestClient(app, raise_server_exceptions=False)
    return _InProcessClient(tc)


# ---------------------------------------------------------------------------
# Givens – server config
# ---------------------------------------------------------------------------

@given("the node has an empty domain allowlist")
def step_node_empty_allowlist(context):
    context._saved_client = context.client
    context.client = _make_in_process_client(domains=[], allow_all=False)


@given("the node is configured with allow_all_domains")
def step_node_allow_all(context):
    context._saved_client = context.client
    context.client = _make_in_process_client(domains=[], allow_all=True)


@given('the node allows domain "{domain}"')
def step_node_allows_domain(context, domain):
    context._saved_client = context.client
    context.client = _make_in_process_client(domains=[domain], allow_all=False)


@given('a block for "{uid}" is gossiped to the node')
def step_block_gossiped(context, uid):
    _ensure_keys(context)
    name = _name_from_uid(uid)
    if name not in context.keys:
        context.keys[name] = context.gpg.generate_key(uid)
    context.gossiped_name = name
    ts = int(time.time())
    key = context.keys[name]
    sig = context.gpg.sign_submit_payload(
        key["armored_public"], key["armored_private"], key["fingerprint"], ts,
        homedir=key.get("homedir"),
    )
    context.client.add_block(key["armored_public"], sig, submit_timestamp=ts)


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------

@then("the node does not store the block")
def step_node_does_not_store(context):
    name = context.gossiped_name
    fp = context.keys[name]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 404, (
        f"Expected block to be absent (404) but got {resp.status_code}"
    )


@then("GET /block/<Bob's fingerprint> returns status 404")
def step_bob_block_404(context):
    _ensure_keys(context)
    fp = context.keys["bob"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
