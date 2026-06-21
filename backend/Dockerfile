# Base image: official slim Python 3.12 build — small footprint, includes pip
FROM python:3.12-slim

# All following instructions run from /app inside the container (created if missing)
WORKDIR /app

# Copy just the dependency file first, so docker caches this layer and skips
# reinstalling packages when only application code changes
COPY requirements.txt .

# Install Python dependencies; --no-cache-dir keeps the image smaller by not
# storing pip's download cache inside it
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actual application code (after deps, so code edits don't invalidate the deps layer)
COPY app ./app

# Ensure Python output is unbuffered, so logs appear immediately in `docker logs`
# Prevent Python from writing .pyc bytecode files into the image
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Documents that this container listens on port 8000 (informational only — doesn't publish it)
EXPOSE 8000

# Default command if none is overridden — runs the FastAPI app with uvicorn,
# bound to all interfaces (0.0.0.0) so other containers can reach it
# Overridden per-service in docker-compose.yml (api runs uvicorn, sync runs app.sync)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
