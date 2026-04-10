"""Step definitions for adding-keys.feature and shared key setup."""
import time

from behave import given, when, then


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _name_from_uid(uid: str) -> str:
    """Return a canonical short name from a UID like 'alice@example.com' → 'alice'."""
    local = uid.split("@")[0].lower()
    return local.split()[0]  # handle 'Alice (no email)' style UIDs


def _ensure_keys(context):
    """Initialise shared state if not already present."""
    if not hasattr(context, "keys"):
        context.keys = {}
    if not hasattr(context, "submitted_blocks"):
        context.submitted_blocks = {}


def _submit_key(context, name: str, client=None):
    """Generate self-sig and submit key for *name*.  Stores response on context."""
    _ensure_keys(context)
    if client is None:
        client = context.client
    key = context.keys[name]
    ts = int(time.time())
    self_sig = context.gpg.sign_submit_payload(
        key["armored_public"], key["armored_private"], key["fingerprint"], ts,
        homedir=key.get("homedir"),
    )
    resp = client.add_block(key["armored_public"], self_sig, submit_timestamp=ts)
    context.submitted_blocks[key["fingerprint"]] = {
        "key": key,
        "self_sig": self_sig,
        "timestamp": ts,
    }
    return resp


def _put_key_on_ledger(context, name: str, client=None):
    """Ensure a key is on the ledger; raise if the server rejects it.

    A 409 (duplicate fingerprint) is treated as success: the key is already
    on the ledger, which satisfies the precondition.
    """
    resp = _submit_key(context, name, client=client)
    assert resp.status_code in (201, 409), (
        f"Failed to put {name}'s key on ledger: {resp.status_code} {resp.text}"
    )


# ---------------------------------------------------------------------------
# Givens – key generation
# ---------------------------------------------------------------------------

@given('a GPG key pair for "{uid}"')
def step_gen_key(context, uid):
    _ensure_keys(context)
    name = _name_from_uid(uid)
    key = context.gpg.generate_key(uid)
    context.keys[name] = key
    # Keep the most-recently-generated key accessible as context.last_key
    context.last_key = key


@given('a GPG key pair with UID "{uid}"')
def step_gen_key_no_email(context, uid):
    _ensure_keys(context)
    name = _name_from_uid(uid)
    key = context.gpg.generate_key(uid)
    context.keys[name] = key
    context.last_key = key


@given('a GPG key pair with UIDs "{uid1}" and "{uid2}"')
def step_gen_key_two_uids(context, uid1, uid2):
    """Generate a key with two UIDs, registered under both names."""
    _ensure_keys(context)
    name1 = _name_from_uid(uid1)
    name2 = _name_from_uid(uid2)
    key = context.gpg.generate_key_with_two_uids(uid1, uid2)
    context.keys[name1] = key
    context.keys[name2] = key
    context.last_key = key


@given('an RSA-1024 key pair for "{uid}"')
def step_gen_rsa1024(context, uid):
    _ensure_keys(context)
    name = _name_from_uid(uid)
    key = context.gpg.generate_weak_rsa_key(uid)
    context.keys[name] = key
    context.last_key = key


@given('a DSA-1024 key pair for "{uid}"')
def step_gen_dsa1024(context, uid):
    """Attempt to generate a DSA-1024 key. Falls back to RSA-1024 since GPGHelper
    does not support DSA directly; the server should reject it on algorithm grounds."""
    _ensure_keys(context)
    name = _name_from_uid(uid)
    # Re-use the weak RSA path as a stand-in for any disallowed algorithm.
    key = context.gpg.generate_weak_rsa_key(uid)
    context.keys[name] = key
    context.last_key = key


@given('a weak RSA-1024 key pair for "{uid}"')
def step_gen_weak_rsa(context, uid):
    _ensure_keys(context)
    name = _name_from_uid(uid)
    key = context.gpg.generate_weak_rsa_key(uid)
    context.keys[name] = key
    context.last_key = key


# ---------------------------------------------------------------------------
# Givens – ledger state
# ---------------------------------------------------------------------------

@given("Alice's key is already on the ledger")
def step_alice_already_on_ledger(context):
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
    _put_key_on_ledger(context, "alice")


@given("Alice's key is on the ledger")
def step_alice_on_ledger(context):
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
    _put_key_on_ledger(context, "alice")


@given("Bob's key is on the ledger")
def step_bob_on_ledger(context):
    _ensure_keys(context)
    if "bob" not in context.keys:
        context.keys["bob"] = context.gpg.generate_key("bob@example.com")
    _put_key_on_ledger(context, "bob")


