FROM python:3.12-slim
WORKDIR /app
RUN adduser --disabled-password --no-create-home appuser
COPY intake/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY _lib/agentic_standards ./agentic_standards
COPY intake/ .
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
