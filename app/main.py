from fastapi import FastAPI
from .database import engine, Base
from .routers import jobs

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Bulk Docx to PDF Converter",
    description="Asynchronous microservice for batch document conversion.",
    version="1.0.0"
)

app.include_router(jobs.router)

@app.get("/")
def root():
    return {"message": "Service is running. Visit /docs for API documentation."}