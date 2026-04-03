from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Integer, Float
from sqlalchemy.sql import func
from core.database import Base


class TechDebtItem(Base):
    __tablename__ = "tech_debt_items"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    service_id = Column(String, ForeignKey("services.id"))
    file_path = Column(String)
    category = Column(String, nullable=False)  # code_quality, architecture, dependency, documentation, test, performance, security
    severity = Column(String, nullable=False)  # low, medium, high, critical
    priority = Column(Integer)  # 1-4 (1 = quick wins, 4 = avoid)
    title = Column(String, nullable=False)
    description = Column(Text)
    code_snippet = Column(Text)
    line_start = Column(Integer)
    line_end = Column(Integer)
    impact_score = Column(Float)  # 0-1
    effort_estimate = Column(String)  # hours, days, weeks
    meta_data = Column(JSON)
    status = Column(String, default="open")  # open, in_progress, resolved, ignored
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TechDebtReport(Base):
    __tablename__ = "tech_debt_reports"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    total_debt_score = Column(Float)  # 0-100
    debt_density = Column(Float)  # debt items per 1000 LOC
    code_quality_score = Column(Float)
    architecture_score = Column(Float)
    dependency_score = Column(Float)
    documentation_score = Column(Float)
    test_coverage_score = Column(Float)
    total_items = Column(Integer)
    items_by_category = Column(JSON)
    items_by_severity = Column(JSON)
    report_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DebtRemediationPlan(Base):
    __tablename__ = "debt_remediation_plans"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    plan_name = Column(String)
    total_estimated_effort = Column(String)
    priority_breakdown = Column(JSON)  # Items by priority
    sprint_allocation = Column(JSON)  # Suggested sprint distribution
    roi_analysis = Column(JSON)
    recommendations = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DebtMetricsHistory(Base):
    __tablename__ = "debt_metrics_history"
    
    id = Column(String, primary_key=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    total_debt_score = Column(Float)
    debt_density = Column(Float)
    total_items = Column(Integer)
    items_by_category = Column(JSON)
    remediation_velocity = Column(Float)  # Items fixed per period
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
