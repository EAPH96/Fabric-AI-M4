# Imagen del HR Assistant para Render (spec/04-production.md, punto 5).
FROM python:3.12-slim

# Sin archivos .pyc, log sin búfer (sale enseguida en Render) y pip sin caché.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/hr-assistant

# Primero las dependencias: la capa se reutiliza mientras requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

# El código queda en manos de root y solo se lee; el proceso corre con otro usuario.
COPY app ./app
COPY data ./data
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin hrassistant
USER hrassistant

EXPOSE 8000

# Render pone el puerto en PORT; en local se usa 8000. "exec" deja a uvicorn como
# proceso principal para que reciba las señales de apagado.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
