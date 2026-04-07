Feature: Signing a key (on-ledger signer)

  Scenario: Valid trust signature is accepted
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When Bob signs Alice's key with a valid trust signature
    Then the response status is 200
    And Alice's block sig chain contains Bob's fingerprint

  Scenario: Signer not on the ledger is rejected
    Given Alice's key is on the ledger
    And Carol's key is not on the ledger
    When Carol attempts to sign Alice's key
    Then the response status is 400

  Scenario: Invalid signature is rejected
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When Bob submits a corrupted trust signature for Alice's key
    Then the response status is 400

  Scenario: Duplicate signer is rejected
    Given Alice's key is on the ledger
    And Bob has already signed Alice's key
    When Bob attempts to sign Alice's key again
    Then the response status is 409

  Scenario: Signing a revoked block is rejected
    Given Alice's key is on the ledger
    And Alice's key has been revoked
    And Bob's key is on the ledger
    When Bob attempts to sign Alice's revoked key
    Then the response status is 409

  Scenario: Sig chain head is updated after each signature
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    And Carol's key is on the ledger
    When Bob signs Alice's key
    And Carol signs Alice's key
    Then Alice's block sig_chain_head reflects Carol's signature
    And the sig chain links back to the block hash
