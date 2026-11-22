"""Catálogo de políticas de solo lectura cargado desde un archivo JSON.

Un tema coincide con una política si su ``topic`` o alguna de sus ``keywords``,
normalizados, son iguales al tema normalizado o están dentro de él (ADR 0003).
"""

import json
import unicodedata
from pathlib import Path

POLICY_FIELDS = ("id", "title", "text")
SUMMARY_FIELDS = ("id", "title")


def normalize(text):
    """Quita acentos, mayúsculas y espacios en los extremos de un texto.

    Los acentos se quitan descomponiendo con NFKD y borrando las marcas
    combinantes, así ``Viáticos`` y ``viaticos`` quedan iguales.

    :param text: Texto a normalizar
    :type text: str
    :return: Texto sin acentos, en minúsculas y sin espacios en los extremos
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return without_marks.casefold().strip()


def _policy_terms(policy):
    """Devuelve el ``topic`` y las ``keywords`` de una política, en ese orden.

    :param policy: Política del archivo
    :type policy: dict
    :return: Términos de la política tal como están escritos en el archivo
    :rtype: list[str]
    """
    terms = []
    topic = policy.get("topic")
    if isinstance(topic, str) and topic:
        terms.append(topic)
    keywords = policy.get("keywords")
    if isinstance(keywords, list):
        terms.extend(word for word in keywords if isinstance(word, str) and word)
    return terms


class PolicyCatalog:
    """Catálogo de políticas que se carga una sola vez y nunca se modifica.

    Los métodos devuelven copias para que nadie altere los datos cargados.

    :param path: Ruta al archivo JSON con la lista de políticas
    :type path: str or pathlib.Path
    :raises ValueError: Si el archivo no contiene una lista de objetos
    """

    def __init__(self, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) for item in raw
        ):
            raise ValueError(f"{path} must contain a list of policy objects")
        self._policies = tuple(dict(item) for item in raw)
        self._normalized_terms = tuple(
            tuple(normalize(term) for term in _policy_terms(policy))
            for policy in self._policies
        )

    def get_policy(self, policy_id):
        """Busca una política por su id exacto, por ejemplo ``POL-003``.

        :param policy_id: Id de la política
        :type policy_id: str
        :return: Copia con ``id``, ``title`` y ``text``, o ``None`` si no existe
        :rtype: dict or None
        """
        wanted = str(policy_id).strip()
        for policy in self._policies:
            if policy.get("id") == wanted:
                return {name: policy.get(name) for name in POLICY_FIELDS}
        return None

    def search(self, topic):
        """Lista las políticas cuyo topic o alguna keyword coincide con el tema.

        Coincide si el término normalizado es igual al tema normalizado o está
        dentro de él (``días de vacaciones`` encuentra ``vacaciones``).

        :param topic: Tema que se busca
        :type topic: str
        :return: ``id`` y ``title`` de cada política encontrada, en el orden del
            archivo (vacía si no hay ninguna)
        :rtype: list[dict]
        """
        wanted = normalize(topic)
        return [
            {name: policy.get(name) for name in SUMMARY_FIELDS}
            for policy, terms in zip(self._policies, self._normalized_terms)
            if any(term and term in wanted for term in terms)
        ]

    def terms(self):
        """Lista los topics y keywords en el orden del archivo.

        Por política, primero su ``topic`` y luego sus ``keywords``; un término
        repetido aparece las veces que esté en el archivo.

        :return: Términos tal como están escritos en el archivo
        :rtype: list[str]
        """
        return [term for policy in self._policies for term in _policy_terms(policy)]
