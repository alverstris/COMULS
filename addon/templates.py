"""Portable COMULS note templates.

Payload must be json.dumps(exercise, ensure_ascii=False), then html.escape(...).
Only the visible Prompt/Answer/PersonalNotes fields may contain intentional HTML.
Inline assets make cards remain readable after syncing without this add-on.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent

_AUDIO = """<div class="comuls-audio">
{{#AudioFile}}{{AudioFile}}{{/AudioFile}}
{{^AudioFile}}{{#AudioText}}{{tts fr_FR:AudioText}}{{/AudioText}}{{/AudioFile}}
</div>"""

_HEADER = """<header class="comuls-header">
<span class="comuls-brand">COMULS</span>
<span class="comuls-badge" data-comuls-type>Practice</span>
<span class="comuls-badge comuls-hidden" data-comuls-level></span>
</header>"""

_NOTES = """{{#PersonalNotes}}<details class="comuls-personal">
<summary>My notes</summary><div>{{PersonalNotes}}</div>
</details>{{/PersonalNotes}}"""

def _script() -> str:
    # The source is trusted packaged code. Do not interpolate student data here.
    source = (_ROOT / "web" / "card.js").read_text(encoding="utf-8")
    return "<script>" + source.replace("</script", "<\\/script") + "</script>"

def front_template() -> str:
    return (
        '<main class="comuls-card" data-comuls-side="front">'
        + _HEADER
        + '<div class="comuls-prompt">{{Prompt}}</div>'
        + _AUDIO
        + '<div class="comuls-data" id="comuls-data" aria-hidden="true">{{Payload}}</div>'
        + '<div class="comuls-data" aria-hidden="true">{{MediaRefs}}</div>'
        + '<div data-comuls-mount></div>'
        + '<div class="comuls-muted" data-comuls-fallback>Think of your answer, then use Anki’s Show Answer.</div>'
        + _NOTES + "</main>" + _script()
    )

def back_template() -> str:
    # Intentionally does not use FrontSide: no duplicate handlers, no front required.
    return (
        '<main class="comuls-card" data-comuls-side="back">'
        + _HEADER
        + '<div class="comuls-prompt">{{Prompt}}</div>'
        + _AUDIO
        + '<div class="comuls-data" id="comuls-data" aria-hidden="true">{{Payload}}</div>'
        + '<div class="comuls-data" aria-hidden="true">{{MediaRefs}}</div>'
        + '<div data-comuls-mount></div>'
        + '<div class="comuls-reference-label">Reference answer</div>'
        + '<div class="comuls-reference" lang="fr">{{Answer}}</div>'
        + '<div data-comuls-explanation></div>'
        + '<div class="comuls-rating-guide">Choose your Anki rating: Again if you could not retrieve the answer; Hard if correct with difficulty; Good if correct normally; Easy if correct immediately. Replaying audio alone does not mean Again.</div>'
        + _NOTES + "</main>" + _script()
    )

def css() -> str:
    return (_ROOT / "web" / "card.css").read_text(encoding="utf-8")
