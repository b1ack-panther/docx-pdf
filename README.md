# Bulk DOCX-to-PDF Conversion Service

Asynchronous microservice for batch conversion of DOCX files to PDF. Built with FastAPI, Celery, Redis, and PostgreSQL.

## Overview

This service handles large batches of document conversions asynchronously to avoid blocking the API or causing timeouts.

### Features

- **Asynchronous Processing**: Background file conversion via Celery.
- **Scalable**: API and Workers can be scaled independently.
- **Reliable**: Uses Celery Chords to finalize jobs only after all conversions are complete.
- **Fault Tolerant**: Tracks status per file; individual failures do not stop the entire job.
- **Dockerized**: Full environment setup with Docker Compose.

## Tech Stack

- **API**: FastAPI
- **Worker**: Celery
- **Broker**: Redis
- **Database**: PostgreSQL
- **Engine**: LibreOffice (Headless)
- **Containerization**: Docker

## Architecture

1. Client uploads a ZIP file to `POST /jobs`.
2. API saves the file and offloads processing to Celery, returning a Job ID immediately.
3. A background task unzips files and schedules individual conversion tasks.
4. Workers convert each file to PDF in parallel.
5. A final callback task zips the results and marks the job as COMPLETED.

## Getting Started

### Prerequisites

- Docker
- Docker Compose

### Running the Service

1. Clone the repository:

   ```bash
   git clone https://github.com/b1ack-panther/docx-pdf.git
   cd docx-pdf
   ```

2. Start the stack:

   ```bash
   docker-compose up --build
   ```

3. Access API documentation:
   http://localhost:8000/docs

## Testing

Run tests using pytest:

```bash
pip install -r requirements.txt pytest httpx
python -m pytest
```

## API Reference

### 1. Submit a Job

- **Endpoint**: `POST /api/v1/jobs`
- **Body**: `multipart/form-data` (file: .zip)
- **Response**:
  ```json
  {
  	"job_id": "...",
  	"status": "PENDING"
  }
  ```

### 2. Check Job Status

- **Endpoint**: `GET /api/v1/jobs/{job_id}`

### 3. Download Results

- **Endpoint**: `GET /api/v1/jobs/{job_id}/download`

## Design Decisions

### LibreOffice

Used for high-fidelity conversions in Linux environments without requiring Microsoft Word.

### Celery Chords

Ensures the final archive is created only when all sub-tasks succeed, preventing race conditions.

### Non-blocking API

The upload endpoint returns immediately after saving the file; all processing (unzipping, conversion) happens in the background to ensure responsiveness.

## Project Structure

```plaintext
├── app/
│   ├── main.py          # Entry point
│   ├── tasks.py         # Celery tasks
│   ├── celery_worker.py # Celery configuration
│   ├── models.py        # Database models
│   ├── database.py      # DB connection
│   └── routers/         # API routes
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
