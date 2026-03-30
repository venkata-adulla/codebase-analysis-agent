from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Integer
from sqlalchemy.sql import func
from core.database import Base


class Service(Base):
    __tablename__ = "services"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    name = Column(String, nullable=False)
    language = Column(String)
    description = Column(Text)
    summary = Column(Text)
    file_path = Column(String)
    meta_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Documentation(Base):
    __tablename__ = "documentation"
    
    id = Column(String, primary_key=True)
    service_id = Column(String, ForeignKey("services.id"), nullable=False)
    content = Column(Text, nullable=False)
    api_specification = Column(JSON)
    architecture_diagram = Column(Text)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ImpactAnalysis(Base):
    __tablename__ = "impact_analyses"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    change_description = Column(Text, nullable=False)
    affected_files = Column(JSON)
    affected_services = Column(JSON)
    impacted_services = Column(JSON)  # Detailed impact data
    risk_level = Column(String)  # low, medium, high, critical
    recommendations = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HumanReview(Base):
    __tablename__ = "human_reviews"
    
    id = Column(String, primary_key=True)
    checkpoint_id = Column(String, nullable=False, unique=True)
    agent_name = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    context = Column(JSON)
    options = Column(JSON)
    response = Column(Text)
    status = Column(String, default="pending")  # pending, resolved
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
