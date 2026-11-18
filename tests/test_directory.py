"""Pruebas del directorio de empleados de solo lectura."""


def test_employee_is_found_by_id(directory):
    employee = directory.get_employee("EMP-0004")

    assert employee["name"] == "Jorge Díaz"
    assert employee["department"] == "Tecnología"


def test_unknown_employee_is_reported_as_missing(directory):
    assert directory.get_employee("EMP-9999") is None


def test_department_search_ignores_case_and_unknown_department_is_empty(directory):
    found = directory.search_by_department("TECNOLOGÍA")

    names = {employee["name"] for employee in found}
    assert names == {"Ana López", "Marta Ruiz", "Jorge Díaz"}
    assert directory.search_by_department("Marketing") == []
    assert set(directory.departments()) == {"Tecnología", "Ventas", "Finanzas"}
