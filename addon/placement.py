"""Optional ungraded domain sampling, separate from Anki scheduling."""
from __future__ import annotations
import json
import time
from pathlib import Path
from aqt.qt import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLabel,
    QPushButton, QLineEdit, QCheckBox, QTextBrowser, QMessageBox, Qt)
from .core import CHOICE_TYPES, evaluate_answer
from .course import route_candidates

DOMAINS = {
    "Meaning": ("meaning_recall",),
    "Written form": ("french_form_recall", "vocabulary_cloze"),
    "Grammar interpretation": ("grammar_meaning_choice",),
    "Grammar production": ("grammar_cloze", "sentence_transformation"),
    "Sound contrasts": ("sound_discrimination",),
    "Word boundaries": ("connected_word_recognition", "sentence_reconstruction", "partial_dictation", "sentence_transcription"),
    "Sentence comprehension": ("audio_meaning_choice", "audio_transcript_choice"),
}


def recommend(correct, total, stage):
    if total < 4:
        return {"action": "insufficient", "stage": stage}
    if correct >= 3:
        return {"action": "higher", "stage": "B2" if stage == "B1" else "B2"}
    if correct <= 1:
        return {"action": "lower", "stage": "B1"}
    return {"action": "more", "stage": stage}


def open_diagnostic(controller):
    from .ui import label, button
    from .collection import record_reference_exposure
    from aqt import mw
    dialog = QDialog(controller.window or mw)
    dialog.setWindowTitle("COMULS optional domain check")
    dialog.resize(680, 590)
    layout = QVBoxLayout(dialog)
    layout.addWidget(label("An ungraded sample, not a CEFR examination. It changes no schedules and declares no words known. "
        "Your course remains the one you selected. Recall and alternative transformations use honest self-comparison."))
    selector = QComboBox(); selector.addItems(list(DOMAINS)); layout.addWidget(selector)
    stage = controller.state()["stage"]
    results = []
    used = set()
    round_scores = []
    current = {}
    status = label(""); layout.addWidget(status)
    card = QVBoxLayout(); layout.addLayout(card)
    footer = label(""); layout.addWidget(footer)
    def clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                clear_layout(item.layout())
    def clear():
        clear_layout(card)
    def finish(reason):
        clear()
        completed = [r for r in results if r["correct"] is not None]
        correct = sum(r["correct"] for r in completed)
        output = {"schema_version": 1, "time": time.time(), "domain": selector.currentText(),
            "selected_course": controller.state()["stage"], "sample": results,
            "completed": len(completed), "correct": correct, "suggestion": reason,
            "validated_cefr_test": False}
        target = controller.local.root / "domain-check.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        status.setText("Domain sample complete")
        card.addWidget(label(f"{correct} of {len(completed)} completed items retrieved; "
            f"{len(results) - len(completed)} unassessed.\n\n{reason}\n\n"
            "This small sample has substantial uncertainty. Immediate feedback affects later attempts. "
            "It is a suggestion only; native scheduled reviews provide longer-term evidence."))
        footer.setText("Saved locally. No level, admission or review history was changed.")
    def next_item():
        nonlocal stage, round_scores
        if len(results) >= 12:
            finish("Maximum twelve presented items reached. Discuss mixed results with your teacher.")
            return
        if len(round_scores) == 4:
            suggestion = recommend(sum(round_scores), 4, stage)
            round_scores = []
            next_stage = suggestion["stage"]
            if suggestion["action"] in ("higher", "lower") and next_stage == stage:
                finish("This sample reached the available course boundary. "
                    + ("The sampled facet may support harder work." if suggestion["action"] == "higher"
                       else "Use lower-level repair for this facet."))
                return
            stage = next_stage
        kinds = DOMAINS[selector.currentText()]
        candidates = [e for e in route_candidates(controller.catalog, stage)
            if e["type"] in kinds and e["id"] not in used]
        if not candidates:
            finish("No further independent items are available for this domain and course.")
            return
        exercise = sorted(candidates, key=lambda e: (len([r for r in results if r["type"] == e["type"]]), e["id"]))[0]
        used.add(exercise["id"])
        current.clear(); current.update(exercise=exercise, response=None, revealed=False)
        clear()
        status.setText(f"{selector.currentText()} · {stage} route · item {len(results) + 1}/12")
        card.addWidget(label(exercise["prompt"]))
        if exercise.get("audio_file") or exercise.get("audio_text"):
            button("Play recording", lambda: controller.play_exercise(exercise), card)
        if exercise["type"] in CHOICE_TYPES:
            buttons = []
            def choose(identity):
                current["response"] = identity
                for widget in buttons:
                    widget.setChecked(widget.property("choice_id") == identity)
            for choice in exercise["choices"]:
                widget = button(choice["text"], lambda identity=choice["id"]: choose(identity), card)
                widget.setCheckable(True); widget.setProperty("choice_id", choice["id"]); buttons.append(widget)
        elif exercise["type"] == "sentence_reconstruction":
            sequence = []; output = label(""); card.addWidget(output)
            row = QHBoxLayout(); card.addLayout(row)
            def append(token, widget):
                sequence.append(token["id"]); widget.setEnabled(False)
                current["response"] = list(sequence)
                words = {t["id"]: t["text"] for t in exercise["tokens"]}
                output.setText(" ".join(words[i] for i in sequence))
            for token in reversed(exercise["tokens"]):
                widget = QPushButton(token["text"]); row.addWidget(widget)
                widget.clicked.connect(lambda _checked=False, t=token, w=widget: append(t, w))
        elif exercise["type"] != "meaning_recall":
            field = QLineEdit(); field.setMaxLength(500); card.addWidget(field)
            field.textChanged.connect(lambda text: current.update(response=text))
        feedback = label(""); card.addWidget(feedback)
        reveal = button("Reveal and compare", lambda: reveal_answer(feedback), card)
        actions = QHBoxLayout(); card.addLayout(actions)
        known = button("Retrieved", lambda: complete(True), actions)
        missed = button("Not retrieved", lambda: complete(False), actions)
        known.setEnabled(False); missed.setEnabled(False)
        current["ratings"] = (known, missed)
        button("Cannot assess / audio problem", lambda: complete(None), card)
    def reveal_answer(feedback):
        if current.get("revealed"):
            return
        exercise = current["exercise"]
        current["revealed"] = True
        record_reference_exposure(mw.col, exercise["id"], time.time())
        verdict = evaluate_answer(exercise, current.get("response"))
        current["verdict"] = verdict["status"]
        feedback.setText("Reference: " + exercise["answer"] + "\n" + exercise.get("explanation", "")
            + "\n" + {"correct": "Your captured answer matches.", "incorrect": "Your captured answer differs.",
                "self_compare": "Compare honestly: was the target retrieved?"}.get(verdict["status"], "Compare your answer."))
        known, missed = current["ratings"]
        known.setEnabled(verdict["status"] != "incorrect"); missed.setEnabled(True)
    def complete(correct):
        from aqt.sound import av_player
        av_player.stop_and_clear_queue()
        if correct is not None and not current.get("revealed"):
            return
        exercise = current["exercise"]
        results.append({"exercise_id": exercise["id"], "type": exercise["type"], "route": stage,
            "correct": correct, "self_compared": current.get("verdict") == "self_compare"})
        if correct is not None:
            round_scores.append(int(correct))
        next_item()
    def start():
        if any(k in ("Sound contrasts", "Word boundaries", "Sentence comprehension") for k in [selector.currentText()]):
            if not controller.state().get("audio_confirmed") or not controller.media_ready:
                QMessageBox.information(dialog, "Check audio first", "Complete the French audio check before this listening sample.")
                return
        selector.setEnabled(False); start_button.setEnabled(False); next_item()
    start_button = button("Start four-item sample", start, layout)
    button("Close", dialog.reject, layout)
    dialog.exec()
    from aqt.sound import av_player
    av_player.stop_and_clear_queue()
