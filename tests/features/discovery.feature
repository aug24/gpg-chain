Feature: Client-side key discovery across nodes

  A client that does not know all node URLs can find a key by querying one
  node, then following the peer graph returned by /.well-known/gpgchain.json
  until the key is found or all reachable nodes have been tried.

  Scenario: Key found on the queried node
    Given Alice's key is on the ledger
    When a client discovers Alice's key by fingerprint
    Then the discovery returns Alice's block from the queried node

  Scenario: Unknown fingerprint returns no result
    When a client discovers a key with an unknown fingerprint
    Then the discovery returns no result

  Scenario: Key found via peer when not on starting node
    Given nodes A and B are peered
    And Alice's key is only on node A
    When a client starts discovery for Alice's fingerprint with both nodes as seeds
    Then the discovery returns Alice's block

  Scenario: Email search finds key across nodes
    Given nodes A and B are peered
    And Alice's key is only on node A
    When a client searches for "alice@example.com" with both nodes as seeds
    Then the search returns Alice's block
