"""Step definitions for signing-keys.feature and off-ledger-signatures.feature."""
import time

from behave import given, when, then

from tests.steps.key_steps import _ensure_keys, _put_key_on_ledger, _submit_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_block_hash(context, name: str, client=None) -> str:
    """Fetch a block from the ledger and return its hash."""
    if client is None:
        client = context.client
    fp = context.keys[name]["fingerprint"]
    resp = client.get_block(fp)
    assert resp.status_code == 200, f"Block for {name} not found: {resp.status_code}"
    return resp.json()["hash"]


def _sign_key(context, signer: str, target: str, source_node: str = "",
              signer_armored_key: str = "", client=None) -> None:
    """Sign *target*'s block with *signer*'s key and call sign_block."""
    if client is None:
        client = context.client
    block_hash = _get_block_hash(context, target, client=client)
    signer_key = context.keys[signer]
    ts = int(time.time())
    sig = context.gpg.sign_trust_payload(
        block_hash, signer_key["fingerprint"], ts, signer_key["armored_private"],
        homedir=signer_key.get("homedir"),
    )
    client.sign_block(
        context.keys[target]["fingerprint"],
        signer_key["fingerprint"],
        sig,
        signer_armored_key=signer_armored_key,
        source_node=source_node,
    )


# ---------------------------------------------------------------------------
# Givens – signing state
# ---------------------------------------------------------------------------

@given("Bob has already signed Alice's key")
def step_bob_already_signed_alice(context):
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
        _put_key_on_ledger(context, "alice")
    if "bob" not in context.keys:
        context.keys["bob"] = context.gpg.generate_key("bob@example.com")
        _put_key_on_ledger(context, "bob")
    _sign_key(context, "bob", "alice")


@given("Alice has signed Bob's key")
def step_alice_signed_bob(context):
    _ensure_keys(context)
    _sign_key(context, "alice", "bob")


@given("Bob has signed Carol's key")
def step_bob_signed_carol(context):
    _ensure_keys(context)
    _sign_key(context, "bob", "carol")


@given("Alice has signed Bob's key and Carol has signed Bob's key")
def step_alice_carol_signed_bob(context):
    _ensure_keys(context)
    _sign_key(context, "alice", "bob")
    _sign_key(context, "carol", "bob")


@given("Bob and Carol have signed Alice's key")
def step_bob_carol_signed_alice(context):
    _ensure_keys(context)
    if "bob" not in context.keys:
        context.keys["bob"] = context.gpg.generate_key("bob@example.com")
        _put_key_on_ledger(context, "bob")
    if "carol" not in context.keys:
        context.keys["carol"] = context.gpg.generate_key("carol@example.com")
        _put_key_on_ledger(context, "carol")
    _sign_key(context, "bob", "alice")
    _sign_key(context, "carol", "alice")


# ---------------------------------------------------------------------------
# Whens – sign operations
# ---------------------------------------------------------------------------

@when("Bob signs Alice's key with a valid trust signature")
def step_bob_signs_alice_valid(context):
    _sign_key(context, "bob", "alice")


@when("Bob signs Alice's key")
def step_bob_signs_alice(context):
    _sign_key(context, "bob", "alice")


@when("Carol signs Alice's key")
def step_carol_signs_alice(context):
    _sign_key(context, "carol", "alice")


@when("Carol attempts to sign Alice's key")
def step_carol_attempts_sign_alice(context):
    """Carol's key is not on the ledger; sign attempt should be rejected."""
    _sign_key(context, "carol", "alice")


