from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from llama_index.llms.ollama import Ollama

from app.models.conversation import Conversation, Message
from app.services.rag_observability import complete_with_metrics, set_trace_attribute


MAX_HISTORY_MESSAGES = 6
MAX_MESSAGE_CONTEXT_CHARS = 1500
CONTEXT_REFERENCE_WORDS = {
    "ca", "cela", "ceci", "celui", "celle", "ceux", "celles",
    "elle", "elles", "eux", "leur", "leurs", "lui", "y",
}
CONTEXT_REFERENCE_PATTERNS = (
    r"\bce(?:t|tte|s)?\s+(?:delai|document|etape|phase|service|programme|session)\b",
    # Un ordinal temporel explicite (première semaine, premier jour) est autonome.
    # Seuls un ordinal substantivé ou une formulation explicitement enchaînée
    # sont considérés comme des références à l'historique.
    r"\b(?:le|la)\s+(?:premier|premiere|second|seconde|deuxieme|troisieme|quatrieme|cinquieme|dernier|derniere)\b(?=\s*(?:[?!.,;:]|$|(?:est|sont|doit|doivent|serait|seraient)\b))",
    r"^(?:et|sinon|alors)\b.*\b(?:premier|premiere|second|seconde|deuxieme|troisieme|quatrieme|cinquieme)\s+(?:element|etape|phase|piece|suivi)\b",
    r"\b(?:ce|cette)\s+(?:dernier|derniere)\b",
    r"\bla\s+bas\b",
    r"\ben\s+(?:a|est|ont|sont)\b",
    r"\b(?:combien|que)\s+(?:faut|doit)(?:\s+il)?\s+en\s+(?:envoyer|fournir|preparer|transmettre)\b",
    r"\b(?:doit|est|peut|pourrait|serait|sont|devrait)\s+(?:il|ils)\b",
)


def get_conversation_history(
    db: Session,
    conversation: Conversation,
    limit: int = MAX_HISTORY_MESSAGES,
) -> list[Message]:
    """
    Récupère les derniers messages de la conversation
    dans l'ordre chronologique.
    """

    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()

    return list(reversed(messages))


def build_conversation_context(
    messages: list[Message],
) -> str:
    """
    Transforme l'historique en contexte textuel.
    """

    if not messages:
        return ""

    lines: list[str] = []

    for message in messages:
        role = "Utilisateur" if message.role == "user" else "Assistant"
        content = message.content[:MAX_MESSAGE_CONTEXT_CHARS]
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def needs_contextualization(question: str) -> bool:
    """Indique si une question dépend probablement d'un échange précédent."""
    normalized = unicodedata.normalize("NFKD", question.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    words = re.findall(r"[a-z0-9]+", normalized)

    if CONTEXT_REFERENCE_WORDS.intersection(words):
        return True
    if any(re.search(pattern, normalized) for pattern in CONTEXT_REFERENCE_PATTERNS):
        return True

    question_words = {"comment", "combien", "ou", "pourquoi", "quand", "que", "qui"}
    function_words = question_words | {
        "a", "au", "aux", "de", "des", "du", "est", "la", "le", "les", "se",
        "un", "une",
    }
    content_words = [word for word in words if word not in function_words]
    return bool(words and words[0] in question_words and len(content_words) <= 1)


def contextualize_question(
    question: str,
    messages: list[Message],
    llm: Ollama,
) -> str:
    """
    Reformule une question dépendante du contexte conversationnel
    afin qu'elle puisse être utilisée pour la recherche documentaire.

    Si la question est déjà autonome, elle doit être conservée.
    """

    if not messages or not needs_contextualization(question):
        return question

    ordinal_reference = resolve_ordinal_reference(question, messages)
    if ordinal_reference:
        return f"{question.rstrip(' ?')} (référence : {ordinal_reference}) ?"

    history = build_conversation_context(messages)

    prompt = f"""
Tu es un module de reformulation pour un assistant d'onboarding.

Ta tâche est de transformer la dernière question de l'utilisateur
en une question autonome pouvant être utilisée pour effectuer
une recherche dans une base documentaire.

Règles :
- Utilise l'historique uniquement pour résoudre les références
  comme "ça", "cela", "et pour lui", "et pour un étudiant étranger",
  "la deuxième étape", etc.
- Ne réponds pas à la question.
- N'ajoute aucune information qui n'est pas présente dans la question
  ou dans l'historique.
- Si la question est déjà autonome, conserve-la presque telle quelle.
- Retourne uniquement la question reformulée.
- Ne mets pas de guillemets.
- Ne donne aucune explication.

Historique :
{history}

Nouvelle question :
{question}

Question autonome :
"""

    set_trace_attribute("historyMessageCount", len(messages))
    set_trace_attribute("historyChars", len(history))
    response = complete_with_metrics(llm, prompt, "reformulation")

    contextualized = str(response).strip()
    set_trace_attribute("reformulatedQuestion", contextualized or question)

    return contextualized or question


def resolve_ordinal_reference(question: str, messages: list[Message]) -> str | None:
    """Résout une référence comme « la deuxième » depuis une liste numérotée."""
    normalized = unicodedata.normalize("NFKD", question.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    ordinal_numbers = {
        "premier": 1,
        "premiere": 1,
        "second": 2,
        "seconde": 2,
        "deuxieme": 2,
        "troisieme": 3,
        "quatrieme": 4,
        "cinquieme": 5,
    }
    target = next(
        (number for ordinal, number in ordinal_numbers.items() if re.search(rf"\b{ordinal}\b", normalized)),
        None,
    )
    if target is None:
        return None

    item_pattern = re.compile(r"(?m)^\s*([1-9])\s*[.)-]\s*([^:\n]+)")
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        for number, label in item_pattern.findall(message.content):
            if int(number) == target:
                return label.strip(" .;–—-")
    return None
