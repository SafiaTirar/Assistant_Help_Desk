"""Point d'entrée historique désactivé pour éviter les vecteurs orphelins.

L'ingestion doit passer par l'administration. Ce flux crée d'abord le document
dans PostgreSQL, puis ajoute aux chunks Qdrant les métadonnées ``active`` et
``app_document_id`` utilisées par le pipeline RAG.
"""

import sys


MESSAGE = (
    "Ingestion directe désactivée : importez ou réindexez le document depuis "
    "l'administration afin de conserver PostgreSQL et Qdrant synchronisés."
)


def main() -> None:
    print(MESSAGE, file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
