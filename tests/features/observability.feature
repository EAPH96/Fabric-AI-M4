Feature: Trace and measure every request
  As a support engineer
  I want every request to carry an id, a JSON log line and metrics
  So that I can answer with data what happened to any request

  Scenario: A response without a client id carries a generated request id
    Given the assistant is running with observability
    When I check the health endpoint
    Then the response carries a generated UUID as its request id

  Scenario: The client request id is kept in the header and in the answer
    Given the assistant is running with observability
    When the client sends the request id "demo-123" with the question "¿Quién es EMP-0004?"
    Then the response header X-Request-ID is "demo-123"
    And the answer body has the request id "demo-123"

  Scenario: Every request writes one JSON request line
    Given the assistant is running with observability
    When I check the health endpoint
    Then the log has exactly one "request" event
    And the request event has method "GET", path "/health" and status 200
    And the request event has a positive latency and the request id of the response

  Scenario: Asking for an employee logs counts and an audit, never the conversation
    Given the assistant is running with observability
    When I ask "¿Quién es EMP-0004?"
    Then the log has exactly one "agent_run" event
    And the agent run event has the counts of the answer and was not stopped
    And the log has one audit of "get_employee" for employee "EMP-0004"
    And the log never contains the question or the answer

  Scenario: An unexpected failure answers 500 with the request id
    Given the assistant is running with a model that fails with a secret message
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 500
    And the body says "internal error" with the request id of the response
    And the log has one error event of type "RuntimeError"
    And the log never contains the secret message

  Scenario: Metrics report requests, tokens and the latency objective
    Given the assistant is running with observability
    When I ask "¿Quién es EMP-0004?"
    And I ask "¿Quiénes trabajan en Finanzas?"
    And I read the metrics
    Then the metrics count 2 requests with an error rate of 0.0
    And the metrics add up the tokens of both answers
    And the latency objective is 2000 ms and it is met

  Scenario: The home page shows the request id of each answer
    Given the assistant is running with observability
    When I open the home page
    Then the page has a place to show the request id
