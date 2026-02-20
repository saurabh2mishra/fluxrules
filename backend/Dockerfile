FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN uv sync

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]