@when("Bob submits a corrupted trust signature for Alice's key")
def step_bob_corrupted_trust_sig(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    context.client.sign_block(
        fp,
        context.keys["bob"]["fingerprint"],
        "bm90YXZhbGlkc2ln",
    )


@when("Bob attempts to sign Alice's key again")
def step_bob_sign_again(context):
    _sign_key(context, "bob", "alice")


@when("Bob attempts to sign Alice's revoked key")
def step_bob_attempts_sign_revoked(context):
    _sign_key(context, "bob", "alice")


# ---------------------------------------------------------------------------
# Thens – sig chain assertions
# ---------------------------------------------------------------------------

@then("Alice's block sig chain contains Bob's fingerprint")
def step_alice_block_has_bob(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200
    body = resp.json()
    bob_fp = context.keys["bob"]["fingerprint"].upper()
    sig_entries = body.get("sig_chain", [])
    signer_fps = [e.get("signer_fingerprint", "").upper() for e in sig_entries]
    assert bob_fp in signer_fps, (
        f"Bob's fingerprint {bob_fp} not in sig_entries: {signer_fps}"
    )


@then("Alice's block sig_chain_head reflects Carol's signature")
def step_alice_sig_chain_head_carol(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200
    body = resp.json()
    # sig_chain_head should be non-empty after signatures
    assert body.get("sig_chain_head"), "sig_chain_head is empty"
    # The last sig entry should be Carol's
    sig_entries = body.get("sig_chain", [])
    assert sig_entries, "No sig entries found"
    last_entry = sig_entries[-1]
    carol_fp = context.keys["carol"]["fingerprint"].upper()
    assert last_entry.get("signer_fingerprint", "").upper() == carol_fp, (
        f"Last signer is not Carol: {last_entry.get('signer_fingerprint')}"
    )


@then("the sig chain links back to the block hash")
def step_sig_chain_links_to_block(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    body = resp.json()
    block_hash = body.get("hash")
    sig_entries = body.get("sig_chain", [])
    assert sig_entries, "No sig entries"
    first_entry = sig_entries[0]
    assert first_entry.get("prev_hash") == block_hash, (
        f"First sig entry prev_hash {first_entry.get('prev_hash')!r} "
        f"does not match block hash {block_hash!r}"
    )


# ---------------------------------------------------------------------------
# Off-ledger signature steps
# ---------------------------------------------------------------------------

@when("Dave signs Alice's key providing his armored public key inline")
def step_dave_signs_alice_inline(context):
    _ensure_keys(context)
    block_hash = _get_block_hash(context, "alice")
    dave = context.keys["dave"]
    ts = int(time.time())
    sig = context.gpg.sign_trust_payload(
        block_hash, dave["fingerprint"], ts, dave["armored_private"],
        homedir=dave.get("homedir"),
    )
    context.client.sign_block(
        context.keys["alice"]["fingerprint"],
        dave["fingerprint"],
        sig,
        signer_armored_key=dave["armored_public"],
    )


@when("Dave submits a corrupted trust signature with his key inline")
def step_dave_corrupted_sig_inline(context):
    _ensure_keys(context)
    dave = context.keys["dave"]
    context.client.sign_block(
        context.keys["alice"]["fingerprint"],
        dave["fingerprint"],
        "bm90YXZhbGlkc2ln",
        signer_armored_key=dave["armored_public"],
    )


@when("the weak key owner signs Alice's key providing the key inline")
def step_weak_owner_signs_alice_inline(context):
    _ensure_keys(context)
    weak = context.keys.get("weak") or context.last_key
    block_hash = _get_block_hash(context, "alice")
    ts = int(time.time())
    sig = context.gpg.sign_trust_payload(
        block_hash, weak["fingerprint"], ts, weak["armored_private"],
        homedir=weak.get("homedir"),
    )
    context.client.sign_block(
        context.keys["alice"]["fingerprint"],
        weak["fingerprint"],
        sig,
        signer_armored_key=weak["armored_public"],
    )


@when("Dave signs Alice's key providing his key inline and source_node URL")
def step_dave_signs_alice_inline_with_source_node(context):
    _ensure_keys(context)
    source_node = getattr(context, "dave_source_node", "https://keys.external.org")
    block_hash = _get_block_hash(context, "alice")
    dave = context.keys["dave"]
    ts = int(time.time())
    sig = context.gpg.sign_trust_payload(
        block_hash, dave["fingerprint"], ts, dave["armored_private"],
        homedir=dave.get("homedir"),
    )
    context.client.sign_block(
        context.keys["alice"]["fingerprint"],
        dave["fingerprint"],
        sig,
        signer_armored_key=dave["armored_public"],
        source_node=source_node,
    )


@when("Dave attempts to sign Alice's revoked key inline")
def step_dave_attempts_sign_revoked_inline(context):
    _ensure_keys(context)
    block_hash = _get_block_hash(context, "alice")
    dave = context.keys["dave"]
    ts = int(time.time())
    sig = context.gpg.sign_trust_payload(
        block_hash, dave["fingerprint"], ts, dave["armored_private"],
        homedir=dave.get("homedir"),
    )
    context.client.sign_block(
        context.keys["alice"]["fingerprint"],
        dave["fingerprint"],
        sig,
        signer_armored_key=dave["armored_public"],
    )


@then("Alice's sig chain contains an entry with Dave's fingerprint")
def step_alice_sig_chain_has_dave(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200
    dave_fp = context.keys["dave"]["fingerprint"].upper()
    sig_entries = resp.json().get("sig_chain", [])
    signer_fps = [e.get("signer_fingerprint", "").upper() for e in sig_entries]
    assert dave_fp in signer_fps, f"Dave's fp {dave_fp} not in sig_entries: {signer_fps}"


@then("the entry stores Dave's armored public key")
def step_entry_stores_dave_key(context):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    dave_fp = context.keys["dave"]["fingerprint"].upper()
    sig_entries = resp.json().get("sig_chain", [])
    dave_entries = [
        e for e in sig_entries
        if e.get("signer_fingerprint", "").upper() == dave_fp
    ]
    assert dave_entries, "No sig entry for Dave"
    assert dave_entries[0].get("signer_armored_key"), "signer_armored_key is empty"


@then('Alice\'s sig chain entry for Dave contains source_node "{expected_url}"')
def step_alice_sig_chain_dave_source_node(context, expected_url):
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    dave_fp = context.keys["dave"]["fingerprint"].upper()
    sig_entries = resp.json().get("sig_chain", [])
    dave_entries = [
        e for e in sig_entries
        if e.get("signer_fingerprint", "").upper() == dave_fp
    ]
    assert dave_entries, "No sig entry for Dave"
    assert dave_entries[0].get("source_node") == expected_url, (
        f"source_node mismatch: {dave_entries[0].get('source_node')!r} != {expected_url!r}"
    )
