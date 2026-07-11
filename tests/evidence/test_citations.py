from performance_agent.evidence.citations import find_unknown_references, format_citation
from performance_agent.evidence.schemas import EvidenceEntry

ENTRY = EvidenceEntry.model_validate(
    {
        "id": "strength-economy",
        "title": "Strength training improves running economy",
        "authors": ["Doe J", "Roe R", "Poe P"],
        "year": 2020,
        "journal": "J Sports Sci",
        "study_type": "meta_analysis",
        "conclusions": "It works.",
        "evidence_level": "strong",
        "doi": "10.1000/strength",
        "pmid": "123456",
    }
)


def test_citation_contains_the_load_bearing_fields():
    citation = format_citation(ENTRY)
    assert "Doe J" in citation
    assert "2020" in citation
    assert "Strength training improves running economy" in citation
    assert "10.1000/strength" in citation


def test_citation_without_journal_still_formats():
    entry = ENTRY.model_copy(update={"journal": None})
    assert "2020" in format_citation(entry)


def test_known_references_pass_the_check():
    text = "Heavy lifting helps (DOI: 10.1000/strength, PMID: 123456)."
    assert find_unknown_references(text, [ENTRY]) == []


def test_unknown_doi_is_flagged():
    text = "As shown in the landmark study (doi:10.9999/fabricated)."
    unknown = find_unknown_references(text, [ENTRY])
    assert unknown == ["10.9999/fabricated"]


def test_unknown_pmid_is_flagged():
    text = "See PMID: 99887766 for details."
    assert find_unknown_references(text, [ENTRY]) == ["PMID:99887766"]


def test_doi_with_trailing_punctuation_is_normalized():
    text = "Great result (10.9999/fabricated)."
    assert find_unknown_references(text, [ENTRY]) == ["10.9999/fabricated"]


def test_text_without_references_is_clean():
    assert find_unknown_references("Squat 5x5 at 80%.", [ENTRY]) == []


def test_pubmed_url_with_unknown_id_is_flagged():
    text = "See https://pubmed.ncbi.nlm.nih.gov/99887766/ for the abstract."
    assert find_unknown_references(text, [ENTRY]) == ["PMID:99887766"]


def test_pubmed_url_with_known_id_passes():
    text = "See https://pubmed.ncbi.nlm.nih.gov/123456/ for details."
    assert find_unknown_references(text, [ENTRY]) == []


def test_same_unknown_pmid_in_both_forms_is_reported_once():
    text = "See PMID: 99887766 (https://pubmed.ncbi.nlm.nih.gov/99887766/)."
    assert find_unknown_references(text, [ENTRY]) == ["PMID:99887766"]


def test_known_doi_cited_as_url_with_trailing_path_passes():
    text = "Full text at https://doi.org/10.1000/strength/full-text.html today."
    assert find_unknown_references(text, [ENTRY]) == []


BOOK = EvidenceEntry(
    id="book-manuel-ultime-musculation",
    title="Manuel ultime de musculation — Connaissances scientifiques et méthodologie",
    authors=["Pourcelot C", "Reiss D", "Caverne A", "Albignac T"],
    year=2023,
    journal="Éditions Amphora",
    study_type="reference_book",
    conclusions="Technique and pedagogy reference for strength training.",
    evidence_level="expert",
    isbn="978-2-7576-0546-2",
)


def test_format_citation_includes_isbn():
    citation = format_citation(BOOK)
    assert "ISBN: 978-2-7576-0546-2." in citation
    assert "Éditions Amphora." in citation


def test_known_isbn_reference_passes():
    text = "Technique cues follow the Manuel ultime (ISBN 978-2-7576-0546-2)."
    assert find_unknown_references(text, [BOOK]) == []


def test_unknown_isbn_reference_is_flagged():
    text = "As shown in some book (ISBN: 978-0-0000-0000-2)."
    assert find_unknown_references(text, [BOOK]) == ["ISBN:978-0-0000-0000-2"]


def test_isbn_matching_ignores_hyphenation():
    text = "See ISBN 9782757605462 for details."
    assert find_unknown_references(text, [BOOK]) == []
