import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Integer, Uuid
from sqlalchemy.orm import relationship
from .database import Base

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class FileStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    
    zip_path = Column(String, nullable=True)

    files = relationship("JobFile", back_populates="job", cascade="all, delete-orphan")

class JobFile(Base):
    __tablename__ = "job_files"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Uuid(as_uuid=True), ForeignKey("jobs.id"))
    filename = Column(String, nullable=False)
    status = Column(Enum(FileStatus), default=FileStatus.PENDING)
    error_message = Column(String, nullable=True)

    job = relationship("Job", back_populates="files")