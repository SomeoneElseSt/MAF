"""A Dates profile: its questions, and the one way its answers become a post and back.

A profile is a normal post. Its text is plain lines, one per question ("From: Europe"), then the optional comment;
its title is "<Rotation city>: <gender>, <from>, <height in cm>, into <interested in>". Only these answers can be set or changed, so a
profile always reads the same way.
"""

import re

# The questions, in order: (field, label in the profile's text, choices).
QUESTIONS = [
    ("region", "From", ["Africa", "East Asia", "Europe", "Latin America", "Middle East", "Mixed", "North America",
                        "Oceania", "South Asia"]),
    ("gender", "Gender", ["Man", "Woman", "Non-binary"]),
    ("interested_in", "Interested in", ["Men", "Women", "Everyone"]),
    ("height", "Height", ["Under 5′3″ (160 cm)", "5′3″–5′9″ (160–175 cm)", "Over 5′9″ (175 cm)"]),
    ("city", "Rotation city", ["Berlin", "Buenos Aires", "San Francisco", "Tokyo"]),
    ("looking_for", "Looking for", ["Friend", "Relationship", "Either, depending on how it goes"]),
]
CHOICES = {field: choices for field, _, choices in QUESTIONS}
LABEL = {field: label for field, label, _ in QUESTIONS}


def missing(values: dict) -> dict[str, str]:
    """The questions left unanswered (or answered with something not offered), as {field: message}."""
    return {field: "Pick one." for field, _, choices in QUESTIONS if values.get(field) not in choices}


def text_of(values: dict) -> str:
    lines = "\n".join(f"{LABEL[field]}: {values[field]}" for field, _, _ in QUESTIONS)
    comment = (values.get("comment") or "").strip()
    return f"{lines}\n\n{comment}" if comment else lines


def title_of(values: dict) -> str:
    """e.g. "Berlin: Woman, Europe, 160–175 cm, into men"; the height's range in cm, with under/over lowercase."""
    cm = re.search(r"\((.*)\)", values["height"]).group(1)
    height = f"under {cm}" if values["height"].startswith("Under") else f"over {cm}" if values["height"].startswith("Over") else cm
    interest = f", into {values['interested_in'].lower()}" if values.get("interested_in") else ""
    return f"{values['city']}: {values['gender']}, {values['region']}, {height}{interest}"


def values_of(text: str | None) -> dict:
    """A profile's answers read back from its text, to fill the form when editing it."""
    lines, _, comment = (text or "").partition("\n\n")
    by_label = dict(line.split(": ", 1) for line in lines.splitlines() if ": " in line)
    values = {field: by_label.get(label, "") for field, label, _ in QUESTIONS}
    values["comment"] = comment
    return values
