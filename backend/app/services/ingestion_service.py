import json
import os
import re
import uuid
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from llama_index.core import (
    Document,
    Settings,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from pypdf import PdfReader
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointIdsList

from app.core.embed_config import get_embed_model

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "onboarding_docs")
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EXTENDED_PROPERTIES_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
WORD = f"{{{WORD_NAMESPACE}}}"
SECTION_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\.\s+\S")


def _get_vector_store() -> QdrantVectorStore:
    client = QdrantClient(url=os.getenv("QDRANT_URL"))
    return QdrantVectorStore(client=client, collection_name=COLLECTION_NAME)


def _paragraph_segments(paragraph: ElementTree.Element) -> list[str]:
    """Découpe un paragraphe Word aux sauts de page réellement rendus."""
    segments: list[list[str]] = [[]]
    for element in paragraph.iter():
        if element.tag == f"{WORD}lastRenderedPageBreak" or (
            element.tag == f"{WORD}br"
            and element.get(f"{WORD}type") == "page"
        ):
            segments.append([])
        elif element.tag == f"{WORD}t":
            segments[-1].append(element.text or "")
        elif element.tag == f"{WORD}tab":
            segments[-1].append("\t")
    return ["".join(segment).strip() for segment in segments]


def _paragraph_style(paragraph: ElementTree.Element) -> str | None:
    style = paragraph.find(f"./{WORD}pPr/{WORD}pStyle")
    return style.get(f"{WORD}val") if style is not None else None


def _is_section_heading(text: str, style: str | None) -> bool:
    if style and style.startswith("TOC"):
        return False
    return bool(SECTION_HEADING_PATTERN.match(text)) or style == "Titre0"


def _load_docx_documents(file_path: str) -> list[Document]:
    """Extrait un DOCX en blocs page/section afin de conserver leur provenance."""
    try:
        with ZipFile(file_path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("Le fichier DOCX est invalide ou illisible.") from exc

    body = root.find(f".//{WORD}body")
    if body is None:
        raise ValueError("Le fichier DOCX ne contient aucun corps de document.")

    page = 1
    section: str | None = None
    blocks: OrderedDict[tuple[int, str | None], list[str]] = OrderedDict()

    # ElementTree conserve ici l'ordre XML, y compris les paragraphes des tableaux.
    for paragraph in body.iter(f"{WORD}p"):
        style = _paragraph_style(paragraph)
        segments = _paragraph_segments(paragraph)
        for index, text in enumerate(segments):
            if text:
                if style and style.startswith("TOC"):
                    effective_section = "Sommaire"
                else:
                    if _is_section_heading(text, style):
                        section = text
                    effective_section = section
                blocks.setdefault((page, effective_section), []).append(text)
            if index < len(segments) - 1:
                page += 1

    documents = []
    for (page_number, section_title), lines in blocks.items():
        metadata = {
            "page": page_number,
            "page_label": str(page_number),
            "source_type": "docx",
        }
        if section_title:
            metadata["section"] = section_title
        documents.append(Document(text="\n".join(lines), metadata=metadata))
    return documents


def _load_pdf_documents(file_path: str) -> list[Document]:
    """Extrait le texte d'un PDF page par page en conservant sa provenance."""
    try:
        reader = PdfReader(file_path)
        documents = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                documents.append(Document(
                    text=text,
                    metadata={
                        "page": page_number,
                        "page_label": str(page_number),
                        "source_type": "pdf",
                    },
                ))
    except Exception as exc:
        raise ValueError("Le fichier PDF est invalide ou illisible.") from exc
    if not documents:
        raise ValueError("Le fichier PDF ne contient aucun texte exploitable.")
    return documents


def get_document_page_count(file_path: str) -> int | None:
    """Retourne le nombre de pages d'un PDF ou celui déclaré par Word."""
    extension = Path(file_path).suffix.lower()
    if extension == ".pdf":
        try:
            return len(PdfReader(file_path).pages)
        except Exception:
            return None
    if extension != ".docx":
        return None
    try:
        with ZipFile(file_path) as archive:
            root = ElementTree.fromstring(archive.read("docProps/app.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError):
        return None
    pages = root.find(f"{{{EXTENDED_PROPERTIES_NAMESPACE}}}Pages")
    try:
        return int(pages.text) if pages is not None and pages.text else None
    except ValueError:
        return None


def index_document(
    file_path: str,
    document_id: str,
    active: bool,
    *,
    file_name: str | None = None,
    document_title: str | None = None,
    generation: str | None = None,
    document_version_id: str | None = None,
) -> int:
    """Charge, découpe et indexe un document dans Qdrant. Retourne le nombre de chunks créés."""
    Settings.embed_model = get_embed_model()
    Settings.llm = None

    if Path(file_path).suffix.lower() == ".docx":
        documents = _load_docx_documents(file_path)
    else:
        documents = _load_pdf_documents(file_path)
    for doc in documents:
        doc.metadata["app_document_id"] = document_id
        doc.metadata["active"] = active
        if generation:
            doc.metadata["index_generation"] = generation
        if document_version_id:
            doc.metadata["document_version_id"] = document_version_id
        if file_name:
            doc.metadata["file_name"] = file_name
        if document_title:
            doc.metadata["document_title"] = document_title

    splitter = SentenceSplitter(chunk_size=800, chunk_overlap=100)
    nodes = splitter.get_nodes_from_documents(documents)

    storage_context = StorageContext.from_defaults(vector_store=_get_vector_store())
    VectorStoreIndex(nodes, storage_context=storage_context)

    return len(nodes)


def _filter_for_document(document_id: str) -> Filter:
    return Filter(
        must=[FieldCondition(key="app_document_id", match=MatchValue(value=document_id))]
    )


def _filter_for_generation(document_id: str, generation: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="app_document_id", match=MatchValue(value=document_id)),
            FieldCondition(key="index_generation", match=MatchValue(value=generation)),
        ]
    )


def replace_document_index(
    file_path: str,
    document_id: str,
    active: bool,
    *,
    file_name: str | None = None,
    document_title: str | None = None,
    document_version_id: str | None = None,
) -> tuple[int, str]:
    """Construit une génération inactive avant de remplacer l'index existant."""
    client = QdrantClient(url=os.getenv("QDRANT_URL"))
    old_ids = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=_filter_for_document(document_id),
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        old_ids.extend(point.id for point in points)
        if offset is None:
            break

    generation = str(uuid.uuid4())
    generation_filter = _filter_for_generation(document_id, generation)
    activated = False
    try:
        chunk_count = index_document(
            file_path,
            document_id,
            False,
            file_name=file_name,
            document_title=document_title,
            generation=generation,
            document_version_id=document_version_id,
        )
        indexed_count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=generation_filter,
            exact=True,
        ).count
        if chunk_count == 0 or indexed_count != chunk_count:
            raise RuntimeError(
                f"Index incomplet : {indexed_count} point(s) écrit(s) pour {chunk_count} chunk(s)."
            )
        _activate_generation_payloads(
            client,
            generation_filter,
            active=active,
            document_version_id=document_version_id,
        )
        activated = True
        if old_ids:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=PointIdsList(points=old_ids),
                wait=True,
            )
        return chunk_count, generation
    except Exception:
        # Tant que l'ancienne génération n'a pas été supprimée, elle reste utilisable.
        if not activated:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=generation_filter,
                wait=True,
            )
        raise


