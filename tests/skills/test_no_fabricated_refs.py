"""The anti-fabrication scanner must pass over the skill texts themselves."""

from performance_agent.evidence.citations import find_unknown_references
from performance_agent.evidence.corpus import load_corpus


def test_skill_bodies_contain_no_unknown_references(skills):
    corpus = load_corpus()
    for skill in skills:
        unknown = find_unknown_references(skill.body, corpus)
        assert unknown == [], f"{skill.path} references unknown works: {unknown}"
