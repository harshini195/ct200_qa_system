from pydantic import BaseModel
from typing import Optional


class NodeOut(BaseModel):
    id: int
    node_id: int
    heading_text: str
    heading_number: Optional[str]
    level: int
    order_in_document: int
    content_hash: str
    body_text: Optional[str] = None
    children: Optional[list["NodeOut"]] = None

    class Config:
        from_attributes = True


class IngestRequest(BaseModel):
    document_name: str
    file_path: Optional[str] = None
    raw_text: Optional[str] = None


class CreateSelectionRequest(BaseModel):
    name: str
    node_ids: list[int]
    version: Optional[int] = None


class DiffResult(BaseModel):
    node_id: int
    from_version: int
    to_version: int
    changed: bool
    diff: Optional[str] = None
