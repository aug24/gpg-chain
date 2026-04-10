Feature: Revocation

  Scenario: Owner can revoke their own key
    Given Alice's key is on the ledger
    When Alice revokes her key with a valid revocation signature
    Then the response status is 200
    And Alice's block is marked revoked

  Scenario: Non-owner revocation attempt is rejected
    Given Alice's key is on the ledger
    And Bob's key is on the ledger
    When Bob attempts to revoke Alice's key
    Then the response status is 403

  Scenario: Invalid revocation signature is rejected
    Given Alice's key is on the ledger
    When Alice submits a corrupted revocation signature
    Then the response status is 403

  Scenario: Revoked block is still retrievable and flagged
    Given Alice's key is on the ledger
    When Alice revokes her key
    Then GET /block/<Alice's fingerprint> returns status 200
    And the block has revoked set to true

  Scenario: Signing a revoked block is rejected
    Given Alice's key is on the ledger and revoked
    And Bob's key is on the ledger
    When Bob attempts to sign Alice's key
    Then the response status is 409

  Scenario: Re-revoking an already revoked block is rejected
    Given Alice's key is on the ledger and already revoked
    When Alice attempts to revoke her key again
    Then the response status is 409
