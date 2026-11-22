Feature: The page links to the other HR product
  As a member of the HR staff
  I want a link in the page header to the HR policies assistant
  So that I can move between both products without looking for the address

  Scenario: Without a companion URL the page shows no link
    Given the assistant is running without a companion URL
    When I open the home page
    Then the page has no companion link

  Scenario: With a companion URL the header links to the policies assistant
    Given the assistant is running with the companion URL "https://politicas.example.com/"
    When I open the home page
    Then the page header has a companion link named "Asistente de políticas de RH"
    And the companion link opens "https://politicas.example.com/"

  Scenario: The companion name changes the text of the link
    Given the assistant is running with the companion URL "https://politicas.example.com/" named "Políticas de RH"
    When I open the home page
    Then the page header has a companion link named "Políticas de RH"

  Scenario: The companion link opens in a new tab without access to this page
    Given the assistant is running with the companion URL "https://politicas.example.com/"
    When I open the home page
    Then the companion link opens in a new tab
    And the companion link gives the other product no access to this page

  Scenario: The link changes neither the open page nor the key on the questions
    Given the assistant is running with the companion URL "https://politicas.example.com/"
    When I open the home page and ask without a key
    Then the home page answers 200
    And the question answers 401
