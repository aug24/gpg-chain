Feature: Cross-ledger discovery and trust traversal

  Scenario: Well-known endpoint returns node metadata
    When a client fetches /.well-known/gpgchain.json
    Then the response status is 200
    And the response contains "node_url"
    And the response contains "domains"
    And the response contains "peers"

  Scenario: Client resolves signer's node from SourceNode in SigEntry
    Given Alice's key is on ledger A
    And Dave's key is on ledger B at "https://keys.external.org"
    And Dave has signed Alice's key with source_node "https://keys.external.org"
    When a client evaluates Alice's trust and follows Dave's source_node
    Then the client fetches Dave's block from "https://keys.external.org"

  Scenario: Cross-ledger trust path is established
    Given Alice is the root of trust on ledger A
    And Bob's key is on ledger A, signed by Alice
    And Carol's key is on ledger B
    And Bob has signed Carol's key with source_node pointing to ledger B
    When Alice checks Carol's trust score with depth 2
    Then the trust score is 1

  Scenario: Unreachable source_node is skipped gracefully
    Given Alice is the root of trust
    And Dave's SigEntry on Bob's key has source_node "https://unreachable.example"
    When Alice checks Bob's trust score
    Then the evaluation completes without error
    And the unreachable source_node path does not count

  Scenario: Cross-ledger traversal respects depth limit
    Given a chain spanning 3 ledgers each 1 hop apart
    When Alice checks the final key with depth 2
    Then the key beyond the depth limit is not trusted

  Scenario: Cycle across ledgers does not loop forever
    Given ledger A and ledger B cross-sign each other
    When a client evaluates trust with depth 5
    Then the evaluation completes without error
