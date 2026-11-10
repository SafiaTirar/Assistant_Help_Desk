import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models.document import Document, DocumentVersion
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentVersionResponse
from app.services.document_management_service import (
    DocumentValidationError,
    next_version,
    process_initial_document,
    process_new_version,
    process_reindex_document,
    validate_and_store_upload,
)
from app.services.ingestion_service import (
    delete_document_vectors,
    update_document_active,
)

router = APIRouter(tags=["admin-documents"])
logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv(
    "DOCUMENT_UPLOAD_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploaded_documents"),
)
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def _to_response(doc: Document) -> DocumentResponse:
    date_str = doc.created_at.strftime("%Y-%m-%d")
    return DocumentResponse(
        id=str(doc.id),
        title=doc.title,
        file_name=doc.file_name,
        format=doc.format,
        version=doc.version,
        versions=doc.versions,
        date=date_str,
        pages=str(doc.page_count) if doc.page_count else "—",
        added_at=date_str,
        status=doc.status,
        active=doc.active,
        progress=doc.progress,
        error_message=doc.error_message,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
    )


def _version_response(version: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        id=str(version.id),
        document_id=str(version.document_id),
        version=version.version,
        file_name=version.file_name,
        format=version.format,
        mime_type=version.mime_type,
        file_size=version.file_size,
        pages=version.page_count,
        chunks=version.chunk_count,
        status=version.status,
        error_message=version.error_message,
        is_current=version.is_current,
        created_at=version.created_at,
    )


def _get_document_or_404(db: Session, document_id: str) -> Document:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identifiant de document invalide.")
    doc = db.get(Document, doc_uuid)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    return doc


