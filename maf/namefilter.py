"""The name filter: Microsoft Presidio PERSON detection before saving.

No list of student names; only a short list of words that are never people (see NOT_PEOPLE). The spaCy model is loaded once, lazily,
because it is the slowest part of startup and only submissions need it.
"""

import threading

from .settings import Settings

PERSON = "PERSON"
# Words the language model mistakes for people's names but never are on MAF. Lowercase.
NOT_PEOPLE = {"minerva"}


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
        joined = "\n".join(t for t in texts if t)
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
        return any(joined[found.start:found.end].strip().lower() not in NOT_PEOPLE for found in results)
