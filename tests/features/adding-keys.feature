Feature: Adding a key

  Scenario: Owner can add their own key
    Given a GPG key pair for "alice@example.com"
    When Alice submits her public key with a valid self-signature
    Then the response status is 201
    And the ledger contains a block for Alice's fingerprint

  Scenario: Submission without a self-signature is rejected
    Given a GPG key pair for "bob@example.com"
    When Bob submits his public key without a self-signature
    Then the response status is 400

  Scenario: Submission with an invalid self-signature is rejected
    Given a GPG key pair for "carol@example.com"
    When Carol submits her public key with a corrupted self-signature
    Then the response status is 400

  Scenario: Self-signature made by a different key is rejected
    Given a GPG key pair for "dave@example.com"
    And a GPG key pair for "eve@example.com"
    When Dave submits his public key signed by Eve's private key
    Then the response status is 400

  Scenario: Weak RSA key is rejected
    Given an RSA-1024 key pair for "weak@example.com"
    When the owner submits the weak key with a valid self-signature
    Then the response status is 400

  Scenario: DSA-1024 key is rejected
    Given a DSA-1024 key pair for "legacy@example.com"
    When the owner submits the DSA key with a valid self-signature
    Then the response status is 400

  Scenario: Duplicate fingerprint is rejected
    Given Alice's key is already on the ledger
    When Alice submits her public key again
    Then the response status is 409

  Scenario: Submitted block is retrievable
    Given a GPG key pair for "frank@example.com"
    When Frank submits his public key with a valid self-signature
    Then the response status is 201
    And GET /block/<Frank's fingerprint> returns status 200
    And the block contains Frank's fingerprint and UID
