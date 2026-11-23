Feature: Business metrics in /metrics
  As the person who runs the HR Assistant
  I want the metrics to say how the assistant is used and what each part costs
  So that I can see the models, the tools, the cache and the answers that were cut

  Scenario: Answers are counted by the model that gave them
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    And I ask "Compara a los empleados de Finanzas"
    And I read the metrics
    Then the answers came from 2 different models
    And each model counts its answers with the cost of those answers

  Scenario: Every executed tool is counted
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    And I ask "¿Quién es EMP-0004?"
    And I ask "¿Quién trabaja en Finanzas?"
    And I read the metrics
    Then the metrics count 2 runs of "get_employee" and 1 run of "search_by_department"
    And the tools in the metrics add up to the tools used by the answers

  Scenario: A request without a key is counted as 4xx and the status classes add up to the requests
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    And I ask "¿Quién es EMP-0004?" without a key
    And I read the metrics
    Then the status classes are 1 "2xx", 1 "4xx" and 0 "5xx"
    And the status classes add up to the requests
    And the metrics count 1 answer in total by model

  Scenario: An answer cut by the step cap is counted as stopped
    Given the assistant is running with a cap of 1 step
    When I ask "¿Quién es EMP-0004?"
    And I read the metrics
    Then the answer was cut by the step cap
    And the metrics count 1 stopped answer

  Scenario: Answers served by the gateway cache are counted in cached_calls and cost nothing
    Given the assistant is running on the gateway and the gateway answers from its cache
    When I ask "¿Quién es EMP-0004?"
    And I read the metrics
    Then the metrics count 1 cached call
    And the model of the answer counts 1 answer with a cost of 0
