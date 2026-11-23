"""The name filter: Microsoft Presidio PERSON detection before saving.

No allowlist and no stored list of names. The spaCy model is loaded once, lazily,
because it is the slowest part of startup and only submissions need it.
"""

import threading

from .settings import Settings

PERSON = "PERSON"


class NameFilter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._analyzer = None
        self._lock = threading.Lock()

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

    def finds_name(self, *texts: str | None) -> bool:
        """True if any text contains a PERSON entity above the threshold."""
        if not self._settings.name_filter_enabled:
            return False
        joined = "\n".join(t for t in texts if t)
        if not joined.strip():
            return False
        results = self._engine().analyze(
            text=joined,
            entities=[PERSON],
            language="en",
            score_threshold=self._settings.name_filter_threshold,
        )
        return bool(results)
