# SentinelAI backend
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# Copy the package source before the editable install: pyproject declares
# packages = ["app"], so setuptools needs app/ present at install time.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install -e .
COPY alembic ./alembic
COPY alembic.ini ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
