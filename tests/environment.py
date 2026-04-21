"""behave environment hooks."""
import os
import shutil
from tests.support.client import APIClient
from tests.support.gpg_helper import GPGHelper


def _find_cli_binary() -> str | None:
    """Locate the Go CLI client binary.

    Search order:
      1. GPGCHAIN_CLIENT environment variable (explicit path)
      2. implementations/go/cmd/client/gpgchain relative to the repo root
         (repo root is two directories above this file's directory)
      3. gpgchain on PATH
    """
    explicit = os.environ.get("GPGCHAIN_CLIENT")
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(
        repo_root, "implementations", "go", "cmd", "client", "gpgchain"
    )
    if os.path.isfile(candidate):
        return candidate

    return shutil.which("gpgchain")


def before_all(context):
    servers = os.environ.get("GPGCHAIN_TEST_SERVER", "http://localhost:8080").split(",")
    context.servers = [s.strip() for s in servers]
    context.client = APIClient(context.servers[0])
    context.gpg = GPGHelper()
    context.cli_binary = _find_cli_binary()


def before_scenario(context, scenario):
    context.client = APIClient(context.servers[0])
    context.keys = {}
    context.submitted_blocks = {}
    context._cli_temp_files = []

    if "cli" in scenario.tags and context.cli_binary is None:
        scenario.skip("CLI binary not found — set GPGCHAIN_CLIENT or build implementations/go/cmd/client/gpgchain")


def after_scenario(context, scenario):
    # Clean up any temp files written by CLI step definitions.
    from tests.steps.cli_steps import cleanup_temp_files
    cleanup_temp_files(context)


