# backend/app/models/rule.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Rule(Base):
    __tablename__ = "rules"
    
    # Add composite index for fast conflict detection
    __table_args__ = (
        Index('ix_rules_group_priority', 'group', 'priority'),
        Index('ix_rules_enabled_group', 'enabled', 'group'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text)
    group = Column(String, index=True)
    priority = Column(Integer, default=0, index=True)
    enabled = Column(Boolean, default=True, index=True)
    condition_dsl = Column(JSON, nullable=False)
    action = Column(Text, nullable=False)
    rule_metadata = Column(JSON)  # Changed from 'metadata' to 'rule_metadata'
    current_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    versions = relationship("RuleVersion", back_populates="rule", cascade="all, delete-orphan")
    creator = relationship("User", back_populates="rules")

class RuleVersion(Base):
    __tablename__ = "rule_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    version = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    group = Column(String)
    priority = Column(Integer)
    enabled = Column(Boolean)
    condition_dsl = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    rule_metadata = Column(Text)  # Changed from 'metadata' to 'rule_metadata'
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    rule = relationship("Rule", back_populates="versions")
    creator = relationship("User")