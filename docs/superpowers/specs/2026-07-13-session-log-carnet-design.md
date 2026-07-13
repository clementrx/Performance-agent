# Carnet de séance copiable — design

**Date :** 2026-07-13
**Statut :** validé par l'athlète, prêt pour le plan d'implémentation

## Problème

L'athlète copie son programme (`.md`) dans Notes iPhone, y note reps/poids
pendant la séance, puis doit **retranscrire ces chiffres en prose dans la
conversation** chaque jour. Le coach l'interroge ensuite set par set pour
reconstruire l'appel `log_session`. Cette retranscription est le point de
friction — pas le suivi pendant la séance, qui convient déjà.

## Objectif

Rendre le report d'une séance quasi sans effort : la note iPhone est **déjà
structurée** pendant la séance, si bien qu'un seul copier-coller dans la
conversation suffit à tout parser d'un coup, sans réinterrogatoire.

Contrainte retenue avec l'athlète : **convention seule, aucun code moteur**.
Le format vit dans le `.md` et dans les skills ; le parsing est fait par le
modèle en conversation.

## Le contrat de format

Chaque séance-type embarque un bloc autoportant, prêt à coller dans Notes :

```
📋 LOG — S1 J1 Push
Date:
Douleur (dos/épaule/coude): non
RPE séance:
—
Dév incliné halt:
Dév épaule dossier:
Écarté poulie:
Élévations lat:
Rot. ext. L-fly:
Ext. triceps:
Notes:
```

**Règle de saisie unique :** par série, `poids×reps` séparés par des espaces.

- `22x9` = 22 kg, 9 reps.
- Séparateurs de multiplication acceptés : `x`, `×`, `*`.
- Décimales autorisées pour la charge : `11.3x15`.
- **Poids du corps** (bird dog, dead bug…) : nombre seul = reps au poids du
  corps. `10 10 10` = 3 séries de 10 reps, charge 0.
- **Isométrie** (planches, gainage latéral) : `Ns` = tenue de N secondes.
  `30s 35s 30s` = 3 tenues. Logué avec la durée en `notes` de l'exercice
  (pas de reps/charge inventés).
- Ligne d'exercice laissée vide = exercice non réalisé (non logué).
- Charges haltères = **charge par bras** (cohérent avec les logs existants).
- Suffixe `/côté` implicite : pour un exercice unilatéral, un seul nombre de
  reps vaut « par côté » (le programme porte déjà la mention).

**Champs d'en-tête :**

- `Date:` — date de réalisation (jour/mois ; l'année est déduite du contexte).
- `Douleur (dos/épaule/coude):` — une seule ligne globale. `non` par défaut.
  Un `oui` (ou toute mention de douleur) **court-circuite le log** et route
  vers `program-adaptation` : la douleur prime, on n'enregistre pas une séance
  « normale » par-dessus un signal de sécurité. Le coach demande alors sur
  quel mouvement avant toute autre chose.
- `RPE séance:` — RPE global (1–10), alimente la sRPE.
- `Notes:` — texte libre, versé dans `SessionEntry.notes`.

Le marqueur `📋 LOG — <label séance>` sert à la fois d'ancre de détection
(le coach reconnaît un bloc à parser) et de lien vers la séance planifiée
(`session_plan_id` via le label).

## Comportement de parsing (convention coach)

Quand un bloc `📋 LOG` est collé dans la conversation :

1. Si la ligne Douleur ≠ `non` → ne pas loguer ; passer à `training-checkin` /
   `program-adaptation`, en demandant le mouvement en cause.
2. Sinon, parser chaque ligne d'exercice non vide en une liste de sets
   `{load_kg, reps}` ; associer les noms aux exercices du programme actif.
3. **Confirmer en une ligne** le total parsé avant d'écrire :
   « 6 exos, 22 sets, RPE 8 — je logue ? ». Jamais de log muet.
4. Sur accord → `log_session` (`source="programmed"`, `session_plan_id` déduit
   du label, `performed_at` depuis `Date:`, `rpe` depuis `RPE séance:`).
5. Bloc illisible ou ambigu → redemander, ne rien deviner.

## Livrables

### 1. Retrofit du programme actuel (donnée athlète, immédiat)

Ajouter une section « 📋 Carnet de séance (à copier dans Notes) » à
`athlete-data/programs/program-v1.md`, avec un bloc par séance-type J1→J7,
exos repris des séances déjà décrites. Utilisable dès la prochaine séance.
Hors repo — c'est le fichier de suivi de l'athlète, pas un artefact versionné
du produit.

### 2. Émission automatique (repo)

`skills/program-optimization/SKILL.md` : quand l'optimiseur construit les
séances concrètes (section « Sessions with the athlete »), il génère le Carnet
à partir des exercices déjà retenus — mêmes noms, même ordre. Tout futur
programme sauvegardé embarque son Carnet. Aucune source d'exercices nouvelle :
le Carnet est une projection des séances déjà écrites.

### 3. Convention de parsing (repo)

`skills/training-checkin/SKILL.md` (chemin de log) et `skills/session-day/SKILL.md`
(séance du jour) : documenter le comportement de parsing ci-dessus, y compris
la priorité de la ligne Douleur et la confirmation obligatoire avant `log_session`.

### 4. Tests (repo)

`tests/skills/` (style `test_structure.py`, qui teste le contenu des docs) :

- Le Carnet et sa règle `poids×reps` sont documentés dans
  `program-optimization`.
- La convention de parsing (marqueur `📋 LOG`, priorité Douleur, confirmation
  avant log) est documentée dans `training-checkin`.
- Le marqueur de format (`📋 LOG`) est cohérent entre émission et parsing —
  garde-fou contre une dérive du contrat entre les deux skills.

## Hors périmètre (YAGNI)

- Pas de parser déterministe en code (`parse_session_shorthand`) : écarté au
  profit de la convention. À rouvrir seulement si le parsing modèle dérive en
  pratique.
- Pas de groupage `poids×reps×séries` : séries écrites explicitement.
- Pas d'import de fichier : le flux est copier-coller conversationnel, pas
  `import_activity_file`.
- Pas de douleur par exercice : une ligne globale suffit.
