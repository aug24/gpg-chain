Feature: P2P gossip

  Scenario: Block submitted to node A appears on node B
    Given nodes A and B are peered
    And Alice's key is not on either node
    When Alice submits her key to node A
    Then node B eventually contains Alice's block

  Scenario: Trust signature gossiped to peer
    Given nodes A and B are peered
    And Alice's key is on both nodes
    And Bob's key is on both nodes
    When Bob signs Alice's key on node A
    Then node B eventually has Bob's signature on Alice's block

  Scenario: Revocation gossiped to peer
    Given nodes A and B are peered
    And Alice's key is on both nodes
    When Alice revokes her key on node A
    Then node B eventually shows Alice's block as revoked

  Scenario: Block does not loop back to originating node
    Given nodes A, B and C are all peered together
    When a block is submitted to node A
    Then node A receives the gossip at most once

  Scenario: Invalid gossiped block is rejected
    Given node A is running
    When a peer sends a block with an invalid self-signature to /p2p/block
    Then the response status is 400
    And the invalid block is not stored
