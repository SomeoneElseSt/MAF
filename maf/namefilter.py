"""The name filter: Microsoft Presidio PERSON detection before saving.

No list of student names; only a short list of words that are never people (see NOT_PEOPLE). The spaCy model is loaded once, lazily,
because it is the slowest part of startup and only submissions need it.
"""

import re
import threading

from .settings import Settings

PERSON = "PERSON"
# Words the language model mistakes for people's names but never are on MAF. Lowercase.
NOT_PEOPLE = {"minerva"}
# Chat abbreviations confuse the model about the words around them: "Tbf Minerva" reads like "Jane Smith",
# and "Tbf Priya Raman" like an organisation. They're taken out before the model reads the text.
CHAT_ABBREVIATIONS = ("tbf", "tbh", "ngl", "imo", "imho", "idk", "fwiw", "btw", "iirc", "afaik", "lol", "lmao", "smh", "fr")
_CHAT = re.compile(rf"\b(?:{'|'.join(CHAT_ABBREVIATIONS)})\b,?", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+")


def without_chat_abbreviations(text: str) -> str:
    return _CHAT.sub(" ", text)


def _is_person(span: str) -> bool:
    """A flagged span counts unless every word in it is on the never-a-person list."""
    words = _WORD.findall(span.lower())
    return not words or any(word not in NOT_PEOPLE for word in words)


class NameFilter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._analyzer = None
        self._lock = threading.Lock()
        self._analyze_lock = threading.Lock()

    def _engine(self):
        with self._lock:
            if self._analyzer is None:
                from presidio_analyzer import AnalyzerEngine
                from presidio_analyzer.nlp_engine import NlpEngineProvider

                provider = NlpEngineProvider(
                    nlp_configuration={
                        "nlp_engine_name": "spacy",
                        "models": [{"lang_code": "en", "model_name": self._settings.spacy_model}],
                    }
                )
                self._analyzer = AnalyzerEngine(
                    nlp_engine=provider.create_engine(), supported_languages=["en"]
                )
            return self._analyzer

    def warm_up(self) -> None:
        """Loads the language model now (a few seconds), so the first post after a restart isn't slow."""
        if self._settings.name_filter_enabled:
            self.finds_name("Warming up the name check.")

    def finds_name(self, *texts: str | None) -> bool:
        """True if any text contains a PERSON entity above the threshold."""
        if not self._settings.name_filter_enabled:
            return False
        joined = without_chat_abbreviations("\n".join(t for t in texts if t))
        if not joined.strip():
            return False
        engine = self._engine()
        with self._analyze_lock:
            results = engine.analyze(
                text=joined,
                entities=[PERSON],
                language="en",
                score_threshold=self._settings.name_filter_threshold,
            )
        return any(_is_person(joined[found.start:found.end]) for found in results)
