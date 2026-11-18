Feature: Ask the HR Assistant about employees
  As a member of the HR staff
  I want to ask questions about employees
  So that I get answers from the employee directory without the server storing anything

  Scenario: Asking for an existing employee
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer mentions "Jorge Díaz"
    And the tools used are "get_employee"
    And the number of steps is 2

  Scenario: Asking for an unknown employee still gets an answer
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-9999?"
    Then the response status is 200
    And the answer mentions "EMP-9999"
    And the answer mentions "not found"

  Scenario: Asking for a department lists its people
    Given the assistant is running with the default settings
    When I ask "¿Quiénes trabajan en Finanzas?"
    Then the response status is 200
    And the answer mentions "Sofía Gómez"
    And the tools used are "search_by_department"

  Scenario: A question without an employee id or a department gets help
    Given the assistant is running with the default settings
    When I ask "¿Qué tal el clima hoy?"
    Then the response status is 200
    And the answer is "Pregúntame por un empleado (EMP-0001) o un departamento."
    And no tools were used

  Scenario: An empty question is rejected
    Given the assistant is running with the default settings
    When I send an empty question
    Then the response status is 422

  Scenario: A question longer than the limit is rejected
    Given the assistant is running with the default settings
    When I ask a question of 2001 characters
    Then the response status is 422

  Scenario: The step cap stops the loop with a fixed message
    Given the assistant is running with a step cap of 1
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer is "No pude completar la respuesta. Intenta con una pregunta más concreta."
    And the tools used are "get_employee"
    And the number of steps is 1

  Scenario: The history comes from the client and is not stored
    Given the assistant is running with the default settings
    When I ask "¿Quién es EMP-0004?" with a previous conversation
    And I ask "¿Quién es EMP-0004?"
    Then both answers are the same
    And the second question counted fewer input tokens than the first
