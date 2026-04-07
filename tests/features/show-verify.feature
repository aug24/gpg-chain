Feature: Show and verify

  Scenario: Show returns full block with sig chain
    Given Alice's key is on the ledger
    And Bob and Carol have signed Alice's key
    When a client fetches Alice's block
    Then the response status is 200
    And the block includes Alice's armored key and UIDs
    And the sig chain contains entries for Bob and Carol

  Scenario: Verify passes on a valid ledger
    Given the ledger contains several valid blocks with valid sig chains
    When a client runs verify
    Then all blocks pass hash verification
    And all sig chain links are intact
    And all GPG signatures verify against the stored keys

  Scenario: Verify detects a tampered block hash
    Given a block with a manually corrupted hash is on the ledger
    When a client runs verify
    Then verify reports the corrupted block as invalid

  Scenario: Verify detects a broken sig chain link
    Given a block whose sig chain has a corrupted intermediate hash
    When a client runs verify
    Then verify reports the broken sig chain link
