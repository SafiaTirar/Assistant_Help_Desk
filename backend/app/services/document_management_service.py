import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.db.database import SessionLocal
from app.models.document import Document, DocumentVersion
from app.services.ingestion_service import (
    delete_document_vectors,
    get_document_page_count,
    index_document,
    replace_document_index,
)


MAX_DOCUMENT_SIZE = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "20")) * 1024 * 1024
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_CONTENT_TYPES = {
    ".pdf": {PDF_MIME, "application/octet-stream"},
    ".docx": {
        DOCX_MIME,
        "application/zip",
        "application/octet-stream",
    },
}
PDF_DANGEROUS_PATTERN = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFile)\b",
    re.IGNORECASE,
)
DOCX_DANGEROUS_PARTS = (
    "vbaproject.bin",
    "word/embeddings/",
    "word/activex/",
)


class DocumentValidationError(ValueError):
    pass


def validate_and_store_upload(file, destination: str, extension: str, content_type: str | None) -> tuple[int, str]:
    extension = extension.lower()
    if extension not in ALLOWED_CONTENT_TYPES:
        raise DocumentValidationError("Format non supporté (PDF ou DOCX uniquement).")
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES[extension]:
        raise DocumentValidationError(
            f"Le type MIME {content_type!r} ne correspond pas à l'extension {extension}."
        )

    target = Path(destination)
    temporary = target.with_suffix(target.suffix + ".uploading")
    size = 0
    try:
        with temporary.open("wb") as output:
            while chunk := file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOCUMENT_SIZE:
                    raise DocumentValidationError(
                        f"Le fichier dépasse la limite de {MAX_DOCUMENT_SIZE // 1024 // 1024} Mo."
                    )
                output.write(chunk)
        if size == 0:
            raise DocumentValidationError("Le fichier envoyé est vide.")
        detected_mime = _validate_file_content(temporary, extension)
        os.replace(temporary, target)
        return size, detected_mime
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _validate_file_content(path: Path, extension: str) -> str:
    if extension == ".pdf":
        content = path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise DocumentValidationError("Le contenu ne correspond pas à un fichier PDF valide.")
        if PDF_DANGEROUS_PATTERN.search(content):
            raise DocumentValidationError(
                "Le PDF contient une action active ou une pièce jointe interdite."
            )
        return PDF_MIME

    try:
        with ZipFile(path) as archive:
            names = [name.lower() for name in archive.namelist()]
            if "[content_types].xml" not in names or "word/document.xml" not in names:
                raise DocumentValidationError("Le contenu ne correspond pas à un document DOCX valide.")
            if any(
                name.startswith("/") or ".." in Path(name).parts
                for name in names
            ):
                raise DocumentValidationError("Le DOCX contient un chemin interne dangereux.")
            if any(marker in name for marker in DOCX_DANGEROUS_PARTS for name in names):
                raise DocumentValidationError(
                    "Le DOCX contient une macro, un objet embarqué ou un contrôle actif interdit."
                )
            expanded_size = sum(item.file_size for item in archive.infolist())
            if expanded_size > MAX_DOCUMENT_SIZE * 10:
                raise DocumentValidationError("Le DOCX compressé dépasse la limite de sécurité.")
    except BadZipFile as exc:
        raise DocumentValidationError("Le contenu ne correspond pas à un document DOCX valide.") from exc
    return DOCX_MIME


def next_version(current: str) -> str:
    match = re.match(r"^(\d+)(?:\.(\d+))?$", current)
    return f"{int(match.group(1)) + 1}.0" if match else "2.0"


def _set_progress(document_id: str, progress: int, status: str = "Traitement en cours") -> None:
    with SessionLocal() as db:
        document = db.get(Document, uuid.UUID(document_id))
        if document:
            document.progress = progress
            document.status = status
            db.commit()


