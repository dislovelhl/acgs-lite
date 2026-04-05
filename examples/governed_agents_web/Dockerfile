FROM python:3.11-slim

WORKDIR /app

# Copy acgs_auth0 package
COPY packages/acgs_auth0 /app/packages/acgs_auth0

# Copy web demo and constitution
COPY examples/governed_agents_web /app/examples/governed_agents_web
COPY examples/governed_agents/constitutions /app/examples/governed_agents/constitutions

# Install deps
RUN pip install --no-cache-dir pyyaml httpx fastapi uvicorn python-multipart

WORKDIR /app/examples/governed_agents_web

ENV PYTHONPATH=/app/packages

EXPOSE 7860

CMD ["python", "main.py"]