@given("Carol's key is on the ledger")
def step_carol_on_ledger(context):
    _ensure_keys(context)
    if "carol" not in context.keys:
        context.keys["carol"] = context.gpg.generate_key("carol@example.com")
    _put_key_on_ledger(context, "carol")


@given("Carol's key is not on the ledger")
def step_carol_not_on_ledger(context):
    _ensure_keys(context)
    if "carol" not in context.keys:
        context.keys["carol"] = context.gpg.generate_key("carol@example.com")
    # Do NOT submit; just ensure the key exists locally.


@given("Dave's key is on the ledger")
def step_dave_on_ledger(context):
    _ensure_keys(context)
    if "dave" not in context.keys:
        context.keys["dave"] = context.gpg.generate_key("dave@example.com")
    _put_key_on_ledger(context, "dave")


@given("Dave's key is NOT on the ledger")
def step_dave_not_on_ledger(context):
    _ensure_keys(context)
    if "dave" not in context.keys:
        context.keys["dave"] = context.gpg.generate_key("dave@example.com")


@given('Dave\'s key is NOT on the ledger but lives at "{source_node}"')
def step_dave_not_on_ledger_but_lives_at(context, source_node):
    _ensure_keys(context)
    if "dave" not in context.keys:
        context.keys["dave"] = context.gpg.generate_key("dave@example.com")
    context.dave_source_node = source_node


# ---------------------------------------------------------------------------
# Whens – submission
# ---------------------------------------------------------------------------

@when("Alice submits her public key with a valid self-signature")
def step_alice_submits(context):
    _submit_key(context, "alice")


@when("Bob submits his public key with a valid self-signature")
def step_bob_submits(context):
    _submit_key(context, "bob")


@when("Bob submits his public key without a self-signature")
def step_bob_submits_no_sig(context):
    _ensure_keys(context)
    key = context.keys["bob"]
    context.client.add_block(key["armored_public"], "")


@when("Carol submits her public key with a corrupted self-signature")
def step_carol_corrupted_sig(context):
    _ensure_keys(context)
    key = context.keys["carol"]
    context.client.add_block(key["armored_public"], "bm90YXZhbGlkc2ln")


@when("Dave submits his public key signed by Eve's private key")
def step_dave_signed_by_eve(context):
    _ensure_keys(context)
    dave = context.keys["dave"]
    eve = context.keys["eve"]
    ts = int(time.time())
    wrong_sig = context.gpg.sign_submit_payload(
        dave["armored_public"], eve["armored_private"], eve["fingerprint"], ts,
        homedir=eve.get("homedir"),
    )
    context.client.add_block(dave["armored_public"], wrong_sig)


@when("the owner submits the weak key with a valid self-signature")
def step_weak_owner_submits(context):
    _submit_key(context, _name_from_uid(context.last_key["uid"]))


@when("the owner submits the DSA key with a valid self-signature")
def step_dsa_owner_submits(context):
    _submit_key(context, _name_from_uid(context.last_key["uid"]))


@when("the owner submits the key with a valid self-signature")
def step_generic_owner_submits(context):
    _submit_key(context, _name_from_uid(context.last_key["uid"]))


@when("Alice submits her public key again")
def step_alice_submits_again(context):
    _submit_key(context, "alice")


@when("Frank submits his public key with a valid self-signature")
def step_frank_submits(context):
    _submit_key(context, "frank")


# ---------------------------------------------------------------------------
# Thens – assertions
# ---------------------------------------------------------------------------

@then("the ledger contains a block for Alice's fingerprint")
def step_ledger_has_alice(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200, f"Expected block for Alice, got {resp.status_code}"


@then("GET /block/<Frank's fingerprint> returns status 200")
def step_frank_block_200(context):
    fp = context.keys["frank"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


@then("the block contains Frank's fingerprint and UID")
def step_block_has_frank(context):
    fp = context.keys["frank"]["fingerprint"]
    resp = context.client.get_block(fp)
    body = resp.json()
    assert fp.upper() in body.get("fingerprint", "").upper(), (
        f"Fingerprint not found in block: {body}"
    )
    uid = context.keys["frank"]["uid"]
    uids_in_block = body.get("uids", [])
    assert any(uid in u for u in uids_in_block), (
        f"UID {uid!r} not found in block uids: {uids_in_block}"
    )