@router.get("/admin/documents", response_model=list[DocumentResponse], response_model_by_alias=True)
def list_documents(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    docs = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return [_to_response(d) for d in docs]


@router.post(
    "/admin/documents",
    response_model=DocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    safe_name = Path(file.filename or "document").name
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté (PDF ou DOCX uniquement).")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    document_id = uuid.uuid4()
    stored_path = os.path.join(UPLOAD_DIR, f"{document_id}{ext}")

    try:
        file_size, mime_type = validate_and_store_upload(
            file.file,
            stored_path,
            ext,
            file.content_type,
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    doc = Document(
        id=document_id,
        title=os.path.splitext(safe_name)[0],
        file_name=safe_name,
        file_path=stored_path,
        format=ext.lstrip(".").upper(),
        status="Traitement en cours",
        active=True,
        progress=10,
        mime_type=mime_type,
        file_size=file_size,
        version="1.0",
        versions=["1.0"],
        uploaded_by=str(admin.id),
    )
    db.add(doc)
    version = DocumentVersion(
        document_id=document_id,
        version="1.0",
        file_name=safe_name,
        file_path=stored_path,
        format=ext.lstrip(".").upper(),
        mime_type=mime_type,
        file_size=file_size,
        status="Traitement en cours",
        is_current=True,
        uploaded_by=str(admin.id),
    )
    db.add(version)
    db.commit()
    db.refresh(doc)
    db.refresh(version)
    background_tasks.add_task(process_initial_document, str(doc.id), str(version.id))
    return _to_response(doc)


@router.patch("/admin/documents/{document_id}/toggle", response_model=DocumentResponse, response_model_by_alias=True)
def toggle_document(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status == "Archivé":
        raise HTTPException(
            status_code=409,
            detail="Un document archivé doit être restauré avant d'être réactivé.",
        )
    if doc.status == "Traitement en cours":
        raise HTTPException(status_code=409, detail="Une indexation est déjà en cours.")
    new_active = not doc.active
    try:
        update_document_active(str(doc.id), new_active)
    except Exception as exc:
        logger.exception(
            "Échec de la synchronisation Qdrant pour le document %s après activation/désactivation.",
            doc.id,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Le document a été mis à jour dans PostgreSQL, mais la synchronisation "
                "avec Qdrant a échoué."
            ),
        ) from exc
    doc.active = new_active
    doc.status = "Prêt" if new_active else "Désactivé"
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return _to_response(doc)


@router.post(
    "/admin/documents/{document_id}/reindex",
    response_model=DocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status in {"Archivé", "Traitement en cours"}:
        raise HTTPException(status_code=409, detail="Ce document ne peut pas être réindexé dans son état actuel.")
    doc.status = "Traitement en cours"
    doc.progress = 10
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(process_reindex_document, str(doc.id))
    return _to_response(doc)


@router.post("/admin/documents/{document_id}/archive", response_model=DocumentResponse, response_model_by_alias=True)
def archive_document(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status == "Traitement en cours":
        raise HTTPException(status_code=409, detail="Une indexation est en cours.")
    try:
        update_document_active(str(doc.id), False)
    except Exception as exc:
        logger.exception(
            "Échec de la synchronisation Qdrant pour le document %s après archivage.",
            doc.id,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Le document a été archivé dans PostgreSQL, mais la synchronisation "
                "avec Qdrant a échoué."
            ),
        ) from exc
    doc.status = "Archivé"
    doc.active = False
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return _to_response(doc)


@router.post("/admin/documents/{document_id}/restore", response_model=DocumentResponse, response_model_by_alias=True)
def restore_document(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status != "Archivé":
        raise HTTPException(status_code=409, detail="Seul un document archivé peut être restauré.")
    try:
        count = update_document_active(str(doc.id), True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="La restauration de l'index Qdrant a échoué.") from exc
    if count == 0:
        raise HTTPException(status_code=409, detail="Aucun index à restaurer : réindexez le document.")
    doc.active = True
    doc.status = "Prêt"
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    return _to_response(doc)


def _document_file_response(doc: Document, disposition: str) -> FileResponse:
    if not os.path.isfile(doc.file_path):
        raise HTTPException(status_code=404, detail="Le fichier physique du document est introuvable.")
    return FileResponse(
        doc.file_path,
        media_type=doc.mime_type or {
            "PDF": "application/pdf",
            "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(doc.format, "application/octet-stream"),
        filename=doc.file_name,
        content_disposition_type=disposition,
    )


@router.get("/admin/documents/{document_id}/download")
def download_document(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    return _document_file_response(_get_document_or_404(db, document_id), "attachment")


@router.get("/admin/documents/{document_id}/view")
def view_document(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    return _document_file_response(_get_document_or_404(db, document_id), "inline")


@router.get(
    "/admin/documents/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    response_model_by_alias=True,
)
def list_document_versions(
    document_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[DocumentVersionResponse]:
    doc = _get_document_or_404(db, document_id)
    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.created_at.desc())
    ).all()
    return [_version_response(version) for version in versions]


@router.post(
    "/admin/documents/{document_id}/versions",
    response_model=DocumentVersionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document_version(
    document_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentVersionResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status in {"Archivé", "Traitement en cours"}:
        raise HTTPException(status_code=409, detail="Ce document ne peut pas recevoir une version maintenant.")
    safe_name = Path(file.filename or "document").name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté (PDF ou DOCX uniquement).")
    latest_version = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.created_at.desc())
    ).first()
    version_number = next_version(latest_version.version if latest_version else doc.version)
    stored_path = os.path.join(UPLOAD_DIR, f"{doc.id}_v{version_number}{extension}")
    try:
        file_size, mime_type = validate_and_store_upload(
            file.file, stored_path, extension, file.content_type
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = DocumentVersion(
        document_id=doc.id,
        version=version_number,
        file_name=safe_name,
        file_path=stored_path,
        format=extension.lstrip(".").upper(),
        mime_type=mime_type,
        file_size=file_size,
        status="Traitement en cours",
        is_current=False,
        uploaded_by=str(admin.id),
    )
    db.add(version)
    doc.status = "Traitement en cours"
    doc.progress = 10
    doc.error_message = None
    db.commit()
    db.refresh(version)
    background_tasks.add_task(process_new_version, str(doc.id), str(version.id), True)
    return _version_response(version)


@router.post(
    "/admin/documents/{document_id}/versions/{version_id}/restore",
    response_model=DocumentVersionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def restore_document_version(
    document_id: str,
    version_id: str,
    background_tasks: BackgroundTasks,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentVersionResponse:
    doc = _get_document_or_404(db, document_id)
    if doc.status in {"Archivé", "Traitement en cours"}:
        raise HTTPException(status_code=409, detail="Ce document ne peut pas changer de version maintenant.")
    try:
        version_uuid = uuid.UUID(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Identifiant de version invalide.") from exc
    version = db.get(DocumentVersion, version_uuid)
    if version is None or version.document_id != doc.id:
        raise HTTPException(status_code=404, detail="Version introuvable.")
    if version.is_current:
        raise HTTPException(status_code=409, detail="Cette version est déjà active.")
    if version.status == "Erreur" or not os.path.isfile(version.file_path):
        raise HTTPException(status_code=409, detail="Cette version ne peut pas être restaurée.")
    version.status = "Traitement en cours"
    version.error_message = None
    doc.status = "Traitement en cours"
    doc.progress = 10
    doc.error_message = None
    db.commit()
    db.refresh(version)
    background_tasks.add_task(process_new_version, str(doc.id), str(version.id), False)
    return _version_response(version)


@router.delete("/admin/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    confirm: bool = Query(False),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    doc = _get_document_or_404(db, document_id)
    if doc.status != "Archivé":
        raise HTTPException(status_code=409, detail="Archivez le document avant sa suppression définitive.")
    if not confirm:
        raise HTTPException(status_code=400, detail="La confirmation explicite est obligatoire.")
    versions = db.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    ).all()
    try:
        delete_document_vectors(str(doc.id))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Suppression Qdrant impossible ; aucune donnée n'a été supprimée.") from exc
    paths = {doc.file_path, *(version.file_path for version in versions)}
    for version in versions:
        db.delete(version)
    db.delete(doc)
    db.commit()
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Le fichier %s n'a pas pu être supprimé du stockage.", path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
