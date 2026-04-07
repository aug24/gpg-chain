Feature: Domain allowlist

  Scenario: Node with empty allowlist rejects all submissions
    Given the node has an empty domain allowlist
    And a GPG key pair for "alice@example.com"
    When Alice submits her public key with a valid self-signature
    Then the response status is 403

  Scenario: Node with allow_all accepts any domain
    Given the node is configured with allow_all_domains
    And a GPG key pair for "alice@anydomain.io"
    When Alice submits her public key with a valid self-signature
    Then the response status is 201

  Scenario: Key with a matching domain is accepted
    Given the node allows domain "example.com"
    And a GPG key pair for "alice@example.com"
    When Alice submits her public key with a valid self-signature
    Then the response status is 201

  Scenario: Key with a non-matching domain is rejected
    Given the node allows domain "example.com"
    And a GPG key pair for "bob@other.org"
    When Bob submits his public key with a valid self-signature
    Then the response status is 403

  Scenario: Key with no email UID is rejected
    Given the node is configured with allow_all_domains
    And a GPG key pair with UID "Alice (no email)"
    When the owner submits the key with a valid self-signature
    Then the response status is 400

  Scenario: Key passes if any UID matches the allowed domain
    Given the node allows domain "example.com"
    And a GPG key pair with UIDs "alice@other.org" and "alice@example.com"
    When Alice submits her public key with a valid self-signature
    Then the response status is 201

  Scenario: Gossiped block from outside allowlist is silently dropped
    Given the node allows domain "example.com"
    And a block for "bob@other.org" is gossiped to the node
    Then the node does not store the block
    And GET /block/<Bob's fingerprint> returns status 404
