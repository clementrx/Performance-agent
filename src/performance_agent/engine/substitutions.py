"""Curated exercise-substitution table, keyed by movement pattern.

Each substitute lists the equipment it needs; substitute_exercise (in
engine/autoregulation.py) returns the ones the athlete can actually do. Bodyweight
options carry no equipment so they are always available as a last resort.

Every entry is labeled coaching judgment: these are standard same-pattern swaps a
coach makes at the rack, not a claim traceable to a single corpus study. Equipment
tokens are lowercase and matched case-insensitively against the profile equipment
list (barbell, rack, dumbbell, kettlebell, machine, cable, bench, pullup_bar,
bands, box); an empty tuple means bodyweight-only.
"""

from dataclasses import dataclass

SOURCE_LABEL = "coaching judgment"

# Movement patterns mirror SessionPlan.patterns (squat, hinge, push_h, push_v,
# pull_h, pull_v, lunge, carry, core, run, ride, swim).
MovementPattern = str


@dataclass(frozen=True)
class Substitute:
    """One alternative exercise for a movement pattern and its equipment need."""

    name: str
    equipment: tuple[str, ...]
    source: str = SOURCE_LABEL


_TABLE: dict[MovementPattern, tuple[Substitute, ...]] = {
    "squat": (
        Substitute("Back Squat", ("barbell", "rack")),
        Substitute("Front Squat", ("barbell", "rack")),
        Substitute("Goblet Squat", ("dumbbell",)),
        Substitute("Goblet Squat", ("kettlebell",)),
        Substitute("Leg Press", ("machine",)),
        Substitute("Bodyweight Squat", ()),
    ),
    "hinge": (
        Substitute("Conventional Deadlift", ("barbell",)),
        Substitute("Romanian Deadlift", ("barbell",)),
        Substitute("Dumbbell Romanian Deadlift", ("dumbbell",)),
        Substitute("Kettlebell Swing", ("kettlebell",)),
        Substitute("Back Extension", ("bench",)),
        Substitute("Single-Leg Hip Hinge", ()),
    ),
    "push_h": (
        Substitute("Barbell Bench Press", ("barbell", "bench")),
        Substitute("Dumbbell Bench Press", ("dumbbell", "bench")),
        Substitute("Machine Chest Press", ("machine",)),
        Substitute("Cable Press", ("cable",)),
        Substitute("Push-Up", ()),
    ),
    "push_v": (
        Substitute("Overhead Press", ("barbell",)),
        Substitute("Dumbbell Shoulder Press", ("dumbbell",)),
        Substitute("Machine Shoulder Press", ("machine",)),
        Substitute("Pike Push-Up", ()),
    ),
    "pull_h": (
        Substitute("Barbell Row", ("barbell",)),
        Substitute("Dumbbell Row", ("dumbbell",)),
        Substitute("Seated Cable Row", ("cable",)),
        Substitute("Machine Row", ("machine",)),
        Substitute("Inverted Row", ("bench",)),
    ),
    "pull_v": (
        Substitute("Pull-Up", ("pullup_bar",)),
        Substitute("Lat Pulldown", ("cable",)),
        Substitute("Machine Pulldown", ("machine",)),
        Substitute("Band Pulldown", ("bands",)),
    ),
    "lunge": (
        Substitute("Barbell Lunge", ("barbell",)),
        Substitute("Dumbbell Walking Lunge", ("dumbbell",)),
        Substitute("Bulgarian Split Squat", ("dumbbell", "bench")),
        Substitute("Bodyweight Split Squat", ()),
    ),
    "carry": (
        Substitute("Farmer Carry", ("dumbbell",)),
        Substitute("Kettlebell Carry", ("kettlebell",)),
        Substitute("Suitcase Carry", ("dumbbell",)),
    ),
    "core": (
        Substitute("Cable Pallof Press", ("cable",)),
        Substitute("Hanging Leg Raise", ("pullup_bar",)),
        Substitute("Plank", ()),
        Substitute("Dead Bug", ()),
    ),
    "run": (
        Substitute("Outdoor Run", ()),
        Substitute("Treadmill Run", ("machine",)),
        Substitute("Row Erg", ("machine",)),
    ),
    "ride": (
        Substitute("Outdoor Ride", ("bike",)),
        Substitute("Indoor Trainer", ("bike",)),
        Substitute("Air Bike", ("machine",)),
    ),
    "swim": (
        Substitute("Pool Swim", ("pool",)),
        Substitute("Dry-Land Pull Circuit", ("bands",)),
    ),
}


def substitutes_for(pattern: MovementPattern) -> tuple[Substitute, ...]:
    """Return the full substitute list for a movement pattern (raises if unknown)."""
    if pattern not in _TABLE:
        msg = f"unknown movement pattern {pattern!r}; known patterns: {sorted(_TABLE)}"
        raise ValueError(msg)
    return _TABLE[pattern]
