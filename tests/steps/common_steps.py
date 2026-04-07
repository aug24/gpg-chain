"""Common behave step definitions shared across all features."""
from behave import given, when, then


@then('the response status is {status:d}')
def step_response_status(context, status):
    assert context.client.last_response.status_code == status, \
        f"expected {status}, got {context.client.last_response.status_code}: " \
        f"{context.client.last_response.text}"


@then('the response contains an error')
def step_response_error(context):
    body = context.client.last_response.json()
    assert "error" in body, f"expected error key in response: {body}"
