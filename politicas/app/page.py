"""Armado de la página web con el enlace al otro producto (ADR 0014 del HR).

El enlace se arma una sola vez al arrancar: ``render_index`` sustituye el
marcador ``<!-- COMPANION_LINK -->`` de ``index.html`` por un ``<a>`` con la URL
y el nombre escapados, o lo borra si ``COMPANION_URL`` está vacía. Así ``GET /``
no depende de JavaScript ni de una ruta nueva. El nombre siempre llega por
configuración: el módulo no sabe cuál es el otro producto.
"""

import html

COMPANION_MARKER = "<!-- COMPANION_LINK -->"


def companion_link_html(url, name):
    """Devuelve el enlace al otro producto, o nada si no hay URL.

    La URL y el nombre se escapan (también las comillas) para que no puedan
    salir del atributo ``href`` ni agregar etiquetas. Se abre en otra pestaña
    porque la conversación solo vive en esta (ADR 0001 del HR), y ``rel``
    impide que el otro producto controle esta página.

    :param url: URL del otro producto; vacía si no hay enlace
    :type url: str
    :param name: Texto visible del enlace
    :type name: str
    :return: Etiqueta ``<a data-testid="companion-link">`` o ``""``
    :rtype: str
    """
    if not url:
        return ""
    href = html.escape(url, quote=True)
    text = html.escape(name, quote=True)
    return (
        f'<a class="companion-link" data-testid="companion-link" href="{href}"'
        f' target="_blank" rel="noopener noreferrer">{text}</a>'
    )


def render_index(template, page):
    """Sustituye el marcador de la plantilla por el enlace al otro producto.

    :param template: HTML de ``index.html`` con el marcador
    :type template: str
    :param page: Configuración de la página
    :type page: app.config.PageSettings
    :return: HTML listo para servir, sin el marcador
    :rtype: str
    """
    link = companion_link_html(page.companion_url, page.companion_name)
    return template.replace(COMPANION_MARKER, link, 1)
