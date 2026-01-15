import os
import subprocess
import zipfile
import uuid
from datetime import datetime, timezone
from celery import chord
from .celery_worker import celery_app
from .database import SessionLocal
from .models import Job, JobFile, JobStatus, FileStatus

def get_db_session():
    return SessionLocal()

STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")

@celery_app.task(name="process_incoming_job")
def process_incoming_job(job_id: str, zip_path: str):
    db = get_db_session()
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        db.close()
        return "Job not found"

    job_dir = os.path.dirname(zip_path)
    input_dir = os.path.join(job_dir, "input")
    output_dir = os.path.join(job_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(input_dir)
        
        all_files = [
            f for f in os.listdir(input_dir) 
            if os.path.isfile(os.path.join(input_dir, f))
        ]

        conversion_tasks = []
        for filename in all_files:
            if filename.lower().endswith(".docx") and not filename.startswith("~$"):
                job_file = JobFile(job_id=job.id, filename=filename, status=FileStatus.PENDING)
                db.add(job_file)
            else:
                job_file = JobFile(
                    job_id=job.id, 
                    filename=filename, 
                    status=FileStatus.FAILED, 
                    error_message="Invalid file format or corrupted DOCX."
                )
                db.add(job_file)

        # Batch commit all JobFile entries
        db.commit()

        # Create tasks after committing so job_file.id is available
        for job_file in job.files:
            if job_file.status == FileStatus.PENDING:
                task = convert_file_task.s(str(job.id), job_file.filename, job_file.id)
                conversion_tasks.append(task)


        if not conversion_tasks:
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return "No valid DOCX files found"

        job.status = JobStatus.IN_PROGRESS

        db.commit()
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
    db = get_db_session()
    job_file = db.query(JobFile).filter(JobFile.id == db_file_id).first()
    
    if isinstance(job_id, str):
        job_id_obj = uuid.UUID(job_id)
    else:
        job_id_obj = job_id
        
    job_dir = os.path.join(STORAGE_PATH, str(job_id))
    input_path = os.path.join(job_dir, "input", filename)
    output_dir = os.path.join(job_dir, "output")
    
    try:
        cmd = [
            "libreoffice", 
            "--headless", 
            f"-env:UserInstallation=file:///tmp/lo_{job_id}_{db_file_id}",
            "--convert-to", "pdf", 
            input_path, 
            "--outdir", output_dir
        ]
        env = os.environ.copy()
        env['HOME'] = '/tmp'

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
            job_file.error_message = "Invalid file format or corrupted DOCX."
            print(f"LibreOffice Error ({filename}): {result.stderr.decode()}")

    except subprocess.TimeoutExpired:
        job_file.status = FileStatus.FAILED
        job_file.error_message = "Conversion timed out"
    except Exception as e:
        job_file.status = FileStatus.FAILED
        job_file.error_message = str(e)
    
    
    final_status = job_file.status.value if job_file.status else "UNKNOWN"
    
    db.commit()
    db.close()
    
    return final_status


@celery_app.task(name="archive_job_task")
def archive_job_task(results, job_id: str):
    db = get_db_session()
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    
    job_dir = os.path.join(STORAGE_PATH, str(job_id))
    output_dir = os.path.join(job_dir, "output")
    zip_filename = "result.zip"
    zip_path_abs = os.path.join(job_dir, zip_filename)

    try:
        files_to_zip = False
        with zipfile.ZipFile(zip_path_abs, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists(output_dir):
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.endswith(".pdf"):
                            files_to_zip = True
                            # Add to zip with just the filename (no full path)
                            zipf.write(os.path.join(root, file), arcname=file)

        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        
        if files_to_zip:
            job.zip_path = f"{job_id}/{zip_filename}"
        else:
            job.zip_path = None
            if not any(r == FileStatus.COMPLETED for r in results):
                 job.status = JobStatus.FAILED


    except Exception as e:
        job.status = JobStatus.FAILED
        print(f"Archiving error for job {job_id}: {e}")
    
    db.commit()
    db.close()
    return "Job Finished"