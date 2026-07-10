from performance_agent.memory.schemas import Locale
from performance_agent.reports.labels import LABEL_KEYS, LABELS


def test_all_locales_present():
    assert set(LABELS) == {"en", "fr", "es"}


def test_every_locale_has_every_key():
    for locale, mapping in LABELS.items():
        assert set(mapping) == set(LABEL_KEYS), f"{locale} label drift"


def test_locale_type_matches_schema():
    # the Locale Literal in memory.schemas is the source of truth
    assert set(LABELS) == set(Locale.__args__)
