Feature: CLI endorse command
  The endorse command signs every key on the ledger that meets the caller's
  trust threshold and has not already been signed by the caller.  The default
  threshold of 2 requires at least two independent paths before an endorsement
  is added, giving a meaningful signal.

  @cli
  Scenario: endorse — single-path threshold (threshold 1)
    # Setup: Bob signs Carol; Carol signs Alice.
    # From Bob's perspective: Alice has trust=1 (path Bob→Carol→Alice).
    # Bob has not yet signed Alice, so endorse should sign her.
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Carol's key is on the ledger
    And Bob has signed Carol's key via the API
    And Carol has signed Alice's key via the API
    When the CLI endorses trusted keys as Bob with threshold 1
    Then the CLI exits successfully
    And the CLI output contains "signed:"
    And the CLI output contains Alice's fingerprint
    And Alice's block has a signature from Bob

  @cli
  Scenario: endorse — two-path threshold (threshold 2, vertex-disjoint)
    # Setup: Bob signs Carol and Dave independently; both sign Alice.
    # From Bob's perspective: Alice has two vertex-disjoint paths
    # (Bob→Carol→Alice and Bob→Dave→Alice), so disjoint score = 2.
    # Carol and Dave each have score=1 (below threshold), so they are not endorsed.
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Carol's key is on the ledger
    And Dave's key is on the ledger
    And Bob has signed Carol's key via the API
    And Bob has signed Dave's key via the API
    And Carol has signed Alice's key via the API
    And Dave has signed Alice's key via the API
    When the CLI endorses trusted keys as Bob with threshold 2 and disjoint scoring
    Then the CLI exits successfully
    And the CLI output contains "signed:"
    And the CLI output contains Alice's fingerprint
    And Alice's block has a signature from Bob
    And the CLI output does not contain Carol's fingerprint
    And the CLI output does not contain Dave's fingerprint

  @cli
  Scenario: endorse — already-signed keys are counted but not re-submitted
    # Bob has directly signed Alice, so Alice is already in Bob's sig chain.
    # Endorse should report her as already signed and not attempt to sign again.
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Bob has signed Alice's key via the API
    When the CLI endorses trusted keys as Bob with threshold 1
    Then the CLI exits successfully
    And the CLI output contains "already signed"

  @cli
  Scenario: endorse — dry run shows candidates without signing
    # Same two-path setup, but --dry-run: output shows candidates, nothing is signed.
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Carol's key is on the ledger
    And Dave's key is on the ledger
    And Bob has signed Carol's key via the API
    And Bob has signed Dave's key via the API
    And Carol has signed Alice's key via the API
    And Dave has signed Alice's key via the API
    When the CLI dry-runs endorse as Bob with threshold 2 and disjoint scoring
    Then the CLI exits successfully
    And the CLI output contains "would sign:"
    And the CLI output contains Alice's fingerprint
    And Alice's block has no signature from Bob
