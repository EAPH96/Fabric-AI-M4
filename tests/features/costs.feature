Feature: Cheaper answers that say what they cost
  As the person who pays for the model
  I want each question routed to the cheapest model that can answer it
  So that every answer reports its model, its route and its cost

  Scenario: A simple employee question goes to the small model
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    Then the answer used the model "@cf/meta/llama-3.1-8b-instruct-fast" for the reason "simple"
    And the answer reports a positive cost and 0 cached calls
    And the agent run event has the model, the route and the cost of the answer

  Scenario: A question with a routing keyword goes to the large model
    Given the assistant is running with the default settings
    When I ask "Compara a los empleados de Finanzas"
    Then the answer used the model "@cf/meta/llama-3.3-70b-instruct-fp8-fast" for the reason "keyword:compara"

  Scenario: A question longer than the routing limit goes to the large model
    Given the assistant is running with a routing limit of 20 characters
    When I ask "¿Quién es EMP-0004 en la empresa?"
    Then the answer used the model "@cf/meta/llama-3.3-70b-instruct-fp8-fast" for the reason "long_question"

  Scenario: With routing disabled every question goes to the large model
    Given the assistant is running with routing disabled
    When I ask "¿Quién es EMP-0004?"
    Then the answer used the model "@cf/meta/llama-3.3-70b-instruct-fp8-fast" for the reason "routing_disabled"

  Scenario: Only the last history messages reach the model
    Given the assistant is running with a history window of 2 and a spy model
    When I ask "¿Quién es EMP-0004?" after a conversation of 4 messages
    Then the model received only the last 2 history messages and the question

  Scenario: A gateway cache hit counts as a cached call and costs nothing
    Given the assistant is running on the gateway and the gateway answers from its cache
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer reports a cost of 0 and 1 cached calls

  Scenario: A gateway failure answers 502 with the request id
    Given the assistant is running on the gateway and the gateway fails with status 500
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 502
    And the body says "model unavailable" with the request id of the response
    And the log has one error event of type "ModelUnavailableError"
    And the log never contains the Cloudflare token

  Scenario: Metrics add up the cost of every answer
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    And I ask "Compara a los empleados de Finanzas"
    And I read the metrics
    Then the metrics cost is the sum of the cost of both answers
