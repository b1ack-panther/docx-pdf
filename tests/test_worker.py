import os
import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.tasks import process_incoming_job, convert_file_task, archive_job_task
from app.models import Job, JobFile, JobStatus, FileStatus

@pytest.fixture
def dummy_zip(tmp_path):
    zip_path = tmp_path / "upload.zip"
    import zipfile
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("doc1.docx", "content")
        zf.writestr("ignore_me.txt", "content") # Should be ignored
    return str(zip_path)

def test_process_incoming_job_unzipping(db_session, dummy_zip):
    job_id = str(uuid.uuid4())
    job = Job(id=uuid.UUID(job_id), status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    with patch("app.tasks.chord") as mock_chord:
        process_incoming_job(job_id, dummy_zip)

    db_session.refresh(job)
    
    assert job.status == JobStatus.IN_PROGRESS
    assert len(job.files) == 2 
    
    docx_file = next(f for f in job.files if f.filename == "doc1.docx")
    txt_file = next(f for f in job.files if f.filename == "ignore_me.txt")
    
    assert docx_file.status == FileStatus.PENDING
    assert txt_file.status == FileStatus.FAILED
    assert txt_file.error_message == "Invalid file format or corrupted DOCX."
    assert mock_chord.called 


def test_convert_file_task_success(db_session, tmp_path):
    job_id = str(uuid.uuid4())
    job_file = JobFile(job_id=uuid.UUID(job_id), filename="test.docx", status=FileStatus.PENDING)
    db_session.add(job_file)
    db_session.commit()
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        convert_file_task(job_id, "test.docx", job_file.id)

    db_session.refresh(job_file)
    assert job_file.status == FileStatus.COMPLETED
    
    args, _ = mock_run.call_args
    assert "libreoffice" in args[0]
    assert "--convert-to" in args[0]

def test_convert_file_task_failure(db_session):
    job_id = str(uuid.uuid4())
    job_file = JobFile(job_id=uuid.UUID(job_id), filename="corrupt.docx")
    db_session.add(job_file)
    db_session.commit()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"Conversion error")
        
        convert_file_task(job_id, "corrupt.docx", job_file.id)

    db_session.refresh(job_file)
    assert job_file.status == FileStatus.FAILED
    assert "Invalid file format or corrupted DOCX." in job_file.error_message

def test_process_job_all_invalid_files(db_session, tmp_path):
    zip_path = tmp_path / "invalid.zip"
    import zipfile
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("test.txt", "content")
        zf.writestr("image.png", "content")
    
    job_id = str(uuid.uuid4())
    job = Job(id=uuid.UUID(job_id), status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    process_incoming_job(job_id, str(zip_path))

    db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.finished_at is not None
    assert len(job.files) == 2
    for f in job.files:
        assert f.status == FileStatus.FAILED
        assert f.error_message == "Invalid file format or corrupted DOCX."

def test_process_job_large_batch(db_session, tmp_path):
    # Create a zip with 1000 files
    zip_path = tmp_path / "large_batch.zip"
    import zipfile
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for i in range(1000):
            zf.writestr(f"file_{i}.docx", "content")
    
    job_id = str(uuid.uuid4())
    job = Job(id=uuid.UUID(job_id), status=JobStatus.PENDING)
    db_session.add(job)
    db_session.commit()

    with patch("app.tasks.chord") as mock_chord:
        process_incoming_job(job_id, str(zip_path))

    db_session.refresh(job)
    assert job.status == JobStatus.IN_PROGRESS
    assert len(job.files) == 1000
    
    # Verify all files are in the DB with status PENDING
    pending_files = [f for f in job.files if f.status == FileStatus.PENDING]
    assert len(pending_files) == 1000
    
    # Verify chord was called with 1000 tasks
    assert mock_chord.called
    conversion_tasks = mock_chord.call_args[0][0]
    assert len(list(conversion_tasks)) == 1000
