FROM python:3.11-slim

WORKDIR /app

# Copy Python files
COPY . .

# Install dependencies (minimal for now)
RUN pip install --no-cache-dir fastapi uvicorn redis

# Expose port
EXPOSE 8081

# Run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Run the dashboard as main service
CMD ["python", "dashboard.py"]
