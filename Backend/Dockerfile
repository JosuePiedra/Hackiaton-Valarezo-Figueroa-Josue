# Base: establece variables y la imagen base de Python
FROM python:3.12-slim as python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=2.1.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    # Rutas
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# Builder: instala dependencias de sistema y crea el entorno virtual con Poetry
FROM python-base as builder-base
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl \
    build-essential \
    gcc \
    python3-dev \
    libffi-dev

# Instalar Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR $PYSETUP_PATH
# Copia los archivos de configuración de Poetry
COPY pyproject.toml poetry.lock* ./
# Instala las dependencias sin incluir el paquete actual (opcionalmente, puedes quitar --no-root si quieres instalarlo)
RUN poetry install --no-root

# Imagen para desarrollo: incluye recarga en caliente (reload)
FROM python-base as development
WORKDIR $PYSETUP_PATH
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH

# Copia el código fuente de la aplicación
WORKDIR /app
COPY . .

EXPOSE 8888
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8888"]

# Imagen para producción
FROM python-base as production
WORKDIR /app
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH
COPY . .

EXPOSE 1000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1000"]