def process_initial_document(document_id: str, version_id: str) -> None:
    try:
        _set_progress(document_id, 20)
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            version = db.get(DocumentVersion, uuid.UUID(version_id))
            if document is None or version is None:
                return
            file_path = document.file_path
            file_name = document.file_name
            title = document.title
            active = document.active

        generation = str(uuid.uuid4())
        chunks = index_document(
            file_path,
            document_id,
            active,
            file_name=file_name,
            document_title=title,
            generation=generation,
            document_version_id=version_id,
        )
        _set_progress(document_id, 85)
        pages = get_document_page_count(file_path)
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            version = db.get(DocumentVersion, uuid.UUID(version_id))
            if document and version:
                document.chunk_count = chunks
                document.page_count = pages
                document.current_generation = generation
                document.progress = 100
                document.status = "Prêt"
                document.error_message = None
                document.indexed_at = datetime.now(timezone.utc)
                version.chunk_count = chunks
                version.page_count = pages
                version.status = "Prêt"
                version.error_message = None
                db.commit()
    except Exception as exc:
        try:
            delete_document_vectors(document_id)
        except Exception:
            pass
        _record_failure(document_id, version_id, f"Indexation impossible : {exc}", initial=True)


def process_reindex_document(document_id: str) -> None:
    try:
        _set_progress(document_id, 20)
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            if document is None:
                return
            current_version = db.query(DocumentVersion).filter(
                DocumentVersion.document_id == document.id,
                DocumentVersion.is_current.is_(True),
            ).one_or_none()
            values = (
                document.file_path,
                document.active,
                document.file_name,
                document.title,
                str(current_version.id) if current_version else None,
            )
        chunks, generation = replace_document_index(
            values[0],
            document_id,
            values[1],
            file_name=values[2],
            document_title=values[3],
            document_version_id=values[4],
        )
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            if document:
                document.chunk_count = chunks
                document.page_count = get_document_page_count(document.file_path)
                document.current_generation = generation
                document.progress = 100
                document.status = "Prêt"
                document.error_message = None
                document.indexed_at = datetime.now(timezone.utc)
                current_version = db.query(DocumentVersion).filter(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.is_current.is_(True),
                ).one_or_none()
                if current_version:
                    current_version.chunk_count = chunks
                    current_version.page_count = document.page_count
                    current_version.status = "Prêt"
                    current_version.error_message = None
                db.commit()
    except Exception as exc:
        _record_failure(
            document_id,
            None,
            f"Réindexation impossible, l'index précédent a été conservé : {exc}",
            initial=False,
        )


def process_new_version(
    document_id: str,
    version_id: str,
    mark_version_error: bool = True,
) -> None:
    try:
        _set_progress(document_id, 20)
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            version = db.get(DocumentVersion, uuid.UUID(version_id))
            if document is None or version is None:
                return
            title = document.title
            active = document.active
            values = (version.file_path, version.file_name)
        chunks, generation = replace_document_index(
            values[0],
            document_id,
            active,
            file_name=values[1],
            document_title=title,
            document_version_id=version_id,
        )
        pages = get_document_page_count(values[0])
        with SessionLocal() as db:
            document = db.get(Document, uuid.UUID(document_id))
            version = db.get(DocumentVersion, uuid.UUID(version_id))
            if document and version:
                for item in db.query(DocumentVersion).filter(
                    DocumentVersion.document_id == document.id
                ):
                    item.is_current = item.id == version.id
                document.file_name = version.file_name
                document.file_path = version.file_path
                document.format = version.format
                document.mime_type = version.mime_type
                document.file_size = version.file_size
                document.version = version.version
                document.versions = sorted(
                    {*(document.versions or []), version.version},
                    key=lambda value: [int(part) for part in value.split(".")],
                    reverse=True,
                )
                document.page_count = pages
                document.chunk_count = chunks
                document.current_generation = generation
                document.progress = 100
                document.status = "Prêt"
                document.error_message = None
                document.indexed_at = datetime.now(timezone.utc)
                version.page_count = pages
                version.chunk_count = chunks
                version.status = "Prêt"
                version.error_message = None
                db.commit()
    except Exception as exc:
        _record_failure(
            document_id,
            version_id,
            f"Nouvelle version refusée, la version précédente reste active : {exc}",
            initial=False,
            mark_version_error=mark_version_error,
        )


def _record_failure(
    document_id: str,
    version_id: str | None,
    message: str,
    *,
    initial: bool,
    mark_version_error: bool = True,
) -> None:
    with SessionLocal() as db:
        document = db.get(Document, uuid.UUID(document_id))
        version = db.get(DocumentVersion, uuid.UUID(version_id)) if version_id else None
        if document:
            document.progress = 0
            document.status = "Erreur" if initial else "Prêt"
            document.error_message = message
        if version:
            version.status = "Erreur" if mark_version_error else "Prêt"
            version.error_message = message
        db.commit()
