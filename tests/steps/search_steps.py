"""Step definitions for search.feature."""
import time

from behave import given, when, then

from tests.steps.key_steps import _ensure_keys, _put_key_on_ledger


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------

@given('Alice\'s key with UID "{uid}" is on the ledger')
def step_alice_uid_on_ledger(context, uid):
    _ensure_keys(context)
    context.keys["alice"] = context.gpg.generate_key(uid)
    _put_key_on_ledger(context, "alice")


@given('multiple keys with "@example.com" addresses are on the ledger')
def step_multiple_example_com_on_ledger(context):
    _ensure_keys(context)
    uids = [
        "search1@example.com",
        "search2@example.com",
        "search3@example.com",
    ]
    context.search_example_fps = []
    for uid in uids:
        name = uid.split("@")[0]
        key = context.gpg.generate_key(uid)
        context.keys[name] = key
        ts = int(time.time())
        sig = context.gpg.sign_submit_payload(
            key["armored_public"], key["armored_private"], key["fingerprint"], ts
        )
        resp = context.client.add_block(key["armored_public"], sig, submit_timestamp=ts)
        assert resp.status_code == 201, f"Failed to add {uid}: {resp.status_code}"
        context.search_example_fps.append(key["fingerprint"])


@given('the ledger has no keys matching "{query}"')
def step_ledger_no_matching(context, query):
    # Nothing to do: if this query is unique enough, no keys will match.
    context.empty_search_query = query


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------

@when('a client searches for "{query}"')
def step_client_searches(context, query):
    context.client.search(query)


@when("a client searches for Alice's email")
def step_client_searches_alice_email(context):
    uid = context.keys["alice"]["uid"]
    email = uid.split("<")[-1].rstrip(">").strip() if "<" in uid else uid
    context.client.search(email)


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------

@then("the results contain Alice's fingerprint")
def step_results_have_alice(context):
    resp = context.client.last_response
    assert resp.status_code == 200
    alice_fp = context.keys["alice"]["fingerprint"].upper()
    results = resp.json()
    # results may be a list or {"results": [...]}
    items = results if isinstance(results, list) else results.get("results", results)
    fps = [item.get("fingerprint", "").upper() for item in items]
    assert alice_fp in fps, f"Alice's fp {alice_fp} not in results: {fps}"


@then("all matching blocks are returned")
def step_all_matching_returned(context):
    resp = context.client.last_response
    assert resp.status_code == 200
    results = resp.json()
    items = results if isinstance(results, list) else results.get("results", results)
    fps_in_results = {item.get("fingerprint", "").upper() for item in items}
    for fp in context.search_example_fps:
        assert fp.upper() in fps_in_results, (
            f"Expected fp {fp} in results but got: {fps_in_results}"
        )


@then("the results list is empty")
def step_results_empty(context):
    resp = context.client.last_response
    assert resp.status_code == 200
    results = resp.json()
    items = results if isinstance(results, list) else results.get("results", results)
    assert len(items) == 0, f"Expected empty results, got: {items}"


@then("the result for Alice's fingerprint has revoked set to true")
def step_search_result_alice_revoked(context):
    resp = context.client.last_response
    alice_fp = context.keys["alice"]["fingerprint"].upper()
    results = resp.json()
    items = results if isinstance(results, list) else results.get("results", results)
    alice_items = [i for i in items if i.get("fingerprint", "").upper() == alice_fp]
    assert alice_items, f"Alice's fp not found in search results"
    assert alice_items[0].get("revoked") is True, (
        f"Alice's result not marked revoked: {alice_items[0]}"
    )
