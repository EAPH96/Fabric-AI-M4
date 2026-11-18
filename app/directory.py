"""Directorio de empleados de solo lectura cargado desde un archivo JSON."""

import json
from pathlib import Path


class EmployeeDirectory:
    """Directorio de empleados que se carga una sola vez y nunca se modifica.

    Los métodos devuelven copias para que nadie altere los datos cargados.

    :param path: Ruta al archivo JSON con la lista de empleados
    :type path: str or pathlib.Path
    :raises ValueError: Si el archivo no contiene una lista de objetos
    """

    def __init__(self, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) for item in raw
        ):
            raise ValueError(f"{path} must contain a list of employee objects")
        self._employees = tuple(dict(item) for item in raw)

    def get_employee(self, employee_id):
        """Busca un empleado por su id exacto, por ejemplo ``EMP-0004``.

        :param employee_id: Id del empleado
        :type employee_id: str
        :return: Copia de los datos del empleado o ``None`` si no existe
        :rtype: dict or None
        """
        wanted = str(employee_id).strip()
        for employee in self._employees:
            if employee.get("id") == wanted:
                return dict(employee)
        return None

    def search_by_department(self, department):
        """Lista los empleados de un departamento, sin distinguir mayúsculas.

        :param department: Nombre del departamento
        :type department: str
        :return: Copias de los empleados del departamento (vacía si no hay)
        :rtype: list[dict]
        """
        wanted = str(department).strip().casefold()
        return [
            dict(employee)
            for employee in self._employees
            if str(employee.get("department", "")).casefold() == wanted
        ]

    def departments(self):
        """Lista los departamentos que existen, sin repetir y en orden de aparición.

        :return: Nombres de los departamentos
        :rtype: list[str]
        """
        names = []
        for employee in self._employees:
            name = employee.get("department")
            if name and name not in names:
                names.append(name)
        return names
