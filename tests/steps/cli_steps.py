"""Step definitions for cli-client.feature.

Exercises the Go CLI binary end-to-end by invoking it via subprocess.
Key material is written to temporary files and cleaned up after each scenario.
"""
import os
import subprocess
import tempfile
import time

from behave import given, when, then

from tests.steps.key_steps import _ensure_keys, _put_key_on_ledger
from tests.steps.signing_steps import _sign_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp(content: str, suffix: str, context) -> str:
    """Write *content* to a temp file, track it for cleanup, return path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    if not hasattr(context, "_cli_temp_files"):
        context._cli_temp_files = []
    context._cli_temp_files.append(path)
    return path


def _run_cli(context, args: list) -> subprocess.CompletedProcess:
    """Run the CLI binary with *args* and store the result on context."""
    cmd = [context.cli_binary] + [str(a) for a in args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    context.cli_result = result
    return result


def _server(context) -> str:
    return context.servers[0].rstrip("/")


def cleanup_temp_files(context):
    for path in getattr(context, "_cli_temp_files", []):
        try:
            os.unlink(path)
        except OSError:
            pass
    context._cli_temp_files = []


# ---------------------------------------------------------------------------
# Givens — re-use existing helpers and add CLI-specific setup
# ---------------------------------------------------------------------------

def _api_sign(context, signer: str, target: str):
    """Ensure both keys exist on the ledger, then sign target as signer via API."""
    _ensure_keys(context)
    for name, uid in [(signer, f"{signer}@example.com"), (target, f"{target}@example.com")]:
        if name not in context.keys:
            context.keys[name] = context.gpg.generate_key(uid)
            _put_key_on_ledger(context, name)
    _sign_key(context, signer, target)


@given("Bob has signed Alice's key via the API")
def step_bob_signed_alice_api(context):
    _api_sign(context, "bob", "alice")


@given("Bob has signed Carol's key via the API")
def step_bob_signed_carol_api(context):
    _api_sign(context, "bob", "carol")


@given("Bob has signed Dave's key via the API")
def step_bob_signed_dave_api(context):
    _api_sign(context, "bob", "dave")


@given("Carol has signed Alice's key via the API")
def step_carol_signed_alice_api(context):
    _api_sign(context, "carol", "alice")


@given("Dave has signed Alice's key via the API")
def step_dave_signed_alice_api(context):
    _api_sign(context, "dave", "alice")


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------

@when("the CLI adds Alice's key to the node")
def step_cli_add_alice(context):
    _ensure_keys(context)
    if "alice" not in context.keys:
        context.keys["alice"] = context.gpg.generate_key("alice@example.com")
    key = context.keys["alice"]
    pub_path = _write_temp(key["armored_public"], ".pub.asc", context)
    priv_path = _write_temp(key["armored_private"], ".priv.asc", context)
    _run_cli(context, [
        "add",
        "--key", pub_path,
        "--privkey", priv_path,
        "--server", _server(context),
    ])


@when("the CLI shows Alice's block")
def step_cli_show_alice(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    _run_cli(context, ["show", "--fingerprint", fp, "--server", _server(context)])


@when("the CLI signs Alice's key as Bob")
def step_cli_sign_alice_as_bob(context):
    _ensure_keys(context)
    alice_fp = context.keys["alice"]["fingerprint"]
    bob = context.keys["bob"]
    priv_path = _write_temp(bob["armored_private"], ".priv.asc", context)
    _run_cli(context, [
        "sign",
        "--fingerprint", alice_fp,
        "--keyid", bob["fingerprint"],
        "--privkey", priv_path,
        "--server", _server(context),
    ])


@when("the CLI revokes Alice's key")
def step_cli_revoke_alice(context):
    _ensure_keys(context)
    alice = context.keys["alice"]
    priv_path = _write_temp(alice["armored_private"], ".priv.asc", context)
    _run_cli(context, [
        "revoke",
        "--fingerprint", alice["fingerprint"],
        "--privkey", priv_path,
        "--server", _server(context),
    ])


@when("the CLI lists all keys on the node")
def step_cli_list(context):
    _run_cli(context, ["list", "--server", _server(context)])


@when("the CLI lists keys with Bob as root of trust and min-trust 1")
def step_cli_list_trusted(context):
    _ensure_keys(context)
    bob_fp = context.keys["bob"]["fingerprint"]
    _run_cli(context, [
        "list",
        "--keyid", bob_fp,
        "--min-trust", "1",
        "--server", _server(context),
    ])


@when("the CLI checks Alice's trust with Bob as root")
def step_cli_check_alice_trust(context):
    _ensure_keys(context)
    alice_fp = context.keys["alice"]["fingerprint"]
    bob_fp = context.keys["bob"]["fingerprint"]
    _run_cli(context, [
        "check",
        "--fingerprint", alice_fp,
        "--keyid", bob_fp,
        "--server", _server(context),
    ])


@when('the CLI searches for "{email}"')
def step_cli_search(context, email):
    _run_cli(context, ["search", "--email", email, "--server", _server(context)])


@when("the CLI verifies the node")
def step_cli_verify(context):
    _run_cli(context, ["verify", "--server", _server(context)])


@when("the CLI endorses trusted keys as Bob with threshold {n:d}")
def step_cli_endorse_bob_threshold(context, n):
    _ensure_keys(context)
    bob = context.keys["bob"]
    priv_path = _write_temp(bob["armored_private"], ".priv.asc", context)
    _run_cli(context, [
        "endorse",
        "--keyid", bob["fingerprint"],
        "--privkey", priv_path,
        "--threshold", str(n),
        "--server", _server(context),
    ])


@when("the CLI endorses trusted keys as Bob with threshold {n:d} and disjoint scoring")
def step_cli_endorse_bob_threshold_disjoint(context, n):
    _ensure_keys(context)
    bob = context.keys["bob"]
    priv_path = _write_temp(bob["armored_private"], ".priv.asc", context)
    _run_cli(context, [
        "endorse",
        "--keyid", bob["fingerprint"],
        "--privkey", priv_path,
        "--threshold", str(n),
        "--disjoint",
        "--server", _server(context),
    ])


@when("the CLI dry-runs endorse as Bob with threshold {n:d} and disjoint scoring")
def step_cli_endorse_dry_run_disjoint(context, n):
    _ensure_keys(context)
    bob = context.keys["bob"]
    _run_cli(context, [
        "endorse",
        "--keyid", bob["fingerprint"],
        "--dry-run",
        "--threshold", str(n),
        "--disjoint",
        "--server", _server(context),
    ])


# ---------------------------------------------------------------------------
# Thens — CLI output and exit code assertions
# ---------------------------------------------------------------------------

@then("the CLI exits successfully")
def step_cli_exits_ok(context):
    result = context.cli_result
    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@then("the CLI exits with status {code:d}")
def step_cli_exits_with(context, code):
    result = context.cli_result
    assert result.returncode == code, (
        f"Expected exit {code}, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@then("the CLI output contains Alice's fingerprint")
def step_cli_output_has_alice_fp(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"].upper()
    out = context.cli_result.stdout.upper()
    assert fp in out, (
        f"Alice's fingerprint {fp!r} not in CLI output:\n{context.cli_result.stdout}"
    )


@then("the CLI output contains Bob's fingerprint")
def step_cli_output_has_bob_fp(context):
    _ensure_keys(context)
    fp = context.keys["bob"]["fingerprint"].upper()
    out = context.cli_result.stdout.upper()
    assert fp in out, (
        f"Bob's fingerprint {fp!r} not in CLI output:\n{context.cli_result.stdout}"
    )


@then('the CLI output contains "{text}"')
def step_cli_output_contains_text(context, text):
    out = context.cli_result.stdout
    assert text in out, (
        f"{text!r} not in CLI output:\n{out}\nstderr: {context.cli_result.stderr}"
    )


# ---------------------------------------------------------------------------
# Thens — server-side verification via HTTP
# ---------------------------------------------------------------------------

@then("the server has a block for Alice's fingerprint")
def step_server_has_alice(context):
    _ensure_keys(context)
    fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(fp)
    assert resp.status_code == 200, (
        f"Expected block for Alice on server, got {resp.status_code}: {resp.text}"
    )


@then("Alice's block has a signature from Bob")
def step_alice_has_sig_from_bob(context):
    _ensure_keys(context)
    alice_fp = context.keys["alice"]["fingerprint"]
    bob_fp = context.keys["bob"]["fingerprint"].upper()
    resp = context.client.get_block(alice_fp)
    assert resp.status_code == 200
    sig_chain = resp.json().get("sig_chain", [])
    signer_fps = {e.get("signer_fingerprint", "").upper() for e in sig_chain}
    assert bob_fp in signer_fps, (
        f"Bob's fingerprint not in Alice's sig chain: {signer_fps}"
    )


@then("the CLI output does not contain Carol's fingerprint")
def step_cli_output_lacks_carol_fp(context):
    _ensure_keys(context)
    fp = context.keys["carol"]["fingerprint"].upper()
    out = context.cli_result.stdout.upper()
    assert fp not in out, (
        f"Carol's fingerprint {fp!r} unexpectedly in CLI output:\n{context.cli_result.stdout}"
    )


@then("the CLI output does not contain Dave's fingerprint")
def step_cli_output_lacks_dave_fp(context):
    _ensure_keys(context)
    fp = context.keys["dave"]["fingerprint"].upper()
    out = context.cli_result.stdout.upper()
    assert fp not in out, (
        f"Dave's fingerprint {fp!r} unexpectedly in CLI output:\n{context.cli_result.stdout}"
    )


@then("Alice's block has no signature from Bob")
def step_alice_has_no_sig_from_bob(context):
    _ensure_keys(context)
    alice_fp = context.keys["alice"]["fingerprint"]
    bob_fp = context.keys["bob"]["fingerprint"].upper()
    resp = context.client.get_block(alice_fp)
    assert resp.status_code == 200
    sig_chain = resp.json().get("sig_chain", [])
    signer_fps = {e.get("signer_fingerprint", "").upper() for e in sig_chain}
    assert bob_fp not in signer_fps, (
        f"Bob's fingerprint unexpectedly in Alice's sig chain: {signer_fps}"
    )


@then("Alice's block is marked revoked on the server")
def step_alice_is_revoked(context):
    _ensure_keys(context)
    alice_fp = context.keys["alice"]["fingerprint"]
    resp = context.client.get_block(alice_fp)
    assert resp.status_code == 200
    assert resp.json().get("revoked") is True, (
        f"Alice's block is not revoked: {resp.json()}"
    )
