from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON
from sqlalchemy.sql import func
from core.database import Base


class Repository(Base):
    __tablename__ = "repositories"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String)
    local_path = Column(String)
    github_owner = Column(String)
    github_repo = Column(String)
    branch = Column(String, default="main")
    status = Column(String, default="pending")  # pending, analyzing, completed, failed
    progress = Column(Float, default=0.0)
    message = Column(Text)
    meta_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, nullable=False)
    status = Column(String, default="running")  # running, completed, failed
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    meta_data = Column(JSON)
