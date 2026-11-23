"""Pruebas de la detección y el enmascaramiento de datos personales (spec 09).

Los datos son ficticios: la CURP genérica ``XEXX010101HDFXXX04``, el RFC
genérico ``XAXX010101000`` y el dominio ``ejemplo.com``.
"""

from app.pii import PII_RULES, mask_pii

CURP = "XEXX010101HDFXXX04"
EMAIL = "ana.perez@ejemplo.com"


def test_rules_follow_the_order_and_marks_of_the_specification():
    names_and_marks = [(name, mark) for name, _, mark in PII_RULES]

    assert names_and_marks == [
        ("curp", "[CURP]"),
        ("rfc", "[RFC]"),
        ("email", "[CORREO]"),
        ("clabe", "[CLABE]"),
        ("card", "[TARJETA]"),
        ("nss", "[NSS]"),
        ("phone", "[TELEFONO]"),
    ]


def test_every_type_is_replaced_by_its_mark():
    text = (
        f"CURP {CURP}, RFC XAXX010101000, correo {EMAIL}, "
        "CLABE 012180001234567897, tarjeta 4111 1111 1111 1111, "
        "NSS 12345678901 y teléfono 5512345678."
    )

    masked, types = mask_pii(text)

    assert masked == (
        "CURP [CURP], RFC [RFC], correo [CORREO], CLABE [CLABE], "
        "tarjeta [TARJETA], NSS [NSS] y teléfono [TELEFONO]."
    )
    assert types == ["card", "clabe", "curp", "email", "nss", "phone", "rfc"]


def test_a_curp_is_not_also_counted_as_an_rfc():
    assert mask_pii(f"Mi CURP es {CURP}") == ("Mi CURP es [CURP]", ["curp"])


def test_a_clabe_is_not_counted_as_a_card_or_a_phone():
    masked = mask_pii("Mi CLABE es 012180001234567897")

    assert masked == ("Mi CLABE es [CLABE]", ["clabe"])


def test_a_card_is_masked_with_spaces_dashes_or_no_separators():
    text = "Tarjetas 4111 1111 1111 1111, 5500-0000-0000-0004 y 4222222222222"

    masked, types = mask_pii(text)

    assert masked == "Tarjetas [TARJETA], [TARJETA] y [TARJETA]"
    assert types == ["card"]


def test_a_phone_is_masked_with_spaces_or_dashes():
    masked = mask_pii("Llámame al 55 1234 5678 o al 55-8765-4321")

    assert masked == ("Llámame al [TELEFONO] o al [TELEFONO]", ["phone"])


def test_ids_and_dates_are_not_personal_data():
    text = "EMP-0004 pidió la POL-003 el 2019-03-04"

    assert mask_pii(text) == (text, [])


def test_types_are_sorted_and_never_repeated():
    text = f"Escribe a {EMAIL} o a luis@ejemplo.com; mi CURP es {CURP}"

    masked, types = mask_pii(text)

    assert types == ["curp", "email"]
    assert EMAIL not in masked
    assert CURP not in masked
