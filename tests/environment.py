"""behave environment hooks."""
import os
from tests.support.client import APIClient
from tests.support.gpg_helper import GPGHelper


def before_all(context):
    servers = os.environ.get("GPGCHAIN_TEST_SERVER", "http://localhost:8080").split(",")
    context.servers = [s.strip() for s in servers]
    context.client = APIClient(context.servers[0])
    context.gpg = GPGHelper()


def before_scenario(context, scenario):
    context.client = APIClient(context.servers[0])
    context.keys = {}
    context.submitted_blocks = {}


