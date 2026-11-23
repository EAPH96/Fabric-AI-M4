"""Detección y enmascaramiento de datos personales con ``re`` (ADR 0018).

``PII_RULES`` lista los tipos en el orden de la especificación 09. Cada regla
se aplica sobre el texto ya enmascarado por las anteriores: así una CURP no se
cuenta también como RFC, ni una CLABE como tarjeta o teléfono. Todas usan
límites de palabra, para que un id como ``EMP-0004`` o ``POL-003`` no sea PII.

Este módulo nunca devuelve ni registra el valor detectado: solo el texto con
las marcas y los nombres de los tipos.
"""

import re

# CURP: 4 letras, 6 dígitos, H o M, 5 letras y 2 caracteres alfanuméricos.
CURP_PATTERN = re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]{2}\b", re.IGNORECASE)
# RFC de persona física o moral: 3 o 4 letras, 6 dígitos y 3 alfanuméricos.
RFC_PATTERN = re.compile(r"\b[A-ZÑ]{3,4}\d{6}[A-Z\d]{3}\b", re.IGNORECASE)
# Correo: usuario, @, dominio con al menos un punto y una terminación de letras.
EMAIL_PATTERN = re.compile(r"\b[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}\b")
# CLABE: 18 dígitos seguidos.
CLABE_PATTERN = re.compile(r"\b\d{18}\b")
# Tarjeta: de 13 a 16 dígitos, con o sin un espacio o guion entre ellos.
CARD_PATTERN = re.compile(r"\b\d(?:[ -]?\d){12,15}\b")
# NSS: 11 dígitos seguidos.
NSS_PATTERN = re.compile(r"\b\d{11}\b")
# Teléfono: 10 dígitos, con o sin un espacio o guion entre ellos.
PHONE_PATTERN = re.compile(r"\b\d(?:[ -]?\d){9}\b")

PII_RULES = (
    ("curp", CURP_PATTERN, "[CURP]"),
    ("rfc", RFC_PATTERN, "[RFC]"),
    ("email", EMAIL_PATTERN, "[CORREO]"),
    ("clabe", CLABE_PATTERN, "[CLABE]"),
    ("card", CARD_PATTERN, "[TARJETA]"),
    ("nss", NSS_PATTERN, "[NSS]"),
    ("phone", PHONE_PATTERN, "[TELEFONO]"),
)


def mask_pii(text):
    """Reemplaza cada dato personal del texto por la marca de su tipo.

    Las reglas se aplican en el orden de ``PII_RULES``, cada una sobre el
    resultado de la anterior.

    :param text: Texto que puede traer datos personales
    :type text: str
    :return: Texto con las marcas y los tipos encontrados, ordenados
        alfabéticamente y sin repetir (lista vacía si no hubo ninguno)
    :rtype: tuple[str, list[str]]
    """
    found = set()
    for name, pattern, mark in PII_RULES:
        text, count = pattern.subn(mark, text)
        if count:
            found.add(name)
    return text, sorted(found)


def merge_types(*groups):
    """Une varias listas de tipos en una sola, ordenada y sin repetir.

    :param groups: Listas de tipos de ``mask_pii``
    :type groups: list[str]
    :return: Tipos ordenados alfabéticamente y sin repetir
    :rtype: list[str]
    """
    return sorted({name for group in groups for name in group})
