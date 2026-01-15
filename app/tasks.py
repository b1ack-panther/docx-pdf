import os
import subprocess
import zipfile
import uuid
from datetime import datetime, timezone
from celery import chord
from .celery_worker import celery_app
from .database import SessionLocal
from .models import Job, JobFile, JobStatus, FileStatus

# Helper to manage DB sessions inside tasks
def get_db_session():
    return SessionLocal()

# Shared storage path (must match the volume mount in docker-compose)
STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")

@celery_app.task(name="process_incoming_job")
def process_incoming_job(job_id: str, zip_path: str):
    """
    Entry point: Unzips the batch, creates DB records, and schedules the conversion chord.
    """
    db = get_db_session()
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        db.close()
        return "Job not found"

    # Setup directories
    job_dir = os.path.dirname(zip_path)
    input_dir = os.path.join(job_dir, "input")
    output_dir = os.path.join(job_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 1. Unzip the uploaded file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(input_dir)
        
        # 2. Identify valid DOCX files
        docx_files = [
            f for f in os.listdir(input_dir) 
            if f.lower().endswith(".docx") and not f.startswith("~$")
        ]

        if not docx_files:
            job.status = JobStatus.FAILED
            db.commit()
            return "No valid DOCX files found"

        # 3. Create database records for each file
        job.status = JobStatus.IN_PROGRESS
        conversion_tasks = []
        
        for filename in docx_files:
            # Create File Record
            job_file = JobFile(job_id=job.id, filename=filename, status=FileStatus.PENDING)
            db.add(job_file)
            db.commit()  # Commit to generate ID
            
            # Create Celery Task Signature
            # usage: convert_file_task(job_id, filename, file_db_id)
            task = convert_file_task.s(job_id, filename, job_file.id)
            conversion_tasks.append(task)

        # 4. Launch the Chord [cite: 30, 32]
        # This executes all conversion_tasks in parallel (or as workers allow).
        # Once ALL are finished, archive_job_task is called automatically.
        callback = archive_job_task.s(job_id)
        chord(conversion_tasks)(callback)

    except Exception as e:
        job.status = JobStatus.FAILED
        print(f"Error processing job {job_id}: {e}")
        db.commit()
    finally:
        db.close()


@celery_app.task(name="convert_file_task")
def convert_file_task(job_id: str, filename: str, db_file_id: int):
    """
    Worker Task: Converts a single DOCX to PDF using LibreOffice.
    """
    db = get_db_session()
    job_file = db.query(JobFile).filter(JobFile.id == db_file_id).first()
    
    # Paths
    if isinstance(job_id, str):
        job_id_obj = uuid.UUID(job_id)
    else:
        job_id_obj = job_id
        
    job_dir = os.path.join(STORAGE_PATH, str(job_id))
    input_path = os.path.join(job_dir, "input", filename)
    output_dir = os.path.join(job_dir, "output")
    
    try:
        # LibreOffice Headless Conversion [cite: 35, 36]
        # LibreOffice Headless Conversion [cite: 35, 36]
        # We use a unique UserInstallation per file to prevent race conditions 
        # and permission issues with the shared home directory in Docker.
        cmd = [
            "libreoffice", 
            "--headless", 
            f"-env:UserInstallation=file:///tmp/lo_{job_id}_{db_file_id}",
            "--convert-to", "pdf", 
            input_path, 
            "--outdir", output_dir
        ]
        # Prepare environment: 
        # 1. Inherit current env vars
        # 2. Force HOME to /tmp (fixes 'javaldx' and permission issues if HOME is unset/read-only)
        env = os.environ.copy()
        env['HOME'] = '/tmp'

        # Execute command with a timeout to prevent hanging workers
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            env=env,  # Pass the modified environment
            timeout=120  # 2 minutes max per file
        )
        
        if result.returncode == 0:
            job_file.status = FileStatus.COMPLETED
        else:
            job_file.status = FileStatus.FAILED
            job_file.error_message = "LibreOffice conversion failed"
            # Log stderr for debugging
            print(f"LibreOffice Error ({filename}): {result.stderr.decode()}")

    except subprocess.TimeoutExpired:
        job_file.status = FileStatus.FAILED
        job_file.error_message = "Conversion timed out"
    except Exception as e:
        job_file.status = FileStatus.FAILED
        job_file.error_message = str(e)
    
    
    # Store the status value in a variable before closing the session
    final_status = job_file.status.value if job_file.status else "UNKNOWN"
    
    db.commit()
    db.close()
    
    # Return the simple string value, NOT the ORM object or Enum attached to the session
    return final_status


@celery_app.task(name="archive_job_task")
def archive_job_task(results, job_id: str):
    """
    Callback Task: Runs only when all file conversions are done.
    Zips the results and updates job status.
    """
    db = get_db_session()
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    
    job_dir = os.path.join(STORAGE_PATH, job_id)
    output_dir = os.path.join(job_dir, "output")
    zip_filename = "result.zip"
    zip_path_abs = os.path.join(job_dir, zip_filename)

    try:
        # Check if we have any files to zip
        files_to_zip = False
        with zipfile.ZipFile(zip_path_abs, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists(output_dir):
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.endswith(".pdf"):
                            files_to_zip = True
                            # Add to zip with just the filename (no full path)
                            zipf.write(os.path.join(root, file), arcname=file)

        # Update Job Status [cite: 39]
        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        
        if files_to_zip:
            job.zip_path = f"{job_id}/{zip_filename}"
        else:
            # Handle edge case where all conversions failed
            job.zip_path = None 
            if not any(r == FileStatus.COMPLETED for r in results):
                 job.status = JobStatus.FAILED

        # Optional: Cleanup input files to save space
        # shutil.rmtree(os.path.join(job_dir, "input"))

    except Exception as e:
        job.status = JobStatus.FAILED
        print(f"Archiving error for job {job_id}: {e}")
    
    db.commit()
    db.close()
    return "Job Finished"