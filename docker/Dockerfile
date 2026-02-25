FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY app /app/app
COPY scripts /app/scripts
COPY prompts /app/prompts

RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -e '.[pdf,docx,html]' \
 && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.10.0 \
 && pip install --no-cache-dir sentence-transformers>=3.0.0

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
