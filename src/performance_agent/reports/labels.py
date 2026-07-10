"""Static report labels per locale (the program body language is the agent's)."""

LABEL_KEYS = (
    "report_title",
    "athlete",
    "goal",
    "program_version",
    "generated_on",
    "adaptation_reason",
    "references",
    "evidence_note",
)

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "report_title": "Training Report",
        "athlete": "Athlete",
        "goal": "Goal",
        "program_version": "Program version",
        "generated_on": "Generated on",
        "adaptation_reason": "Adaptation reason",
        "references": "References",
        "evidence_note": "Evidence grades: ★★★★★ strong … ★☆☆☆☆ expert opinion.",
    },
    "fr": {
        "report_title": "Rapport d'entraînement",
        "athlete": "Athlète",
        "goal": "Objectif",
        "program_version": "Version du programme",
        "generated_on": "Généré le",
        "adaptation_reason": "Raison de l'adaptation",
        "references": "Références",
        "evidence_note": "Niveaux de preuve : ★★★★★ solide … ★☆☆☆☆ avis d'expert.",
    },
    "es": {
        "report_title": "Informe de entrenamiento",
        "athlete": "Atleta",
        "goal": "Objetivo",
        "program_version": "Versión del programa",
        "generated_on": "Generado el",
        "adaptation_reason": "Motivo de la adaptación",
        "references": "Referencias",
        "evidence_note": "Niveles de evidencia: ★★★★★ sólido … ★☆☆☆☆ opinión experta.",
    },
}
