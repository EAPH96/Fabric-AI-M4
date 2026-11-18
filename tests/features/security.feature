Feature: Only clients with a key can ask, and nobody floods the assistant
  As the owner of the HR Assistant in production
  I want every client to send its own key and to respect a limit per minute
  So that only trusted clients use the model and no one can abuse it

  Scenario: Asking without a key is rejected
    Given the assistant is running for the clients "hr" and "payroll"
    When I ask without a key
    Then the response status is 401
    And the body says exactly "invalid or missing API key"

  Scenario: Asking with a wrong key is rejected
    Given the assistant is running for the clients "hr" and "payroll"
    When I ask with the wrong key "not-the-right-key-0000"
    Then the response status is 401
    And the body says exactly "invalid or missing API key"

  Scenario: A valid key answers and the log names the client but never the key
    Given the assistant is running for the clients "hr" and "payroll"
    When client "hr" asks 1 question
    Then the response status is 200
    And the request, agent run and audit events name the client "hr"
    And the log never contains the key of client "hr"

  Scenario: The page, the health check and the docs are open but the metrics need a key
    Given the assistant is running for the clients "hr" and "payroll"
    When I open the page, the health check, the docs and the metrics without a key
    Then the page, the health check and the docs answer 200
    And the metrics answer 401

  Scenario: The third question in a minute is limited
    Given the assistant allows 2 questions per minute to each client
    When client "hr" asks 3 questions
    Then the first 2 questions were answered
    And the response status is 429
    And the body says exactly "rate limit exceeded"
    And the response has a positive Retry-After header

  Scenario: After a minute the same client can ask again
    Given the assistant allows 2 questions per minute to each client
    When client "hr" asks 3 questions
    And the clock moves 60 seconds
    And client "hr" asks 1 question
    Then the response status is 200

  Scenario: The limit is counted per client
    Given the assistant allows 2 questions per minute to each client
    When client "hr" asks 3 questions
    And client "payroll" asks 1 question
    Then the response status is 200

  Scenario: Production refuses to start with the fake model
    Given the environment is production with the fake model
    When the assistant starts
    Then it refuses to start naming "MODEL_PROVIDER" but never the key
