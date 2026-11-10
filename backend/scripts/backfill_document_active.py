import sys
from pathlib import Path

from sqlalchemy import select


sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.models.document import Document, DocumentVersion  # noqa: E402
from app.services.ingestion_service import update_document_active  # noqa: E402


def main() -> int:
    db = SessionLocal()
    errors: list[tuple[str, str]] = []
    processed_documents = 0
    updated_points = 0

    try:
        documents = db.scalars(select(Document).order_by(Document.created_at)).all()
        for document in documents:
            try:
                current_version = db.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == document.id,
                        DocumentVersion.is_current.is_(True),
                    )
                )
                point_count = update_document_active(
                    str(document.id),
                    document.active,
                    str(current_version.id) if current_version else None,
                )
                processed_documents += 1
                updated_points += point_count
                print(f"Document {document.id}: {point_count} point(s) mis à jour.")
            except Exception as exc:
                error_name = type(exc).__name__
                errors.append((str(document.id), error_name))
                print(f"Document {document.id}: erreur de synchronisation ({error_name}).")
    finally:
        db.close()

    print("\nRésumé du backfill :")
    print(f"- Documents trouvés : {processed_documents + len(errors)}")
    print(f"- Documents traités : {processed_documents}")
    print(f"- Points mis à jour : {updated_points}")
    print(f"- Erreurs : {len(errors)}")

    if errors:
        print("\nDocuments en erreur :")
        for document_id, error in errors:
            print(f"- {document_id}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
