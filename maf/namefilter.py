"""The name filter: Microsoft Presidio PERSON detection before saving.

No list of student names; only a short list of words that are never people (see NOT_PEOPLE and demonyms.py). The spaCy model is loaded once, lazily,
because it is the slowest part of startup and only submissions need it.
"""

import re
import threading

from . import markdown
from .demonyms import is_demonym
from .settings import Settings

PERSON = "PERSON"
# Words the language model mistakes for people's names but never are on MAF. Lowercase.
# Nationalities ("Kazakh") count too: see maf/demonyms.py.
NOT_PEOPLE: set[str] = set()  # plus the organization's own word (settings.org_tag)
# Chat abbreviations confuse the model about the words around them: "Tbf Minerva" reads like "Jane Smith",
# and "Tbf Priya Raman" like an organisation. They're taken out before the model reads the text.
CHAT_ABBREVIATIONS = ("tbf", "tbh", "ngl", "imo", "imho", "idk", "fwiw", "btw", "iirc", "afaik", "lol", "lmao", "smh", "fr")
_CHAT = re.compile(rf"\b(?:{'|'.join(CHAT_ABBREVIATIONS)})\b,?", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+(?:['’]s)?")  # keeps "kazakh's" as one word


def without_chat_abbreviations(text: str) -> str:
    return _CHAT.sub(" ", text)


def _is_person(span: str, never_people: set[str]) -> bool:
    """A flagged span counts unless every word in it is on the never-a-person list."""
    words = _WORD.findall(span.lower())
    return not words or any(word not in never_people and not is_demonym(word) for word in words)


_ANALYZERS: dict[str, object] = {}  # one loaded model per process, whichever app asks (tests make many apps)
_ANALYZERS_LOCK = threading.Lock()
_ANALYZE_LOCK = threading.Lock()  # the shared model analyzes one text at a time


def _analyzer_for(model: str):
    with _ANALYZERS_LOCK:
        if model not in _ANALYZERS:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(
                nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model}]}
            )
            _ANALYZERS[model] = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        return _ANALYZERS[model]


class NameFilter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _engine(self):
        return _analyzer_for(self._settings.spacy_model)

    def warm_up(self) -> None:
        """Loads the language model now (a few seconds), so the first post after a restart isn't slow."""
        if self._settings.name_filter_enabled:
            self.finds_name("Warming up the name check.")

    def finds_name(self, *texts: str | None) -> bool:
        """True if any text contains a PERSON entity above the threshold."""
        if not self._settings.name_filter_enabled:
            return False
        # Both as typed and as shown (markdown symbols gone), so formatting can't hide a name.
        given = [t for t in texts if t]
        joined = without_chat_abbreviations("\n\n".join(given + [markdown.words(t) for t in given]))
        if not joined.strip():
            return False
        engine = self._engine()
        with _ANALYZE_LOCK:
            results = engine.analyze(
                text=joined,
                entities=[PERSON],
                language="en",
                score_threshold=self._settings.name_filter_threshold,
            )
        never_people = NOT_PEOPLE | {self._settings.org_tag}
        return any(_is_person(joined[found.start:found.end], never_people) for found in results)
