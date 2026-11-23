Feature: Personal data is masked, citations are checked and every rejection is audited
  As the owner of the HR policies assistant in production
  I want personal data masked, only real citations kept and every rejected request audited
  So that no one leaks personal data or reads a policy the assistant never consulted

  Scenario: A question with a CURP and an email is masked before the model
    Given the assistant is running with a spy model
    When I ask "Mi CURP es XEXX010101HDFXXX04 y mi correo es ana.perez@ejemplo.com, ¿cuántos días de vacaciones me tocan?"
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
    When I ask "¿Y cuántos días de vacaciones?" after saying "Mi teléfono es 55 1234 5678"
    Then the response status is 200
    And the masked types are "phone"
    And the model received "[TELEFONO]"
    And the model never received "55 1234 5678"
    And the log has a pii detected event in the "history" with the types "phone"

  Scenario: An email in the answer is masked before it is returned
    Given the assistant is running with a model that answers "Escribe a rh.ayuda@ejemplo.com para más detalles"
    When I ask "¿Cuántos días de vacaciones me tocan?"
    Then the response status is 200
    And the answer is "Escribe a [CORREO] para más detalles"
    And the masked types are "email"
    And the log has a pii detected event in the "answer" with the types "email"
    And the log never contains "rh.ayuda@ejemplo.com"

  Scenario: A question without personal data is not changed
    Given the assistant is running with a spy model
    When I ask "¿Cuántos días de vacaciones me tocan?"
    Then the response status is 200
    And no personal data was masked
    And the answer is "Respuesta del modelo espía"
    And the model received "¿Cuántos días de vacaciones me tocan?"

  Scenario: The chain trace only sees the masked question and the masked answer
    Given the assistant is running with a spy tracer and a model that answers "Escribe a rh.ayuda@ejemplo.com para más detalles"
    When I ask "Mi CURP es XEXX010101HDFXXX04, ¿cuántos días de vacaciones me tocan?"
    Then the response status is 200
    And the chain trace received "[CURP]" and returned "[CORREO]"
    And the chain trace never contains "XEXX010101HDFXXX04"
    And the chain trace never contains "rh.ayuda@ejemplo.com"

  Scenario: A policy the model cites without consulting it is replaced by the not found text
    Given the assistant is running with a model that answers "Según la política POL-002 te toca una prima vacacional"
    When I ask "¿De cuánto es la prima vacacional?"
    Then the response status is 200
    And the answer is "No encontré esa información en las políticas. Pregunta por una política (POL-001) o un tema, como vacaciones."
    And no tools were used
    And no personal data was masked

  Scenario: A policy returned by a tool keeps its citation
    Given the assistant is running with the default settings
    When I ask "¿Qué dice la política POL-003?"
    Then the response status is 200
    And the answer mentions "POL-003"
    And the tools used are "get_policy"

  Scenario: Asking without a key is audited as missing
    Given the assistant is running without a key in the client
    When I ask without a key
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
