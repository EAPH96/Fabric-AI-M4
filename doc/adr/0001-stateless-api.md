# ADR 0001: API sin estado con historial en el cliente

Estado: aceptada

## Contexto

El HR Assistant debe escalar corriendo más copias de la API. Si el servidor guardara conversaciones,
cada petición tendría que llegar a la misma copia o haría falta un almacén compartido.

## Decisión

- La API no guarda nada entre peticiones. El navegador guarda el historial y lo manda en `history`
  en cada `POST /ask`.
- `main.py` crea un `Agent` nuevo por petición. Lo único compartido es de solo lectura: la
  configuración, el modelo y el directorio de empleados cargado al arrancar.
- `create_app(settings, model, directory)` recibe sus dependencias para que las pruebas inyecten
  las suyas; `app = create_app()` las construye desde el entorno.

## Consecuencias

- Cualquier copia atiende cualquier petición; `GET /health` devuelve el `pid` para comprobarlo.
- El cliente controla el historial: la API valida su forma (`role` en `user` o `assistant`).
  Limitar su tamaño queda pendiente.
- Recargar la página borra la conversación; es aceptable en esta sesión.
