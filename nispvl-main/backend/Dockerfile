FROM python:3.11-slim

# Тайм-аут и повторы загрузки пакетов можно задать при сборке:
#   docker compose build --build-arg PIP_DEFAULT_TIMEOUT=300 backend
ARG PIP_DEFAULT_TIMEOUT=120
ARG PIP_RETRIES=10
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg \
    PIP_DEFAULT_TIMEOUT=${PIP_DEFAULT_TIMEOUT} PIP_RETRIES=${PIP_RETRIES} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

WORKDIR /srv/backend
# Зависимости ставятся отдельным слоем по зафиксированным версиям (constraints.txt):
# без перебора версий резолвером и с кэшем слоя Docker при изменении только кода.
COPY pyproject.toml constraints.txt ./
RUN mkdir app && touch app/__init__.py \
    && pip install --only-binary=:all: -c constraints.txt . \
    && pip uninstall -y agro-sevooborot-backend
COPY app ./app
RUN pip install --no-deps .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
