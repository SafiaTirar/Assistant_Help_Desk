from __future__ import annotations

import math
import os
import re
import unicodedata

from app.services.rag_observability import set_trace_attribute, timed_step


PROMPT_INJECTION_MESSAGE = (
    "Je ne peux pas ignorer mes règles, révéler des instructions internes ni "
    "inventer des données personnelles. Je réponds uniquement à partir des "
    "documents d'onboarding disponibles."
)
AMBIGUOUS_QUESTION_MESSAGE = (
    "Les documents utilisent ces informations sans permettre de confirmer une "
    "réponse exacte. Pouvez-vous préciser le contexte ou la référence attendue ?"
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if not denominator:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / denominator


class ScopeClassifier:
    """Classifie la portée avec règles de sûreté puis proximité sémantique."""

    IN_SCOPE_EXAMPLES = (
        "démarches RH et administratives du parcours d'intégration",
        "documents à préparer avant l'arrivée et le premier jour",
        "visa titre de séjour contrat autorisation administrative et accueil",
        "équipements informatiques badge bureau accès et services responsables",
        "formation suivi accompagnement et intégration des enseignants chercheurs",
    )
    OUT_OF_SCOPE_EXAMPLES = (
        "actualité classement international et nouvelles récentes de l'université",
        "architecture technique RAG modèle de base vectorielle et programmation",
        "politique météo sport musique cinéma films horoscope et résultats de football",
        "recettes de cuisine tourisme culture générale et capitale d'un pays",
        "informations personnelles privées sans rapport avec l'onboarding",
    )
    IN_SCOPE_HINTS = {
        "accueil", "arrivee", "autorisation", "badge", "bureau", "carte", "contrat",
        "demarche", "document", "dossier", "equipement", "formation", "integration",
        "legaliser", "onboarding", "ordinateur", "phase", "responsable", "sejour",
        "signature", "signer", "service", "visa",
    }
    EXPLICIT_OUT_OF_SCOPE_PATTERNS = (
        r"\b(?:base vectorielle|architecture rag|modele rag|futur rag)\b",
        r"\b(?:classement|actualite|meteo|football|horoscope|recette|capitale|cinema|film)\b",
        r"\b(?:politique|musique|temperature)\b",
    )
    PROMPT_INJECTION_PATTERNS = (
        r"\bignore\w*\s+(?:toutes?\s+)?(?:les\s+)?(?:consignes|instructions|regles)\b",
        r"\b(?:revele|affiche|donne)\w*\s+(?:tes|les)\s+instructions\s+systeme\b",
        r"\b(?:revele|affiche|donne)\w*\s+(?:ton|le|un)\s+prompt\s+systeme\b",
        r"\b(?:supprime|contourne|desactive)\w*\s+(?:les\s+)?(?:exigences|regles|protections)\b",
        r"\binvente\w*\s+(?:les\s+)?(?:coordonnees|donnees personnelles)\b",
        r"\bignore\w*\s+(?:les\s+)?(?:documents|sources)\b.*\binvente\w*\b",
        r"\breponds?\s+sans\s+(?:citer|respecter|utiliser)\b",
        r"\b(?:abandonne|affranchis\s+toi|contourne|desactive)\w*\b.*"
        r"\b(?:contrainte|preuve|source|document|sourcing)\w*\b",
        r"\b(?:change|modifie|altere)\w*\b.*\b(?:comportement|mode|regles?)\s+systeme\b",
        r"\b(?:affiche|revele|expose|divulgue)\w*\b.*"
        r"\b(?:secret|instruction|configuration|regle)\w*\s+(?:interne|systeme)\w*\b",
        r"\b(?:fabrique|invente|cree)\w*\b.*"
        r"\b(?:adresse|coordonnees|donnee|numero|telephone)\w*\s+(?:personnel|prive)\w*\b",
        r"\b(?:produis|genere|fabrique|invente)\w*\b.*\b(?:n existe pas|absent)\b.*"
        r"\b(?:source|document)\w*\b",
    )
    AMBIGUITY_PATTERNS = (
        r"\bdate exacte\b.*\bn\s*(?:moins\s*)?\d+\b",
        r"\b(?:est|sont)\b.*\bexactement\b.*\b(?:project manager|charge d integration)\b",
        r"\b(?:equivalent|equivalence|meme personne|meme role)\b.*\b(?:manager|charge|responsable)\b",
        r"^(?:et\s+)?(?:apres|ensuite|lequel|laquelle|lesquels|lesquelles|lui|elle|eux)\b\s*[?]?$",
        r"^(?:peut|doit|pourrait|devrait)\s+(?:il|elle|ils|elles)\b.*"
        r"\b(?:le|la|les|lui|leur)\b.*[?]?$",
        r"^lequel\b.*\b(?:valider|transmettre|signer|controler|verifier)\w*\b",
        r"\bquel\s+est\s+le\s+delai\s+d\s+acces\b",
    )

    def __init__(self, embed_model=None) -> None:
        self.embed_model = embed_model
        self._example_vectors: list[list[float]] | None = None
        self.out_of_scope_threshold = float(os.getenv("SCOPE_OUT_OF_SCOPE_THRESHOLD", "0.68"))
        self.out_of_scope_margin = float(os.getenv("SCOPE_OUT_OF_SCOPE_MARGIN", "0.10"))

    @classmethod
    def rule_based_status(cls, question: str) -> str | None:
        normalized = _normalize(question)
        # Une référence résolue par la mémoire est explicite et ne doit plus
        # être reclassée comme ambiguë à cause du pronom ou de l'ordinal initial.
        has_resolved_reference = "reference" in normalized
        if any(re.search(pattern, normalized) for pattern in cls.PROMPT_INJECTION_PATTERNS):
            return "prompt_injection"
        if not has_resolved_reference and any(
            re.search(pattern, normalized) for pattern in cls.AMBIGUITY_PATTERNS
        ):
            return "question_ambigue"
        if any(re.search(pattern, normalized) for pattern in cls.EXPLICIT_OUT_OF_SCOPE_PATTERNS):
            return "hors_perimetre"
        return None

    def classify(self, question: str) -> str | None:
        rule_status = self.rule_based_status(question)
        if rule_status is not None:
            return rule_status

        normalized = _normalize(question)
        if set(normalized.split()) & self.IN_SCOPE_HINTS:
            return None
        if self.embed_model is None:
            return None

        try:
            examples = self.IN_SCOPE_EXAMPLES + self.OUT_OF_SCOPE_EXAMPLES
            if self._example_vectors is None:
                with timed_step("classification_example_embedding", itemCount=len(examples)):
                    self._example_vectors = self.embed_model.get_text_embedding_batch(list(examples))
            with timed_step("classification_query_embedding", itemCount=1):
                question_vector = self.embed_model.get_text_embedding(question)
            split = len(self.IN_SCOPE_EXAMPLES)
            in_score = max(_cosine(question_vector, vector) for vector in self._example_vectors[:split])
            out_score = max(_cosine(question_vector, vector) for vector in self._example_vectors[split:])
            set_trace_attribute("scopeInScore", round(in_score, 6))
            set_trace_attribute("scopeOutScore", round(out_score, 6))
            set_trace_attribute("scopeScoreMargin", round(out_score - in_score, 6))
            if (
                out_score >= self.out_of_scope_threshold
                and out_score - in_score >= self.out_of_scope_margin
            ):
                return "hors_perimetre"
        except Exception:
            return None
        return None
