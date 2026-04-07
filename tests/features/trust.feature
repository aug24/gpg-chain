Feature: Trust evaluation

  Scenario: Own key has a trust score of 1 at depth 0
    Given Alice is the root of trust
    When Alice checks her own key's trust score
    Then the trust score is 1

  Scenario: Key signed directly by own key is trusted at depth 1
    Given Alice is the root of trust
    And Bob's key is on the ledger
    And Alice has signed Bob's key
    When Alice checks Bob's trust score with depth 1
    Then the trust score is 1
    And Bob's key is trusted at threshold 1

  Scenario: Key trusted transitively at depth 2
    Given Alice is the root of trust
    And Bob and Carol are on the ledger
    And Alice has signed Bob's key
    And Bob has signed Carol's key
    When Alice checks Carol's trust score with depth 2
    Then the trust score is 1
    And Carol's key is trusted at threshold 1

  Scenario: Key beyond depth limit is not trusted
    Given Alice is the root of trust
    And Bob, Carol and Dave are on the ledger
    And Alice signed Bob, Bob signed Carol, Carol signed Dave
    When Alice checks Dave's trust score with depth 2
    Then the trust score is 0
    And Dave's key is not trusted at threshold 1

  Scenario: Revoked key in trust path breaks the path
    Given Alice is the root of trust
    And Bob and Carol are on the ledger
    And Alice has signed Bob's key
    And Bob has signed Carol's key
    And Bob's key has been revoked
    When Alice checks Carol's trust score with depth 2
    Then the trust score is 0

  Scenario: Multiple independent paths increase the score
    Given Alice is the root of trust
    And Bob, Carol and Dave are on the ledger
    And Alice signed Bob and Carol
    And Bob signed Dave
    And Carol signed Dave
    When Alice checks Dave's trust score with depth 2
    Then the trust score is 2
    And Dave's key is trusted at threshold 2

  Scenario: Threshold of 2 requires 2 distinct paths
    Given Alice is the root of trust
    And only Bob has signed Dave (depth 2)
    When Alice checks Dave's trust score with threshold 2
    Then the trust score is 1
    And Dave's key is not trusted at threshold 2

  Scenario: Cycle in the trust graph does not loop forever
    Given Alice is the root of trust
    And Bob and Carol are on the ledger
    And Alice signed Bob, Bob signed Carol, Carol signed Bob
    When Alice checks Carol's trust score with depth 5
    Then the evaluation completes without error
    And the trust score is 1

  Scenario: Off-ledger signer in local keyring closes a path
    Given Alice is the root of trust
    And Dave is an off-ledger signer known to Alice's local keyring
    And Dave has signed Bob's key (off-ledger sig stored inline)
    When Alice checks Bob's trust score with depth 2
    Then the trust score is 1

  Scenario: Off-ledger signer not in keyring contributes no path
    Given Alice is the root of trust
    And Dave is an off-ledger signer unknown to Alice
    And Dave has signed Bob's key (off-ledger sig stored inline)
    When Alice checks Bob's trust score with depth 2
    Then the trust score is 0
