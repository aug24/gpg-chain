Feature: P2P peer registration

  Scenario: Valid peer registration is accepted
    Given two nodes A and B are running
    When node A registers node B as a peer
    Then the response status is 200
    And node A lists node B in its peer list

  Scenario: Unreachable peer is rejected
    When a node attempts to register an unreachable URL as a peer
    Then the response status is 400

  Scenario: Private IP address is rejected
    When a node attempts to register "http://192.168.1.1:8080" as a peer
    Then the response status is 400

  Scenario: Loopback address is rejected
    When a node attempts to register "http://127.0.0.1:9999" as a peer
    Then the response status is 400

  Scenario: Peer list cap is enforced
    Given the node's peer list is full
    When a new peer attempts to register
    Then the response status is 429

  Scenario: Duplicate peer URL is deduplicated
    Given node B is already in node A's peer list
    When node B registers with node A again
    Then the response status is 200
    And node B appears only once in node A's peer list
