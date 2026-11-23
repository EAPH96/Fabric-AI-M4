Feature: Ask the HR policies assistant
  As a member of the staff
  I want to ask about the company policies
  So that every answer cites the policy it comes from

  Scenario: Asking for a policy by its id cites it
    Given the assistant is running with the default settings
    When I ask "¿Qué dice la política POL-003?"
    Then the response status is 200
    And the answer mentions "POL-003"
    And the answer mentions "Aguinaldo"
    And the tools used are "get_policy"
    And the number of steps is 2

  Scenario: Asking about a topic searches the policies and cites the policy
    Given the assistant is running with the default settings
    When I ask "¿Cuántos días de vacaciones me tocan?"
    Then the response status is 200
    And the answer mentions "POL-001"
    And the tools used are "search_policies"

  Scenario: Asking for an unknown policy gets the not found text
    Given the assistant is running with the default settings
    When I ask "¿Qué dice la política POL-999?"
    Then the response status is 200
    And the answer is "No encontré esa información en las políticas. Pregunta por una política (POL-001) o un tema, como vacaciones."
    And the tools used are "get_policy"

  Scenario: A question without a policy id or a topic gets the not found text
    Given the assistant is running with the default settings
    When I ask "¿Qué tal el clima hoy?"
    Then the response status is 200
    And the answer is "No encontré esa información en las políticas. Pregunta por una política (POL-001) o un tema, como vacaciones."
    And no tools were used

  Scenario: The home page shows the legal notice and links to the HR Assistant
    Given the assistant is running with the companion URL "https://hr.example.com/"
    When I open the home page without a key
    Then the response status is 200
    And the page says "Políticas ficticias de ejemplo; no son asesoría legal"
    And the page header has a companion link named "HR Assistant" to "https://hr.example.com/"

  Scenario: Asking without a key or with a wrong key is rejected
    Given the assistant is running for one client
    When I ask about vacations without a key
    And I ask about vacations with the key "wrong-key-not-real"
    Then every response has status 401

  Scenario: The third question in a minute is rate limited
    Given the assistant allows 2 questions per minute
    When I ask about vacations 3 times
    Then the statuses are "200, 200, 429"
    And the last response has a positive Retry-After header
