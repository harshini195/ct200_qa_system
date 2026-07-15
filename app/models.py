from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    versions = relationship("DocumentVersion", back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    ingested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    raw_file_hash = Column(String, nullable=False)
    parser_warnings = Column(Text, nullable=True)  # JSON-encoded list[str]

    document = relationship("Document", back_populates="versions")
    revisions = relationship("NodeRevision", back_populates="version")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
    )


class Node(Base):
    """Stable logical identity of a section, persists across versions."""
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    first_version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)

    revisions = relationship("NodeRevision", back_populates="node")


class NodeRevision(Base):
    """One row per (logical node, version) it appears in."""
    __tablename__ = "node_revisions"
    id = Column(Integer, primary_key=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)

    heading_text = Column(String, nullable=False)
    heading_number = Column(String, nullable=True)
    level = Column(Integer, nullable=False)
    order_in_document = Column(Integer, nullable=False)
    parent_revision_id = Column(Integer, ForeignKey("node_revisions.id"), nullable=True)
    body_text = Column(Text, nullable=False, default="")
    content_hash = Column(String, nullable=False)

    node = relationship("Node", back_populates="revisions")
    version = relationship("DocumentVersion", back_populates="revisions")


class Selection(Base):
    __tablename__ = "selections"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("SelectionNode", back_populates="selection")


class SelectionNode(Base):
    """Version-pinned reference: a selection points at an exact
    (node, version, node_revision) triple so it always resolves to the
    exact text it was created against, even after re-ingestion."""
    __tablename__ = "selection_nodes"
    id = Column(Integer, primary_key=True)
    selection_id = Column(Integer, ForeignKey("selections.id"), nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("document_versions.id"), nullable=False)
    node_revision_id = Column(Integer, ForeignKey("node_revisions.id"), nullable=False)

    selection = relationship("Selection", back_populates="items")
