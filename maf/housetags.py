"""House tags: tags with their own templates, etiquette and styling.

Everything about a house tag lives in HOUSE_TAGS, so adding one needs no code
changes elsewhere. Topic tags such as #minerva have no entry and behave as plain
tags.
"""

HOUSE_TAGS: dict[str, dict] = {
    "hottakes": {
        "submit_template": [
            "- My take in one sentence",
            "- Why I think this, with one experience or piece of evidence",
            "- The strongest argument against my take, as I understand it",
            "- What could change my mind, and whether I want debate, advice, or just listening",
        ],
        "reply_placeholder": [
            "- Which part of the take you're responding to",
            "- Your reason, or an experience that backs it up",
            "- What would change your mind",
        ],
        "etiquette": (
            "argue with the take, not the person. Push back as hard as you like, "
            "assume the poster means it in good faith, and say what would change your mind."
        ),
        "highlight": True,
    },
    "help": {
        "submit_template": [
            "- What I need help with",
            "- What I've already tried",
            "- My situation: city, deadline, anything that narrows it down",
            "- What kind of answer would help most",
        ],
        "reply_placeholder": [
            "- What worked for you, or who to ask",
            "- How sure I am and how recent my experience is",
        ],
        "etiquette": None,
        "highlight": False,
    },
    "wondering": {
        "submit_template": [
            "- My question",
            "- Why I'm curious",
            "- My best guess so far",
        ],
        "reply_placeholder": [
            "- My answer or a guess",
            "- What it's based on",
        ],
        "etiquette": None,
        "highlight": False,
    },
    "confession": {
        "submit_template": [
            "- What happened, or what I'm feeling",
            "- How I feel about it now",
            "- What I'd like back: to be heard, advice, or company",
            "- Leave out details that could identify me or anyone else.",
        ],
        "reply_placeholder": [
            "- Respond to the person, not the verdict",
            "- Share something similar if I have it",
        ],
        "etiquette": (
            "respond to the person, not the verdict. Be kind, and don't guess who wrote it "
            "or who it's about."
        ),
        "highlight": False,
    },
}

# Lead with common tags, then retain the remaining house tags in alphabetical order.
_PRIORITY_TAGS = ("hottakes", "confessions", "minerva")
SUGGESTED_TAGS = [*_PRIORITY_TAGS, *(tag for tag in sorted(HOUSE_TAGS) if tag not in _PRIORITY_TAGS)]

DEFAULT_SUBMIT_TEMPLATE = [
    "- What it's about",
    "- Your claim or question",
    "- What kind of conversation you'd like: debate, advice, or just sharing",
]

EXAMPLE_POST = (
    "Every rotation I spend the first few weeks feeling lost. Curious which routines, "
    "apps or places made the move easier for you."
)


def house_tag(tags: list[str]) -> tuple[str, dict] | None:
    """The first house tag among `tags`, in the order given."""
    for tag in tags:
        entry = HOUSE_TAGS.get(tag)
        if entry:
            return tag, entry
    return None


def submit_placeholder(tags: list[str]) -> str:
    """The Text box hint: a house tag's outline, else the default one, else an example."""
    found = house_tag(tags)
    if found:
        return "\n".join(found[1]["submit_template"])
    if tags:
        return "\n".join(DEFAULT_SUBMIT_TEMPLATE)
    return EXAMPLE_POST


def reply_placeholder(tags: list[str]) -> str:
    found = house_tag(tags)
    if not found:
        return "Write a reply"
    lines = found[1]["reply_placeholder"]
    return "Write a reply. Ideally:\n" + "\n".join(lines)


def etiquette(tags: list[str]) -> tuple[str, str] | None:
    """(tag, etiquette text) for the thread banner, if the first house tag has one."""
    found = house_tag(tags)
    if not found or not found[1]["etiquette"]:
        return None
    return found[0], found[1]["etiquette"]


def is_hot(tags: list[str]) -> bool:
    return any(HOUSE_TAGS.get(t, {}).get("highlight") for t in tags)
