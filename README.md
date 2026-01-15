# Bulk DOCX-to-PDF Conversion Service

A robust, asynchronous microservice designed to handle high-volume batch conversions of DOCX files to PDF. Built with FastAPI, Celery, Redis, and PostgreSQL, completely containerized for easy deployment.

## 🚀 Overview

This service addresses the challenge of converting large batches (e.g., 1,000+ files) of documents without blocking clients or timing out.

### Key Features:

- **Asynchronous Processing**: Uses a message queue to handle file conversion in the background.
- **Scalable Architecture**: Separation of API (producer) and Worker (consumer) allows independent scaling.
- **Race Condition Handling**: Implements Celery Chords to ensure the final ZIP archive is created only after all individual files are processed.
- **Fault Tolerance**: Retry logic and status tracking per individual file; one bad file does not fail the whole job.
- **Dockerized**: Runs the entire stack (API, Worker, DB, Redis) with a single command.

## 🛠 Tech Stack

- **API**: Python 3.11 + FastAPI
- **Worker**: Celery (Distributed Task Queue)
- **Broker**: Redis
- **Database**: PostgreSQL (Stores Job and File state)
- **Conversion Engine**: LibreOffice (Headless mode)
- **Containerization**: Docker & Docker Compose

## 🏗 Architecture

1. **Client uploads a ZIP file** to `POST /jobs`.
2. **API saves the ZIP** to a shared Docker volume and offloads the "Processing" task to Celery. Returns a Job ID immediately.
3. **Job Processor (Async Task)** unzips the file, creates DB records for every file, and triggers a Celery Chord.
4. **Conversion Workers (Parallel)** pick up individual files and convert them using LibreOffice.
5. **Archiver (Callback)** triggers automatically once all conversion tasks finish, zipping the PDFs and marking the job as COMPLETED.

## 🏃 Getting Started

### Prerequisites

- Docker
- Docker Compose

### Installation & Running

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd docx-to-pdf-service
   ```

2. **Start the stack**:

   ```bash
   docker-compose up --build
   ```

   This will build the Python images (installing LibreOffice takes a moment) and spin up Postgres and Redis.

3. **Verify it's running**:
   API docs are available at: http://localhost:8000/docs

## 🧪 Testing

The service includes a comprehensive test suite covering the API endpoints and background workers.

**Run tests locally**:

```bash
pip install -r requirements.txt pytest httpx
python -m pytest
```

## 📖 API Reference

### 1. Submit a Job

Uploads a ZIP file containing DOCX documents.

- **Endpoint**: `POST /api/v1/jobs`
- **Body**: `multipart/form-data` with key `file` (must be a .zip).
- **Response**:
  ```json
  {
  	"job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  	"status": "PENDING"
  }
  ```

### 2. Check Job Status

Poll this endpoint to track progress.

- **Endpoint**: `GET /api/v1/jobs/{job_id}`
- **Response**:
  ```json
  {
  	"job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  	"status": "IN_PROGRESS",
  	"files": [
  		{ "filename": "doc1.docx", "status": "COMPLETED", "error": null },
  		{ "filename": "doc2.docx", "status": "PENDING", "error": null }
  	]
  }
  ```

### 3. Download Results

Streams the final ZIP containing converted PDFs.

- **Endpoint**: `GET /api/v1/jobs/{job_id}/download`
- **Response**: Binary ZIP file.

## 🧠 Design Decisions & Trade-offs

### Why LibreOffice?

While Python libraries like `docx2pdf` exist, they often require Microsoft Word installed (Windows only) or lack perfect formatting fidelity. LibreOffice Headless is the industry standard for reliable, formatting-preserved conversions in Linux/Docker environments.

### Why Celery "Chords"?

A common pitfall in bulk processing is knowing when the job is finished.

- **Naive Approach**: Have every worker check the DB: "Am I the last one?" This leads to race conditions where two workers finish simultaneously and both try to finalize the job.
- **My Approach (Chord)**: Celery handles this synchronization. The "Archive" task is a callback that the broker only executes after the group of conversion tasks has successfully returned. This guarantees data integrity.

### Handling "Blocking" Operations

The assignment requires handling 1,000+ files. Unzipping and inserting 1,000 DB records takes time.

- **Decision**: The API endpoint (`POST /jobs`) does not unzip the file. It only saves the raw upload and returns.
- **A background "Setup Task"** handles the unzipping and DB population. This ensures the API remains responsive under heavy load.

## 📂 Project Structure

```plaintext
├── app/
│   ├── main.py          # App entry point
│   ├── tasks.py         # Celery tasks (Logic for Unzip, Convert, Archive)
│   ├── celery_worker.py # Celery App config
│   ├── models.py        # SQLAlchemy Database models
│   ├── database.py      # DB Connection
│   └── routers/         # API Route definitions
├── Dockerfile           # Unified image for API and Worker
├── docker-compose.yml   # Infrastructure orchestration
└── requirements.txt     # Python dependencies
```

