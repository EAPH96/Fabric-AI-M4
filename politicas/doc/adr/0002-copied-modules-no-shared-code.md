# ADR 0002: Duplicación aceptada: los módulos se copian, no se comparten

Estado: aceptada

## Contexto

Políticas es el HR Assistant con otros datos, otras dos herramientas y otro modelo simulado. Doce de sus módulos
(reloj, errores, log, métricas, observabilidad, protocolo, enrutador, precios, seguridad, límite, compliance y
página) no tienen nada del dominio. La especificación 06 pide que cada servicio se construya y se despliegue solo,
y que Políticas no importe nada de `product/app/`.

## Decisión

- Los doce módulos sin dominio se copian de `product/app/` a `product/politicas/app/` sin cambios de lógica; solo
  cambian los docstrings que nombran al HR.
- Se adaptan seis módulos: `agent.py` (herramientas), `llm.py` (modelo simulado), `gateway.py` (`SYSTEM_PROMPT`),
  `config.py` (variables y valores por omisión), `tracing.py` (`LANGSMITH_PROJECT`) y `main.py` (título y
  catálogo); `static/index.html` cambia sus textos y agrega el aviso legal, con el mismo diseño y los mismos
  `data-testid`; `directory.py` se reemplaza por `policies.py`.
- `doc/architecture.md` de Políticas lista qué se copió y qué se adaptó; qa-style compara los módulos de seguridad
  de los dos productos.

## Alternativas descartadas

- Un paquete común instalable (`hr_core`): los dos Dockerfile necesitarían un contexto mayor que su carpeta, y un
  cambio para un producto podría romper el otro sin que su CI lo note.
- Importar desde `product/app/` con `sys.path`: acopla las imágenes y el paquete `app` de los dos chocaría.
- Generalizar el HR para que sirva cualquier catálogo: cambiaría el HR, que esta especificación no toca.

## Consecuencias

- Un arreglo en un módulo copiado hay que hacerlo dos veces; la lista de `architecture.md` dice dónde.
- Cada producto tiene sus propias pruebas y cobertura; Políticas no hereda las del HR.
- Una diferencia entre copias que no esté en la lista de adaptados es un error, no una variante.