def _activate_generation_payloads(
    client: QdrantClient,
    generation_filter: Filter,
    *,
    active: bool,
    document_version_id: str | None,
) -> None:
    """Synchronise le payload filtrable et le JSON LlamaIndex avant activation."""
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=generation_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = dict(point.payload or {})
            update = {"active": active}
            if document_version_id:
                update["document_version_id"] = document_version_id
            serialized = payload.get("_node_content")
            if isinstance(serialized, str):
                try:
                    node_content = json.loads(serialized)
                    metadata = node_content.setdefault("metadata", {})
                    metadata["active"] = active
                    if document_version_id:
                        metadata["document_version_id"] = document_version_id
                    update["_node_content"] = json.dumps(node_content, ensure_ascii=False)
                except (TypeError, ValueError):
                    # Compatibilité : un ancien payload illisible reste requêtable
                    # via les métadonnées Qdrant de premier niveau.
                    pass
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update,
                points=PointIdsList(points=[point.id]),
                wait=True,
            )
        if offset is None:
            break


def update_document_active(
    document_id: str,
    active: bool,
    document_version_id: str | None = None,
) -> int:
    """Met à jour l'état des vecteurs d'un document sans recalculer ses embeddings."""
    client = QdrantClient(url=os.getenv("QDRANT_URL"))
    document_filter = _filter_for_document(document_id)
    point_count = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=document_filter,
        exact=True,
    ).count
    _activate_generation_payloads(
        client,
        document_filter,
        active=active,
        document_version_id=document_version_id,
    )
    return point_count


def delete_document_vectors(document_id: str) -> None:
    """Supprime les vecteurs Qdrant associés à un document (avant réindexation)."""
    client = QdrantClient(url=os.getenv("QDRANT_URL"))
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=_filter_for_document(document_id),
        wait=True,
    )
