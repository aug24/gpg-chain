Feature: Independent-path (vertex-disjoint) trust scoring

  Background:
    Given Alice is the root of trust

  Scenario: Two independent paths give independent score 2
    Given Bob, Carol and Dave are on the ledger
    And Alice signed Bob and Carol
    And Bob signed Dave
    And Carol signed Dave
    When Alice checks Dave's independent path score with depth 2
    Then the independent path score is 2

  Scenario: Shared intermediate key reduces independent score to 1
    Given Bob, Carol, Dave and Eve are on the ledger
    And Alice signed Bob
    And Alice signed Eve
    And Bob signed Carol
    And Eve signed Carol
    And Carol signed Dave
    When Alice checks Dave's independent path score with depth 3
    Then the independent path score is 1

  Scenario: Standard scoring counts all distinct paths through shared intermediate
    Given Bob, Carol, Dave and Eve are on the ledger
    And Alice signed Bob
    And Alice signed Eve
    And Bob signed Carol
    And Eve signed Carol
    And Carol signed Dave
    When Alice checks Dave's trust score with depth 3
    Then the trust score is 2

  Scenario: Independent score respects depth limit
    Given Bob, Carol and Dave are on the ledger
    And Alice signed Bob and Carol
    And Bob signed Dave
    And Carol signed Dave
    When Alice checks Dave's independent path score with depth 1
    Then the independent path score is 0
