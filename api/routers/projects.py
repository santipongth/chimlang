"""Project and Evidence Library API (P9-M2)."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Literal
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from api.auth import get_principal, require
from api.models import ApiError
from core.config import get_settings
from core.project_store import EvidenceStore, ProjectStore
from governance.pii import PIIRedactionError
from governance.rbac import Permission, Principal

router = APIRouter(prefix="/projects", tags=["projects", "evidence"])
MAX_UPLOAD_BYTES = 2_000_000


class ProjectCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    brief: str = Field(default="", max_length=20_000)


class ProjectUpdateBody(BaseModel):
    stage: (
        Literal[
            "brief",
            "evidence",
            "population",
            "assumptions",
            "run",
            "compare",
            "decision",
            "resolution",
        ]
        | None
    ) = None
    brief: str | None = Field(default=None, max_length=20_000)
    population: dict[str, Any] | None = None
    assumptions: list[dict[str, Any] | str] | None = None
    decision: str | None = Field(default=None, max_length=20_000)
    resolution: str | None = Field(default=None, max_length=20_000)


class ProjectSummary(BaseModel):
    project_id: str
    created_at: str
    updated_at: str
    name: str
    stage: str
    brief: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class ProjectResponse(BaseModel):
    project_id: str
    created_at: str
    updated_at: str
    name: str
    stage: str
    stage_index: int
    brief: str
    population: dict[str, Any]
    assumptions: list[Any]
    decision: str
    resolution: str
    created_by: str
    evidence_count: int
    runs: list[dict[str, Any]]
    evidence_sets: list[dict[str, Any]]
    workflow: list[dict[str, str]]


class EvidenceTextBody(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000_000)
    kind: Literal["text", "txt", "csv"] = "text"
    item_id: str = ""


class EvidenceUrlBody(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=2_000)
    kind: Literal["url", "rss"] = "url"
    item_id: str = ""


class EvidencePreviewBody(BaseModel):
    text: str = Field(max_length=2_000_000)


class EvidencePreviewResponse(BaseModel):
    safe_to_store: bool
    pii_counts: dict[str, int]
    policy: str


class EvidenceVersionResponse(BaseModel):
    version_id: str
    item_id: str
    project_id: str
    label: str
    kind: str
    source_url: str
    version_no: int
    created_at: str
    content_hash: str
    byte_size: int
    media_type: str
    status: str
    source_health: str
    duplicate_of: str
    pii_redactions: dict[str, int]
    metadata: dict[str, Any]


class EvidenceListResponse(BaseModel):
    evidence: list[EvidenceVersionResponse]


class EvidenceFreezeBody(BaseModel):
    name: str = Field(default="Frozen evidence", max_length=200)
    version_ids: list[str] = Field(default_factory=list, max_length=100)


class EvidenceSetResponse(BaseModel):
    set_id: str
    project_id: str
    created_at: str
    schema_version: int
    name: str
    content_hash: str
    manifest: dict[str, Any]
    created_by: str
    hash_valid: bool
    versions: list[EvidenceVersionResponse]


def _projects() -> ProjectStore:
    return ProjectStore(get_settings().postgres_url)


def _evidence() -> EvidenceStore:
    return EvidenceStore(get_settings().postgres_url)


def _raise_store_error(exc: Exception) -> None:
    status = 404 if str(exc).startswith("ไม่พบ") else 422
    raise HTTPException(status_code=status, detail=str(exc)) from exc


def _extract_upload(filename: str, media_type: str, payload: bytes) -> tuple[str, str]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix in {"txt", "csv"}:
        try:
            return payload.decode("utf-8-sig"), suffix
        except UnicodeDecodeError as exc:
            raise ValueError("TXT/CSV ต้องเข้ารหัส UTF-8") from exc
    if suffix == "pdf":
        try:
            reader = PdfReader(BytesIO(payload))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages[:500]), "pdf"
        except (PdfReadError, ValueError) as exc:
            raise ValueError("PDF ไม่ถูกต้องหรือเข้ารหัส") from exc
    if suffix == "docx":
        try:
            with ZipFile(BytesIO(payload)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > MAX_UPLOAD_BYTES * 5:
                    raise ValueError("DOCX ขยายแล้วเกิน 10 MB")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError("DOCX ไม่ถูกต้อง") from exc
        text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
        return text, "docx"
    raise ValueError("รองรับเฉพาะ PDF, DOCX, TXT และ CSV")


@router.get("", response_model=ProjectListResponse)
def list_projects(
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
) -> dict:
    return {"projects": _projects().list(limit=limit)}


@router.post(
    "",
    status_code=201,
    response_model=ProjectResponse,
    responses={422: {"model": ApiError}},
)
def create_project(body: ProjectCreateBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    return _projects().create(name=body.name, brief=body.brief, actor=principal.user_id)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ApiError}},
)
def get_project(project_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        return _projects().get(project_id)
    except ValueError as exc:
        _raise_store_error(exc)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def update_project(
    project_id: str,
    body: ProjectUpdateBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        return _projects().update(
            project_id,
            actor=principal.user_id,
            **body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        _raise_store_error(exc)


@router.post(
    "/{project_id}/evidence/preview",
    response_model=EvidencePreviewResponse,
    responses={422: {"model": ApiError}},
)
def preview_evidence(
    project_id: str,
    body: EvidencePreviewBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        _projects().get(project_id)
        return _evidence().preview(body.text)
    except (ValueError, RuntimeError) as exc:
        _raise_store_error(exc)


@router.get(
    "/{project_id}/evidence",
    response_model=EvidenceListResponse,
    responses={404: {"model": ApiError}},
)
def list_evidence(project_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        _projects().get(project_id)
        return {"evidence": _evidence().list_project(project_id)}
    except ValueError as exc:
        _raise_store_error(exc)


@router.post(
    "/{project_id}/evidence/text",
    status_code=201,
    response_model=EvidenceVersionResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def add_text_evidence(
    project_id: str,
    body: EvidenceTextBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        return _evidence().add_content(
            project_id,
            label=body.label,
            kind=body.kind,
            content=body.text,
            actor=principal.user_id,
            item_id=body.item_id,
            media_type="text/csv" if body.kind == "csv" else "text/plain",
        )
    except (ValueError, RuntimeError, PIIRedactionError) as exc:
        _raise_store_error(exc)


@router.post(
    "/{project_id}/evidence/url",
    status_code=201,
    response_model=EvidenceVersionResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def add_url_evidence(
    project_id: str,
    body: EvidenceUrlBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        return _evidence().add_url(
            project_id,
            label=body.label,
            kind=body.kind,
            url=body.url,
            actor=principal.user_id,
            item_id=body.item_id,
        )
    except (ValueError, RuntimeError, PIIRedactionError) as exc:
        _raise_store_error(exc)


@router.post(
    "/{project_id}/evidence/upload",
    status_code=201,
    response_model=EvidenceVersionResponse,
    responses={404: {"model": ApiError}, 413: {"model": ApiError}, 422: {"model": ApiError}},
)
async def upload_evidence(
    project_id: str,
    file: UploadFile = File(...),
    label: str = Form(""),
    item_id: str = Form(""),
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ไฟล์เกิน 2 MB")
    try:
        text, kind = _extract_upload(file.filename or "evidence", file.content_type or "", payload)
        return _evidence().add_content(
            project_id,
            label=label.strip() or (file.filename or "evidence"),
            kind=kind,
            content=text,
            actor=principal.user_id,
            item_id=item_id,
            media_type=file.content_type or "application/octet-stream",
            metadata={"filename": file.filename or "", "parser": f"{kind}-v1"},
        )
    except (ValueError, RuntimeError, PIIRedactionError) as exc:
        _raise_store_error(exc)


@router.post(
    "/{project_id}/evidence-sets",
    status_code=201,
    response_model=EvidenceSetResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def freeze_evidence(
    project_id: str,
    body: EvidenceFreezeBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        return _evidence().freeze(
            project_id,
            name=body.name,
            actor=principal.user_id,
            version_ids=body.version_ids,
        )
    except ValueError as exc:
        _raise_store_error(exc)


@router.get(
    "/{project_id}/evidence-sets/{set_id}",
    response_model=EvidenceSetResponse,
    responses={404: {"model": ApiError}},
)
def get_evidence_set(
    project_id: str,
    set_id: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        frozen = _evidence().get_set(set_id)
        if frozen["project_id"] != project_id:
            raise ValueError(f"ไม่พบ evidence set {set_id} ใน project นี้")
        return frozen
    except ValueError as exc:
        _raise_store_error(exc)
