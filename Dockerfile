# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files to disc
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
# We need LibreOffice for conversion and generic tools (curl, netcat) for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libreoffice \
    libreoffice-writer \
    default-jre \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create a directory for shared file storage
RUN mkdir -p /app/storage

# Create a non-root user for security (optional but recommended for production readiness)
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# The command is omitted here because we will specify different commands
# for the API and the Worker in docker-compose.yml