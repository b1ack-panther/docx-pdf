import pytest
from unittest.mock import patch
from app.models import Job, JobStatus

def test_submit_job_valid_zip(client):
    """
    Test uploading a valid zip file.
    Should return 202 Accepted and a Job ID.
    Mocks the Celery task to prevent actual execution.
    """
    # Create a dummy zip file in memory
    import io
    import zipfile
    
    file_like = io.BytesIO()
    with zipfile.ZipFile(file_like, "w") as zf:
        zf.writestr("test.docx", "dummy content")
    file_like.seek(0)

    # Mock the Celery .delay() call so we don't need Redis running
    with patch("app.tasks.process_incoming_job.delay") as mock_task:
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("test.zip", file_like, "application/zip")}
        )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    assert mock_task.called  # Verify Celery was triggered

def test_submit_job_invalid_extension(client):
    """Test that non-zip files are rejected immediately."""
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("image.png", b"fake", "image/png")}
    )
    assert response.status_code == 400
    assert "Only .zip files" in response.json()["detail"]

def test_get_job_status(client, db_session):
    """Test retrieving status for an existing job."""
    # Seed DB with a dummy job
    import uuid
    job_id = uuid.uuid4()
    job = Job(id=job_id, status=JobStatus.IN_PROGRESS)
    db_session.add(job)
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{str(job_id)}")
    
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"

def test_download_job_not_ready(client, db_session):
    """Test that downloading a non-complete job returns 400."""
    import uuid
    job_id = uuid.uuid4()
    job = Job(id=job_id, status=JobStatus.IN_PROGRESS)
    db_session.add(job)
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{str(job_id)}/download")
    assert response.status_code == 400