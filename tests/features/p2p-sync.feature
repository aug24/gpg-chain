Feature: P2P sync on connect

  Scenario: New node syncs full ledger from existing peer
    Given node A has 5 blocks
    When node B starts and peers with node A
    Then node B eventually has all 5 blocks

  Scenario: Sync includes complete sig chains
    Given node A has a block with 3 signatures
    When node B syncs with node A
    Then node B's copy of the block has all 3 signatures
    And the sig chain head matches node A's

  Scenario: Blocks added while node was offline are synced on reconnect
    Given node A has 3 blocks
    And node B was offline
    And 2 more blocks were added to node A while B was offline
    When node B reconnects and syncs with node A
    Then node B has all 5 blocks

  Scenario: Invalid block from peer during sync is rejected and sync continues
    Given node A has 1 valid block and 1 block with a corrupted hash
    When node B syncs with node A
    Then node B stores only the valid block
    And sync completes without crashing
