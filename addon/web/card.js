/* COMULS portable card controls. Native Anki remains the scheduler and grader. */
(function () {
  "use strict";
  var root = typeof window !== "undefined" ? window : globalThis;
  var TYPE_NAMES = {
    meaning_recall: "Meaning recall", french_form_recall: "French form",
    vocabulary_cloze: "Vocabulary gap", grammar_cloze: "Grammar gap",
    grammar_meaning_choice: "Grammar meaning", sentence_transformation: "Transform a sentence",
    sound_discrimination: "Hear the difference", connected_word_recognition: "Find the spoken word",
    sentence_reconstruction: "Build what you heard", partial_dictation: "Complete what you heard",
    sentence_transcription: "Write what you heard", audio_transcript_choice: "Choose what you heard",
    audio_meaning_choice: "Choose the meaning"
  };
  function normalize(value, policy) {
    var text = String(value == null ? "" : value).normalize("NFC").toLowerCase();
    text = text.replace(/\u00df/g, "ss").replace(/[\u2018\u2019\u02bc]/g, "'")
      .replace(/[\u2010\u2011\u2012\u2013\u2014\u2212]/g, "-")
      .replace(/[\u00a0\u202f]/g, " ").replace(/\s+/g, " ").trim()
      .replace(/\s*'\s*/g, "'").replace(/\s*-\s*/g, "-");
    if (policy !== "punctuation") text = text.replace(/[.!?\u2026]+$/g, "").trim();
    return text;
  }
  function shellFor(payload) {
    if (payload.type === "meaning_recall") return "reveal";
    if (payload.type === "sentence_reconstruction") return "tiles";
    if (Array.isArray(payload.choices) && payload.choices.length) return "choice";
    return "typed";
  }
  function tokensFor(payload) {
    if (Array.isArray(payload.tokens) && payload.tokens.length) {
      return payload.tokens.map(function (token) { return {id: String(token.id), text: String(token.text)}; });
    }
    return String(payload.answer || "").trim().split(/\s+/).filter(Boolean)
      .map(function (text, i) { return {id: "token-" + i, text: text}; });
  }
  function evaluate(payload, response, selectedIds) {
    var shell = shellFor(payload);
    if (shell === "reveal" || response == null || String(response).trim() === "") return "self_compare";
    if (shell === "choice") {
      var option = payload.choices.filter(function (item) { return String(item.id) === String(response); })[0];
      if (!option || !payload.choices.some(function (item) { return item.correct === true; })) return "self_compare";
      return option.correct === true ? "correct" : "incorrect";
    }
    if (shell === "tiles") {
      var tokens = tokensFor(payload);
      if (!Array.isArray(selectedIds) || selectedIds.length !== tokens.length) return "incorrect";
      var expected = tokens.map(function (token) { return token.id; }).sort();
      var actual = selectedIds.map(String).slice().sort();
      if (expected.some(function (id, i) { return id !== actual[i] || (i > 0 && actual[i] === actual[i - 1]); })) return "incorrect";
    }
    var policy = payload.answer_policy || payload.grading_policy || "strict";
    var answers = [payload.answer].concat(Array.isArray(payload.accepted) ? payload.accepted : []);
    var normalized = normalize(response, policy);
    if (answers.some(function (answer) { return answer != null && normalize(answer, policy) === normalized; })) return "correct";
    return payload.type === "sentence_transformation" ? "self_compare" : "incorrect";
  }
  function hash(text) {
    var value = 2166136261;
    for (var i = 0; i < text.length; i += 1) { value ^= text.charCodeAt(i); value = Math.imul(value, 16777619); }
    return value >>> 0;
  }
  function shuffled(items, seed) {
    var output = items.slice(), state = hash(String(seed));
    function random() {
      state += 0x6D2B79F5;
      var value = state;
      value = Math.imul(value ^ value >>> 15, value | 1);
      value ^= value + Math.imul(value ^ value >>> 7, value | 61);
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    }
    for (var i = output.length - 1; i > 0; i -= 1) {
      var j = Math.floor(random() * (i + 1)), temporary = output[i];
      output[i] = output[j]; output[j] = temporary;
    }
    return output;
  }
  root.COMULSCard = {normalize: normalize, shellFor: shellFor, tokensFor: tokensFor, evaluate: evaluate, shuffled: shuffled};
  if (typeof document === "undefined") return;
  var card = document.querySelector(".comuls-card"), data = document.getElementById("comuls-data");
  if (!card || !data || card.getAttribute("data-comuls-mounted") === "true") return;
  var payload;
  try { payload = JSON.parse(data.textContent); }
  catch (_) { return; } // Static Prompt/Answer remain useful if a payload is damaged.
  if (!payload || typeof payload.id !== "string" || !payload.id) return;
  card.setAttribute("data-comuls-mounted", "true");
  var mount = card.querySelector("[data-comuls-mount]");
  var fallback = card.querySelector("[data-comuls-fallback]");
  if (fallback) fallback.classList.add("comuls-hidden");
  var side = card.getAttribute("data-comuls-side");
  var typeBadge = card.querySelector("[data-comuls-type]");
  if (typeBadge) typeBadge.textContent = TYPE_NAMES[payload.type] || "Practice";
  var levelBadge = card.querySelector("[data-comuls-level]");
  if (levelBadge && payload.level) { levelBadge.textContent = String(payload.level); levelBadge.classList.remove("comuls-hidden"); }
  var KEY = "comuls-current-attempt-v1";
  var AGE = 2 * 60 * 60 * 1000;
  root.__COMULS_ATTEMPTS = root.__COMULS_ATTEMPTS || {};
  function context() { return root.comulsContext || {}; }
  function readAttempt() {
    var value;
    try { value = JSON.parse(root.sessionStorage.getItem(KEY) || "null"); } catch (_) { /* restricted webview */ }
    value = value || root.__COMULS_ATTEMPTS[KEY];
    if (!value || value.exercise_id !== payload.id || Date.now() - value.created_at > AGE || value.consumed) return null;
    if (context().nonce && value.context_nonce !== context().nonce) return null;
    return value;
  }
  function persist(value) {
    root.__COMULS_ATTEMPTS[KEY] = value;
    try { root.sessionStorage.setItem(KEY, JSON.stringify(value)); } catch (_) { /* in-memory fallback */ }
  }
  function emit(event, details) {
    var ctx = context();
    if (!ctx.nonce || typeof root.pycmd !== "function") return false;
    var message = {event: event, nonce: ctx.nonce, card_id: ctx.card_id, exercise_id: payload.id};
    Object.keys(details || {}).forEach(function (key) { message[key] = details[key]; });
    root.pycmd("comuls:" + JSON.stringify(message));
    return true;
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }
  function button(text, className, action) {
    var node = el("button", className, text);
    node.type = "button";
    node.addEventListener("click", function (event) { event.preventDefault(); event.stopPropagation(); action(); });
    node.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") event.stopPropagation();
    });
    return node;
  }
  function attemptDetails(state) {
    return {response: state.response, selected_ids: state.selected_ids || [], submitted: true,
      target_hint: !!state.target_hint, carrier_help: !!state.carrier_help,
      replays: state.replays || 0, presentation_seed: state.seed};
  }
  var state = side === "front" ? {
    created_at: Date.now(), exercise_id: payload.id, context_nonce: context().nonce || null,
    response: "", selected_ids: [], target_hint: false, carrier_help: false,
    replays: 0, submitted: false, seed: payload.id + ":" + Date.now() + ":" + Math.random()
  } : readAttempt();
  if (side === "front") persist(state);
  var audio = card.querySelector(".comuls-audio");
  if (audio) audio.addEventListener("click", function (event) {
    if (!event.target.closest("a, button, .replay-button")) return;
    if (side === "front" && state) { state.replays += 1; persist(state); }
    emit("replay", {side: side});
  });
  if (side === "back") {
    if (state) {
      // Also captures work when the student used Anki's native Show Answer.
      emit("attempt", attemptDetails(state));
      state.consumed = true; persist(state);
    }
    var result = state ? evaluate(payload, state.response, state.selected_ids) : "self_compare";
    var feedback = el("div", "comuls-feedback");
    feedback.setAttribute("role", "status");
    feedback.setAttribute("data-status", result);
    if (state && state.target_hint) {
      feedback.textContent = "Answer support was used. Again is recommended so you can retrieve it independently next time.";
    } else if (result === "correct") {
      feedback.textContent = "Matches an accepted answer. Choose how difficult it felt using Anki’s rating buttons.";
    } else if (result === "incorrect") {
      feedback.textContent = "Your response differs from the reference. Compare the difference; Again is recommended if you could not retrieve the answer.";
    } else if (payload.type === "sentence_transformation" && state && state.response) {
      feedback.textContent = "This wording needs your comparison. Another valid transformation may be possible; do not mark it wrong solely because the wording differs.";
    } else {
      feedback.textContent = "Compare your answer with the reference, then choose your Anki rating.";
    }
    mount.appendChild(feedback);
    if (state && state.response) {
      mount.appendChild(el("div", "comuls-reference-label", "Your answer"));
      var shown = state.response;
      if (shellFor(payload) === "choice") {
        var chosen = payload.choices.filter(function (option) { return String(option.id) === state.response; })[0];
        if (chosen) shown = chosen.text;
      }
      mount.appendChild(el("div", "comuls-response", shown));
    }
    var explanationMount = card.querySelector("[data-comuls-explanation]");
    if (explanationMount && payload.explanation) explanationMount.appendChild(el("div", "comuls-explanation", payload.explanation));
    if (explanationMount && /^audio_|dictation|transcription|reconstruction|connected_word|sound_discrimination/.test(payload.type) && payload.audio_text) {
      explanationMount.appendChild(el("div", "comuls-reference-label", "What you heard"));
      var transcript = el("div", "comuls-explanation", payload.audio_text); transcript.lang = "fr";
      explanationMount.appendChild(transcript);
      explanationMount.appendChild(el("div", "comuls-muted", "Repair: read the transcript, hide the text, then replay the complete phrase. Notice where the words join without adding pauses."));
    }
    var backActions = el("div", "comuls-actions");
    if (payload.audio_text) {
      var repairHidden = false;
      var repairButton = button("Hide text and listen again", "comuls-quiet", function () {
        repairHidden = !repairHidden;
        var repairNodes = card.querySelectorAll(".comuls-prompt, .comuls-reference-label, .comuls-reference, [data-comuls-explanation], .comuls-feedback, .comuls-response, .comuls-rating-guide");
        Array.prototype.forEach.call(repairNodes, function (node) { node.classList.toggle("comuls-hidden", repairHidden); });
        repairButton.textContent = repairHidden ? "Show text again" : "Hide text and listen again";
        repairButton.setAttribute("aria-pressed", repairHidden ? "true" : "false");
      });
      repairButton.setAttribute("aria-pressed", "false");
      backActions.appendChild(repairButton);
    }
    var reportButton = button("Report this card", "comuls-quiet", function () {
      reportButton.disabled = true;
      if (emit("report", {reason: "card_quality", side: "back"})) {
        mount.appendChild(el("div", "comuls-muted", "Flagged for review. You can also add details in COMULS → Feedback."));
      } else {
        mount.appendChild(el("div", "comuls-muted", "Use COMULS → Feedback on Anki Desktop and include this card ID: " + payload.id));
      }
    });
    backActions.appendChild(reportButton);
    mount.appendChild(backActions);
    return;
  }

  var shell = shellFor(payload), submitted = false;
  var instructions = {
    reveal: "Recall the meaning before showing the answer.",
    typed: "Answer from memory. You can replay audio as needed.",
    choice: "Choose one answer, then check it.",
    tiles: "Listen, then arrange the words. Tap a selected word to return it."
  };
  if (shell === "typed" && !payload.audio_text && !payload.audio_file) instructions.typed = "Answer from memory, then check it.";
  mount.appendChild(el("div", "comuls-instruction", instructions[shell]));
  var checkButton;
  function saveResponse(value, selectedIds) {
    state.response = String(value == null ? "" : value);
    if (selectedIds) state.selected_ids = selectedIds;
    persist(state);
  }
  function reveal() {
    if (submitted) return;
    submitted = true; state.submitted = true; persist(state);
    emit("attempt", attemptDetails(state));
    if (context().nonce && typeof root.pycmd === "function") {
      root.pycmd("ans");
    } else {
      // Synced mobile cards keep all controls, but the native Show Answer remains authoritative.
      checkButton.disabled = true;
      checkButton.textContent = "Use Anki’s Show Answer";
    }
  }
  if (shell === "typed") {
    var label = el("label", "comuls-field-label", "Your answer");
    label.htmlFor = "comuls-response";
    var input = el("textarea", "comuls-answer-input");
    input.id = "comuls-response"; input.rows = payload.type === "sentence_transcription" || payload.type === "sentence_transformation" ? 3 : 1;
    input.lang = "fr"; input.autocomplete = "off"; input.spellcheck = false; input.maxLength = 2000;
    input.setAttribute("autocapitalize", "none");
    input.setAttribute("autocorrect", "off");
    input.addEventListener("input", function () { saveResponse(input.value); });
    input.addEventListener("keydown", function (event) {
      event.stopPropagation();
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); reveal(); }
    });
    mount.appendChild(label); mount.appendChild(input);
  } else if (shell === "choice") {
    var list = el("div", "comuls-choice-list");
    list.setAttribute("role", "group"); list.setAttribute("aria-label", "Answer choices");
    shuffled(payload.choices, state.seed).forEach(function (choice) {
      var option = button(choice.text, "", function () {
        Array.prototype.forEach.call(list.children, function (item) { item.setAttribute("aria-pressed", "false"); });
        option.setAttribute("aria-pressed", "true"); saveResponse(String(choice.id), [String(choice.id)]);
      });
      option.setAttribute("aria-pressed", "false"); option.setAttribute("data-choice-id", String(choice.id));
      list.appendChild(option);
    });
    mount.appendChild(list);
  } else if (shell === "tiles") {
    var allTokens = tokensFor(payload), selected = [], bankOrder = shuffled(allTokens, state.seed);
    var area = el("div", "comuls-tile-area"); area.setAttribute("aria-label", "Your sentence"); area.setAttribute("aria-live", "polite");
    var bank = el("div", "comuls-tile-bank"); bank.setAttribute("aria-label", "Available words");
    function paintTiles() {
      area.replaceChildren(); bank.replaceChildren();
      if (!selected.length) area.appendChild(el("span", "comuls-tile-empty", "Your sentence appears here"));
      selected.forEach(function (token, index) {
        area.appendChild(button(token.text, "", function () { selected.splice(index, 1); paintTiles(); }));
      });
      bankOrder.forEach(function (token) {
        var used = selected.some(function (item) { return item.id === token.id; });
        var tile = button(token.text, "", function () { selected.push(token); paintTiles(); });
        tile.disabled = used; bank.appendChild(tile);
      });
      saveResponse(selected.map(function (token) { return token.text; }).join(" "), selected.map(function (token) { return token.id; }));
    }
    mount.appendChild(area); mount.appendChild(bank);
    var tileTools = el("div", "comuls-actions");
    tileTools.appendChild(button("Undo word", "comuls-quiet", function () { selected.pop(); paintTiles(); }));
    tileTools.appendChild(button("Clear", "comuls-quiet", function () { selected = []; paintTiles(); }));
    mount.appendChild(tileTools); paintTiles();
  }
  var actions = el("div", "comuls-actions");
  checkButton = button(shell === "reveal" ? "Show answer" : "Check answer", "comuls-primary", reveal);
  actions.appendChild(checkButton); mount.appendChild(actions);
  var support = el("div", "comuls-support");
  function addSupport(label, content, kind) {
    if (!content) return;
    var activated = false, supportText = el("div", "comuls-support-content comuls-hidden", content);
    var control = button(label, "comuls-quiet", function () {
      var opening = supportText.classList.contains("comuls-hidden");
      supportText.classList.toggle("comuls-hidden");
      control.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening && !activated) {
        activated = true;
        var revealsTarget = kind === "target" || (kind === "carrier" && payload.carrier_help_reveals_target === true);
        if (kind === "carrier") state.carrier_help = true;
        if (revealsTarget) state.target_hint = true;
        persist(state);
        emit("hint", {kind: revealsTarget ? "target" : "carrier", reveals_target: revealsTarget, carrier_help: kind === "carrier"});
      }
    });
    control.setAttribute("aria-expanded", "false");
    support.appendChild(control); mount.appendChild(supportText);
  }
  addSupport("Meaning support", payload.carrier_meaning, "carrier");
  addSupport("Answer hint", payload.target_meaning, "target");
  if (support.children.length) mount.appendChild(support);
  mount.appendChild(el("div", "comuls-muted", "No timer. Anki’s Show Answer and rating buttons always remain available."));
})();
