Feature: Go CLI client
  Exercises every command of the gpgchain CLI binary end-to-end.
  Requires GPGCHAIN_CLIENT to point to a built binary, or the binary to exist at
  implementations/go/cmd/client/gpgchain relative to the repo root.
  All scenarios are tagged @cli and are skipped if the binary is not found.

  @cli
  Scenario: add — submit a key via the CLI
    Given a GPG key pair for "alice@example.com"
    When the CLI adds Alice's key to the node
    Then the CLI exits successfully
    And the CLI output contains Alice's fingerprint
    And the server has a block for Alice's fingerprint

  @cli
  Scenario: show — display a block via the CLI
    Given Alice's key is on the ledger
    When the CLI shows Alice's block
    Then the CLI exits successfully
    And the CLI output contains Alice's fingerprint
    And the CLI output contains "active"

  @cli
  Scenario: sign — append a trust signature via the CLI
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When the CLI signs Alice's key as Bob
    Then the CLI exits successfully
    And the CLI output contains "Signed block"
    And Alice's block has a signature from Bob

  @cli
  Scenario: revoke — revoke a key via the CLI
    Given Alice's key is on the ledger
    When the CLI revokes Alice's key
    Then the CLI exits successfully
    And the CLI output contains "Revoked"
    And Alice's block is marked revoked on the server

  @cli
  Scenario: list — enumerate keys via the CLI
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When the CLI lists all keys on the node
    Then the CLI exits successfully
    And the CLI output contains Alice's fingerprint
    And the CLI output contains Bob's fingerprint

  @cli
  Scenario: list with trust filter — only trusted keys are shown
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Carol's key is on the ledger
    And Bob has signed Alice's key via the API
    When the CLI lists keys with Bob as root of trust and min-trust 1
    Then the CLI exits successfully
    And the CLI output contains Alice's fingerprint
    And the CLI output does not contain Carol's fingerprint

  @cli
  Scenario: check — evaluate trust score via the CLI
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Bob has signed Alice's key via the API
    When the CLI checks Alice's trust with Bob as root
    Then the CLI exits successfully
    And the CLI output contains "TRUSTED"

  @cli
  Scenario: check — untrusted key
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When the CLI checks Alice's trust with Bob as root
    Then the CLI exits with status 2
    And the CLI output contains "NOT TRUSTED"

  @cli
  Scenario: search — find a key by email via the CLI
    Given Alice's key is on the ledger
    When the CLI searches for "alice@example.com"
    Then the CLI exits successfully
    And the CLI output contains Alice's fingerprint

  @cli
  Scenario: search — no results for unknown email
    When the CLI searches for "nobody@nowhere.example"
    Then the CLI exits successfully
    And the CLI output contains "No blocks found"

  @cli
  Scenario: verify — ledger with valid blocks passes
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Bob has signed Alice's key via the API
    When the CLI verifies the node
    Then the CLI exits successfully
    And the CLI output contains "verified OK"
