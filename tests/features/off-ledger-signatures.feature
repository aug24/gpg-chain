Feature: Off-ledger signatures

  Scenario: Off-ledger signer with valid inline key is accepted
    Given Alice's key is on the ledger
    And Dave's key is NOT on the ledger
    When Dave signs Alice's key providing his armored public key inline
    Then the response status is 200
    And Alice's sig chain contains an entry with Dave's fingerprint
    And the entry stores Dave's armored public key

  Scenario: Off-ledger signer with invalid signature is rejected
    Given Alice's key is on the ledger
    And Dave's key is NOT on the ledger
    When Dave submits a corrupted trust signature with his key inline
    Then the response status is 400

  Scenario: Off-ledger signer with weak key is rejected
    Given Alice's key is on the ledger
    And a weak RSA-1024 key pair for "weak@external.org"
    When the weak key owner signs Alice's key providing the key inline
    Then the response status is 400

  Scenario: Off-ledger SigEntry stores source_node when provided
    Given Alice's key is on the ledger
    And Dave's key is NOT on the ledger but lives at "https://keys.external.org"
    When Dave signs Alice's key providing his key inline and source_node URL
    Then the response status is 200
    And Alice's sig chain entry for Dave contains source_node "https://keys.external.org"

  Scenario: Signing a revoked block with off-ledger key is rejected
    Given Alice's key is on the ledger and revoked
    And Dave's key is NOT on the ledger
    When Dave attempts to sign Alice's revoked key inline
    Then the response status is 409
