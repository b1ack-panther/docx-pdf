import os
import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.tasks import process_incoming_job, convert_file_task, archive_job_task
from app.models import Job, JobFile, JobStatus, FileStatus

# Helper to create a dummy zip file
@pytest.fixture
def dummy_zip(tmp_path):
    zip_path = tmp_path / "upload.zip"
    import zipfile
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("doc1.docx", "content")
        zf.writestr("ignore_me.txt", "content") # Should be ignored
    return str(zip_path)

def test_process_incoming_job_unzipping(db_session, dummy_zip):
    """
    Test that the worker unzips files and populates the DB.
    Mocks 'chord' so we don't try to dispatch to Redis.
    """
    # Create Job in DB
    job_id = str(uuid.uuid4())
    job = Job(id=uuid.UUID(job_id), status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    # Mock celery chord
    with patch("app.tasks.chord") as mock_chord:
        # Run the task function directly (synchronously)
        process_incoming_job(job_id, dummy_zip)

    # Reload job from DB
    db_session.refresh(job)
    
    # Assertions
    assert job.status == JobStatus.IN_PROGRESS
    assert len(job.files) == 1 # Should only pick up the .docx, not .txt
    assert job.files[0].filename == "doc1.docx"
    assert mock_chord.called # Verify it tried to trigger the next step

def test_convert_file_task_success(db_session, tmp_path):
    """
    Test individual file conversion. 
    Mocks subprocess.run to simulate LibreOffice success.
    """
    # Setup Data
    job_id = str(uuid.uuid4())
    job_file = JobFile(job_id=uuid.UUID(job_id), filename="test.docx", status=FileStatus.PENDING)
    db_session.add(job_file)
    db_session.commit()
    
    # Mock subprocess.run to return success (returncode 0)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        # Run task
        convert_file_task(job_id, "test.docx", job_file.id)

    # Verify DB update
    db_session.refresh(job_file)
    assert job_file.status == FileStatus.COMPLETED
    
    # Verify the correct command was called (security/logic check)
    args, _ = mock_run.call_args
    assert "libreoffice" in args[0]
    assert "--convert-to" in args[0]

def test_convert_file_task_failure(db_session):
    """
    Test handling of LibreOffice failure.
    Mocks subprocess.run to simulate a crash or error.
    """
    job_id = str(uuid.uuid4())
    job_file = JobFile(job_id=uuid.UUID(job_id), filename="corrupt.docx")
    db_session.add(job_file)
    db_session.commit()

    # Mock failure (returncode 1)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"Conversion error")
        
        convert_file_task(job_id, "corrupt.docx", job_file.id)

    db_session.refresh(job_file)
    assert job_file.status == FileStatus.FAILED
    assert "LibreOffice conversion failed" in job_file.error_message