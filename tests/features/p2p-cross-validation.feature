Feature: P2P cross-validation

  Scenario: Node detects peer serving wrong SigChainHead
    Given nodes A and B are peered and have the same blocks
    And node B has had a signature stripped from Alice's block
    When node A cross-validates with node B
    Then node A detects a SigChainHead mismatch for Alice's fingerprint

  Scenario: Node fetches longer sig chain from honest peer
    Given node A is missing a signature on Alice's block
    And node B has the full sig chain
    When node A cross-validates with node B
    Then node A fetches and applies the missing signature from node B

  Scenario: Node detects peer missing a block entirely
    Given node A has a block that node B does not have
    When node A cross-validates with node B
    Then node A detects that node B is missing the block
