"""Step definitions for discovery.feature."""
from behave import given, when, then

from tests.support.client import APIClient
from tests.steps.key_steps import _ensure_keys, _put_key_on_ledger
from tests.steps.pending_steps import _require_nodes, _wait_for

from gpgchain.discovery import find_block, find_blocks_by_email


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------

@given("Alice's key is only on node A")
def step_alice_only_on_node_a(context):
    """Put Alice's key on node A but not node B.

    Requires two peered nodes (set up by 'nodes A and B are peered').
    """
    if not hasattr(context, "node_a"):
        return  # already skipped by peering step
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
    # Submit only to node A.
    _put_key_on_ledger(context, "alice", client=context.node_a)
    # Verify node B does not have it yet (gossip may have propagated; if so,
    # still meaningful — discovery can succeed via direct hit on B or via A).
    # We don't block gossip here; the discovery test is valid either way.


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------

@when("a client discovers Alice's key by fingerprint")
def step_discover_alice_by_fp(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    context.discovery_result = find_block(fp, [context.servers[0]])


@when("a client discovers a key with an unknown fingerprint")
def step_discover_unknown_fp(context):
    unknown = "DEADBEEF" * 10  # 80-char fake fingerprint
    context.discovery_result = find_block(unknown, [context.servers[0]])


@when("a client starts discovery for Alice's fingerprint with both nodes as seeds")
def step_discover_alice_from_node_b(context):
    if not hasattr(context, "node_b"):
        return  # already skipped
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    # Provide both node URLs as seeds; discovery tries B first (not found),
    # then A (found).  In production the peer list would come from .well-known;
    # in the test environment the node URLs are the externally-accessible seeds.
    context.discovery_result = find_block(fp, [context.servers[1], context.servers[0]])


@when('a client searches for "alice@example.com" with both nodes as seeds')
def step_search_alice_from_node_b(context):
    if not hasattr(context, "node_b"):
        return  # already skipped
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    context.alice_fp = fp
    context.email_results = find_blocks_by_email(
        "alice@example.com", [context.servers[1], context.servers[0]]
    )


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------

@then("the discovery returns Alice's block from the queried node")
def step_discovery_returns_alice_local(context):
    result = context.discovery_result
    assert result.found, f"Discovery returned no result (tried {result.nodes_tried} nodes)"
    fp = context.keys["alice"]["fingerprint"]
    assert result.block.get("fingerprint", "").upper() == fp.upper(), (
        f"Returned block fingerprint {result.block.get('fingerprint')!r} != {fp!r}"
    )
    assert result.node_url.rstrip("/") == context.servers[0].rstrip("/"), (
        f"Expected result from {context.servers[0]!r}, got {result.node_url!r}"
    )


@then("the discovery returns no result")
def step_discovery_returns_nothing(context):
    result = context.discovery_result
    assert not result.found, f"Expected no result, got block on {result.node_url!r}"


@then("the discovery returns Alice's block")
def step_discovery_returns_alice(context):
    if not hasattr(context, "node_b"):
        return  # already skipped
    result = context.discovery_result
    assert result.found, f"Discovery returned no result (tried {result.nodes_tried} nodes)"
    fp = context.keys["alice"]["fingerprint"]
    assert result.block.get("fingerprint", "").upper() == fp.upper(), (
        f"Returned block fingerprint {result.block.get('fingerprint')!r} != {fp!r}"
    )


@then("the search returns Alice's block")
def step_search_returns_alice(context):
    if not hasattr(context, "node_b"):
        return  # already skipped
    result = context.email_results
    assert result.found, f"Email search returned no results (tried {result.nodes_tried} nodes)"
    fp = context.alice_fp
    fps = [b.get("fingerprint", "").upper() for _, b in result.blocks]
    assert fp.upper() in fps, (
        f"Alice's fingerprint {fp!r} not in search results"
    )
