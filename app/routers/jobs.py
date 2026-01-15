import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Job, JobStatus
from .. import tasks 

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")

@router.post("", status_code=202)
def submit_job(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed.")

    job_id = uuid.uuid4()
    job_dir = os.path.join(STORAGE_PATH, str(job_id))
    input_dir = os.path.join(job_dir, "input")
    os.makedirs(input_dir, exist_ok=True)

    zip_location = os.path.join(job_dir, "upload.zip")
    with open(zip_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_job = Job(id=job_id, status=JobStatus.PENDING)
    db.add(new_job)
    db.commit()

    tasks.process_incoming_job.delay(str(job_id), zip_location)

    return {"job_id": str(job_id), "status": "PENDING"}



@router.get("/{job_id}")
def get_job_status(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": str(job.id),
        "status": job.status,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "files": [
            {"filename": f.filename, "status": f.status, "error_message": f.error_message} 
            for f in job.files
        ]
    }

    if job.status == JobStatus.COMPLETED:
        response["download_url"] = str(request.url_for("download_job_result", job_id=job_id))

    return response



@router.get("/{job_id}/download")
def download_job_result(job_id: uuid.UUID, db: Session = Depends(get_db)):
    print("Downloading job result for job_id:", job_id)
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not ready or failed")
    
    full_path = os.path.join(STORAGE_PATH, job.zip_path)
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=500, detail="File missing from storage")

    return FileResponse(
        path=full_path, 
        filename=f"converted_{job_id}.zip",
        media_type="application/zip"
    )