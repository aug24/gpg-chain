"""Step definitions for revocation.feature."""
import time

from behave import given, when, then

from tests.steps.key_steps import _ensure_keys, _put_key_on_ledger
from tests.steps.signing_steps import _sign_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_block_hash(context, name: str, client=None) -> str:
    if client is None:
        client = context.client
    fp = context.keys[name]["fingerprint"]
    resp = client.get_block(fp)
    assert resp.status_code == 200, f"Block for {name} not found: {resp.status_code}"
    return resp.json()["hash"]


def _revoke_key(context, name: str, client=None) -> None:
    """Perform a valid revocation for *name*."""
    if client is None:
        client = context.client
    key = context.keys[name]
    block_hash = _get_block_hash(context, name, client=client)
    sig = context.gpg.sign_revoke_payload(
        key["fingerprint"], block_hash, key["armored_private"],
        homedir=key.get("homedir"),
    )
    client.revoke_block(key["fingerprint"], sig)


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------

@given("Alice's key is on the ledger and revoked")
def step_alice_on_ledger_and_revoked(context):
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
    _put_key_on_ledger(context, "alice")
    _revoke_key(context, "alice")


@given("Alice's key is on the ledger and already revoked")
def step_alice_already_revoked(context):
    step_alice_on_ledger_and_revoked(context)


@given("Alice's key has been revoked")
def step_alice_key_revoked(context):
    _revoke_key(context, "alice")


@given("Bob's key has been revoked")
def step_bob_key_revoked(context):
    _revoke_key(context, "bob")


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------

@when("Alice revokes her key with a valid revocation signature")
def step_alice_revokes_valid(context):
    _revoke_key(context, "alice")


@when("Alice revokes her key")
def step_alice_revokes(context):
    _revoke_key(context, "alice")


@when("Bob attempts to revoke Alice's key")
def step_bob_attempts_revoke_alice(context):
    """Bob signs the revoke payload with *his own* key but for *Alice's* fingerprint."""
    alice_fp = context.keys["alice"]["fingerprint"]
    block_hash = _get_block_hash(context, "alice")
    bob = context.keys["bob"]
    # Sign with Bob's private key but using Alice's fingerprint in the payload
    sig = context.gpg.sign_revoke_payload(alice_fp, block_hash, bob["armored_private"],
                                           homedir=bob.get("homedir"))
    context.client.revoke_block(alice_fp, sig)


@when("Alice submits a corrupted revocation signature")
def step_alice_corrupted_revoke(context):
    fp = context.keys["alice"]["fingerprint"]
    context.client.revoke_block(fp, "bm90YXZhbGlkc2ln")


@when("Alice attempts to revoke her key again")
def step_alice_revokes_again(context):
    _revoke_key(context, "alice")


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------

@then("Alice's block is marked revoked")
def step_alice_block_revoked(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200
    assert resp.json().get("revoked") is True, f"Block not marked revoked: {resp.json()}"


@then("GET /block/<Alice's fingerprint> returns status 200")
def step_alice_block_still_200(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@then("the block has revoked set to true")
def step_block_revoked_true(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.json().get("revoked") is True, f"revoked not true: {resp.json()}"


@when("Bob attempts to sign Alice's key")
def step_bob_attempts_sign_after_revoke(context):
    """When Bob tries to sign Alice's (revoked) key; response checked separately."""
    _sign_key(context, "bob", "alice")
