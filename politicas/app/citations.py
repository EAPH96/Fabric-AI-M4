"""Validación de las citas de políticas de una respuesta (ADR 0018).

Solo se cita una política que devolvió una herramienta en la misma petición.
Si la respuesta cita un ``POL-`` con 3 dígitos que no está entre los id
devueltos, se reemplaza completa por ``NOT_FOUND_ANSWER``. Así el modelo no
puede responder «según la política POL-002» sin haberla consultado.
"""

import re

CITATION_PATTERN = re.compile(r"\bPOL-[0-9]{3}\b")
NOT_FOUND_ANSWER = (
    "No encontré esa información en las políticas. Pregunta por una política "
    "(POL-001) o un tema, como vacaciones."
)


def check_citations(answer, returned_ids):
    """Deja la respuesta si todas sus citas salieron de una herramienta.

    :param answer: Respuesta del agente, antes de enmascarar
    :type answer: str
    :param returned_ids: Id de las políticas que devolvió el catálogo en la
        petición
    :type returned_ids: collections.abc.Iterable[str]
    :return: La misma respuesta, o ``NOT_FOUND_ANSWER`` si cita una política
        que ninguna herramienta devolvió
    :rtype: str
    """
    returned = set(returned_ids)
    cited = set(CITATION_PATTERN.findall(answer))
    if cited <= returned:
        return answer
    return NOT_FOUND_ANSWER
