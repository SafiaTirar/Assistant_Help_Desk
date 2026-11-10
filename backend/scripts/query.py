import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from app.services.rag_service import CONFIDENCE_THRESHOLD, get_rag_service


def main():
    print("🔎 Chargement de l'index Qdrant...")
    service = get_rag_service()
    print(f"✅ Prêt. Seuil de confiance : {CONFIDENCE_THRESHOLD}\n")

    while True:
        question = input("❓ Ta question (ou 'exit' pour quitter) : ").strip()
        if question.lower() in ("exit", "quit"):
            break
        if not question:
            continue

        result = service.answer_question(question)
        print(f"\n💬 [{result.status}] {result.answer}\n")


if __name__ == "__main__":
    main()
