"""Claves por cliente: lectura de ``API_KEYS`` e identificación (ADR 0010).

``API_KEYS`` tiene la forma ``cliente:clave,cliente2:clave2``. Un error nombra
el número de la entrada y su largo, nunca su valor: el mensaje termina en la
salida de arranque, que cualquiera con acceso a la plataforma puede leer.

``ApiKeyAuth`` compara la clave recibida con ``hmac.compare_digest`` contra
todas las claves, sin cortar al primer acierto, para que el tiempo de
respuesta no revele qué clave existe.
"""

import hmac
import re
from types import MappingProxyType

from app.errors import ConfigError

ENTRY_SEPARATOR = ","
CLIENT_SEPARATOR = ":"
# El nombre del cliente va en el log y en las trazas: solo caracteres seguros.
CLIENT_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
KEY_ENCODING = "utf-8"
# Ida y vuelta exacta de cualquier texto, para que un encabezado raro no truene.
KEY_ENCODING_ERRORS = "surrogatepass"


def _entry_problem(has_separator, client, key, previous):
    """Dice qué está mal en una entrada ya partida, sin mencionar su valor.

    :param has_separator: Si la entrada tiene ``:`` entre cliente y clave
    :type has_separator: bool
    :param client: Nombre del cliente de la entrada, sin espacios alrededor
    :type client: str
    :param key: Clave de la entrada, sin espacios alrededor
    :type key: str
    :param previous: Claves por cliente de las entradas anteriores
    :type previous: dict[str, str]
    :return: Descripción del problema, o ``None`` si la entrada es válida
    :rtype: str or None
    """
    if not has_separator:
        return "has no ':' between client and key"
    if not CLIENT_PATTERN.fullmatch(client):
        return "has an invalid client name (use 1 to 64 of A-Z a-z 0-9 _ -)"
    if not key or any(character.isspace() for character in key):
        return "has an empty key or a key with spaces"
    if client in previous:
        return "repeats a client"
    if key in previous.values():
        return "repeats the key of another client"
    return None


def _malformed(number, entry, reason):
    """Crea el error de una entrada inválida con su número y su largo.

    :param number: Número de la entrada, contando desde 1
    :type number: int
    :param entry: Entrada inválida; solo se usa su largo
    :type entry: str
    :param reason: Qué está mal, sin el valor
    :type reason: str
    :return: Error listo para lanzar
    :rtype: app.errors.ConfigError
    """
    return ConfigError(
        f"API_KEYS entry {number} is malformed (length {len(entry)}): {reason}; "
        "expected client:key"
    )


def parse_api_keys(raw):
    """Convierte ``API_KEYS`` en un diccionario de solo lectura ``{cliente: clave}``.

    Las entradas se separan con coma y se parten en el **primer** ``:``, así
    que una clave puede tener ``:``. Se recortan los espacios alrededor de cada
    entrada. Un texto vacío da un diccionario vacío.

    :param raw: Valor de ``API_KEYS``
    :type raw: str
    :return: Claves por nombre de cliente
    :rtype: types.MappingProxyType
    :raises app.errors.ConfigError: Si una entrada no tiene ``:``, el cliente no
        es válido, la clave está vacía o tiene espacios, o se repite un cliente
        o una clave. El mensaje nombra la entrada y su largo, nunca su valor.
    """
    keys = {}
    if not raw.strip():
        return MappingProxyType(keys)
    for number, part in enumerate(raw.split(ENTRY_SEPARATOR), start=1):
        entry = part.strip()
        client, separator, key = entry.partition(CLIENT_SEPARATOR)
        client, key = client.strip(), key.strip()
        reason = _entry_problem(bool(separator), client, key, keys)
        if reason:
            # Sin excepción encadenada: ningún rastro debe mostrar la entrada.
            raise _malformed(number, entry, reason) from None
        keys[client] = key
    return MappingProxyType(keys)


class ApiKeyAuth:
    """Identifica al cliente por su clave, en tiempo constante.

    :param keys: Claves por nombre de cliente, de ``parse_api_keys``
    :type keys: collections.abc.Mapping[str, str]
    """

    def __init__(self, keys):
        self._keys = tuple(
            (client, key.encode(KEY_ENCODING, KEY_ENCODING_ERRORS))
            for client, key in keys.items()
        )

    def identify(self, api_key):
        """Devuelve el cliente dueño de la clave, o ``None`` si no es de nadie.

        Compara bytes con ``hmac.compare_digest`` contra **todas** las claves,
        aunque ya haya encontrado al dueño.

        :param api_key: Valor del encabezado ``X-API-Key`` o ``None``
        :type api_key: str or None
        :return: Nombre del cliente, o ``None`` si falta o no es válida
        :rtype: str or None
        """
        if not api_key:
            return None
        candidate = api_key.encode(KEY_ENCODING, KEY_ENCODING_ERRORS)
        owner = None
        for client, key in self._keys:
            if hmac.compare_digest(candidate, key) and owner is None:
                owner = client
        return owner
