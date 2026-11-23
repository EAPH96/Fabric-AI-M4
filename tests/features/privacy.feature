Feature: Personal data is masked and every rejection is audited
  As the owner of the HR Assistant in production
  I want personal data masked before the model sees it and every rejected request audited
  So that no CURP, email or key leaks through the assistant, its traces or its logs

  Scenario: A question with a CURP and an email is masked before the model
    Given the assistant is running with a spy model
    When I ask "Mi CURP es XEXX010101HDFXXX04 y mi correo es ana.perez@ejemplo.com, ¿quién es EMP-0004?"
    Then the response status is 200
    And the masked types are "curp, email"
    And the model received "[CURP]"
    And the model received "[CORREO]"
    And the model never received "XEXX010101HDFXXX04"
    And the model never received "ana.perez@ejemplo.com"
    And the log has a pii detected event in the "question" with the types "curp, email"
    And the log never contains "XEXX010101HDFXXX04"
    And the log never contains "ana.perez@ejemplo.com"

  Scenario: A phone number in the history is masked before the model
    Given the assistant is running with a spy model
    When I ask "¿Y en qué departamento está?" after saying "Mi teléfono es 55 1234 5678"
    Then the response status is 200
    And the masked types are "phone"
    And the model received "[TELEFONO]"
    And the model never received "55 1234 5678"
    And the log has a pii detected event in the "history" with the types "phone"

  Scenario: An email in the answer is masked before it is returned
    Given the assistant is running with a model that answers "Escribe a rh.ayuda@ejemplo.com para más detalles"
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer is "Escribe a [CORREO] para más detalles"
    And the masked types are "email"
    And the log has a pii detected event in the "answer" with the types "email"
    And the log never contains "rh.ayuda@ejemplo.com"

  Scenario: Personal data in the question, the history and the answer is reported once per place
    Given the assistant is running with a model that answers "Escribe a rh.ayuda@ejemplo.com para más detalles"
    When I ask "Mi NSS es 12345678901, ¿y mis vacaciones?" after saying "Mi CURP es XEXX010101HDFXXX04"
    Then the response status is 200
    And the masked types are "curp, email, nss"
    And the log has 3 pii detected events
    And the log has a pii detected event in the "question" with the types "nss"
    And the log has a pii detected event in the "history" with the types "curp"
    And the log has a pii detected event in the "answer" with the types "email"

  Scenario: A question without personal data is not changed
    Given the assistant is running with a spy model
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And no personal data was masked
    And the answer is "Respuesta del modelo espía"
    And the model received "¿Quién es EMP-0004?"

  Scenario: The chain trace only sees the masked question and the masked answer
    Given the assistant is running with a spy tracer and a model that answers "Escribe a rh.ayuda@ejemplo.com para más detalles"
    When I ask "Mi CURP es XEXX010101HDFXXX04, ¿quién es EMP-0004?"
    Then the response status is 200
    And the chain trace received "[CURP]" and returned "[CORREO]"
    And the chain trace never contains "XEXX010101HDFXXX04"
    And the chain trace never contains "rh.ayuda@ejemplo.com"

  Scenario: Asking without a key is audited as missing
    Given the assistant is running without a key in the client
    When I ask without a key
    Then the response status is 401
    And the log has one auth failed event with only the reason "missing"

  Scenario: Asking with an empty key is audited as missing
    Given the assistant is running without a key in the client
    When I ask with the key ""
    Then the response status is 401
    And the log has one auth failed event with only the reason "missing"

  Scenario: Asking with a wrong key is audited as invalid and the key is never logged
    Given the assistant is running without a key in the client
    When I ask with the key "not-the-right-key-0000"
    Then the response status is 401
    And the log has one auth failed event with only the reason "invalid"
    And the log never contains "not-the-right-key-0000"

  Scenario: Passing the limit is audited with the client and the seconds to wait
    Given the assistant allows 1 question per minute
    When I ask 2 questions in a row
    Then the response status is 429
    And the log has one rate limited event for the client "tests" with the Retry-After seconds
