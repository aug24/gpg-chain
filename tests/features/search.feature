Feature: Search

  Scenario: Search by exact UID returns matching block
    Given Alice's key with UID "Alice <alice@example.com>" is on the ledger
    When a client searches for "alice@example.com"
    Then the response status is 200
    And the results contain Alice's fingerprint

  Scenario: Search by partial email returns matching blocks
    Given multiple keys with "@example.com" addresses are on the ledger
    When a client searches for "example.com"
    Then the response status is 200
    And all matching blocks are returned

  Scenario: Search with no matches returns empty list
    Given the ledger has no keys matching "nobody@nowhere.example"
    When a client searches for "nobody@nowhere.example"
    Then the response status is 200
    And the results list is empty

  Scenario: Revoked key appears in results flagged as revoked
    Given Alice's key is on the ledger and revoked
    When a client searches for Alice's email
    Then the response status is 200
    And the result for Alice's fingerprint has revoked set to true
