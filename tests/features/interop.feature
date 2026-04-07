Feature: Mixed-language interoperability

  Scenario: Block submitted to Go node is readable from Python node
    Given a Go node and a Python node are peered
    When Alice submits her key to the Go node
    Then the Python node eventually contains Alice's block
    And the block hash is identical on both nodes

  Scenario: Block submitted to Python node is readable from Go node
    Given a Go node and a Python node are peered
    When Alice submits her key to the Python node
    Then the Go node eventually contains Alice's block
    And the block hash is identical on both nodes

  Scenario: Trust signature from Go client verifies on Python node
    Given Alice's key is on both nodes
    And Bob's key is on both nodes
    When Bob signs Alice's key using the Go client against the Go node
    Then the Python node has Bob's signature on Alice's block
    And the signature verifies correctly

  Scenario: Trust signature from Python client verifies on Go node
    Given Alice's key is on both nodes
    And Bob's key is on both nodes
    When Bob signs Alice's key using the Python client against the Python node
    Then the Go node has Bob's signature on Alice's block
    And the signature verifies correctly

  Scenario: Trust evaluation gives same result regardless of which node is queried
    Given a mixed cluster with 2 Go nodes and 2 Python nodes all peered
    And a trust chain Alice -> Bob -> Carol exists on the ledger
    When a client queries trust for Carol against each node with depth 2
    Then all four nodes return the same trust score
