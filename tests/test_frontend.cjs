/* Run with Node >=18 and jsdom@22.1.0 installed.
   This verifies DOM behaviour and portable template contracts, not Qt audio
   playback or Anki scheduling. A live Anki smoke test is still required. */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const childProcess = require("node:child_process");
const {JSDOM, VirtualConsole} = require("jsdom");

const repo = path.resolve(__dirname, "..");
const pack = JSON.parse(fs.readFileSync(path.join(repo, "addon/data/tester.json"), "utf8"));
const python = process.env.PYTHON || "python";
const templates = JSON.parse(childProcess.execFileSync(python, ["-c", [
  "import importlib.util,json,pathlib",
  "p=pathlib.Path('addon/templates.py').resolve()",
  "s=importlib.util.spec_from_file_location('comuls_template_test',p)",
  "m=importlib.util.module_from_spec(s)",
  "s.loader.exec_module(m)",
  "print(json.dumps({'front':m.front_template(),'back':m.back_template(),'css':m.css()}))"
].join("\n")], {cwd: repo, encoding: "utf8"}));
const AUDIO_TYPES = new Set([
  "sound_discrimination", "connected_word_recognition", "sentence_reconstruction",
  "partial_dictation", "sentence_transcription", "audio_transcript_choice", "audio_meaning_choice"
]);
const STORE_KEY = "comuls-current-attempt-v1";
const context = {nonce: "frontend-test-review-1", card_id: 123};
let assertions = 0;

function check(condition, message) {
  assert.ok(condition, message); assertions += 1;
}
function same(actual, expected, message) {
  assert.deepEqual(actual, expected, message); assertions += 1;
}
function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function render(exercise, side) {
  const fields = {
    COMULS_ID: escapeHtml(exercise.id),
    Payload: escapeHtml(JSON.stringify(exercise)),
    Prompt: escapeHtml(exercise.prompt),
    Answer: escapeHtml(exercise.answer),
    AudioText: AUDIO_TYPES.has(exercise.type) ? escapeHtml(exercise.audio_text || "") : "",
    AudioFile: "",
    PersonalNotes: "",
    State: "{}"
  };
  function sections(source) {
    let previous;
    do {
      previous = source;
      source = source.replace(/\{\{([#^])(\w+)\}\}([\s\S]*?)\{\{\/\2\}\}/g,
        (_, mode, key, body) => ((mode === "#") === Boolean(fields[key])) ? sections(body) : "");
    } while (source !== previous);
    return source;
  }
  let html = sections(templates[side]);
  // Anki expands TTS to a native replay control; do not display its text on front.
  html = html.replace(/\{\{tts fr_FR:AudioText\}\}/g,
    fields.AudioText ? '<button class="replay-button" type="button">Replay audio</button>' : "");
  html = html.replace(/\{\{(\w+)\}\}/g, (_, key) => fields[key] || "");
  return "<!doctype html><html><head><style>" + templates.css +
    "</style></head><body class='card'>" + html + "</body></html>";
}
function openCard(exercise, side = "front", options = {}) {
  const messages = [], errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", error => errors.push(error.message));
  const dom = new JSDOM(render(exercise, side), {
    url: "https://comuls-card.test/", runScripts: "dangerously", virtualConsole: vc,
    beforeParse(window) {
      window.__attack = false;
      window.comulsContext = options.noContext ? undefined :
        {...context, exercise_id: exercise.id, ...(options.context || {})};
      window.pycmd = message => messages.push(message);
      if (options.stored) window.sessionStorage.setItem(STORE_KEY, options.stored);
    }
  });
  return {dom, window: dom.window, document: dom.window.document, messages, errors,
    close() { dom.window.close(); }};
}
function events(view, type) {
  return view.messages.filter(message => message.startsWith("comuls:"))
    .map(message => JSON.parse(message.slice(7))).filter(event => !type || event.event === type);
}
function getButton(view, text) {
  const button = [...view.document.querySelectorAll("button")].find(node => node.textContent === text);
  assert.ok(button, "Missing button: " + text);
  return button;
}
function visibleText(view) {
  function walk(node) {
    if (node.nodeType === 3) return node.textContent;
    if (node.nodeType !== 1) return "";
    if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(node.tagName)) return "";
    const style = view.window.getComputedStyle(node);
    if (node.hidden || style.display === "none" || style.visibility === "hidden") return "";
    return [...node.childNodes].map(walk).join(" ");
  }
  return walk(view.document.body).replace(/\s+/g, " ").trim();
}
function enterText(view, text, submit = true) {
  const input = view.document.querySelector(".comuls-answer-input");
  assert.ok(input, "Typed input exists");
  input.value = text;
  input.dispatchEvent(new view.window.Event("input", {bubbles: true}));
  if (submit) input.dispatchEvent(new view.window.KeyboardEvent("keydown", {
    key: "Enter", bubbles: true, cancelable: true
  }));
}
function stored(view) { return view.window.sessionStorage.getItem(STORE_KEY); }
function assertNoGrade(view, label) {
  check(!view.messages.some(message => /^ease/.test(message)), label + ": never grades through native bridge");
}
function completeCorrectly(view, exercise) {
  const api = view.window.COMULSCard, shell = api.shellFor(exercise);
  if (shell === "typed") {
    let escapedKey = false;
    view.document.addEventListener("keydown", () => { escapedKey = true; });
    enterText(view, exercise.answer);
    check(!escapedKey, exercise.id + ": typed Enter is isolated from native shortcuts");
  } else if (shell === "choice") {
    const correct = exercise.choices.find(choice => choice.correct === true);
    assert.ok(correct, exercise.id + ": one correct choice exists");
    const button = [...view.document.querySelectorAll("[data-choice-id]")]
      .find(node => node.getAttribute("data-choice-id") === String(correct.id));
    button.click();
    same(events(view, "attempt").length, 0, exercise.id + ": selecting an option does not reveal");
    getButton(view, "Check answer").click();
    same(events(view, "attempt")[0].response, String(correct.id), exercise.id + ": choice submits stable ID");
  } else if (shell === "tiles") {
    for (const token of api.tokensFor(exercise)) {
      const button = [...view.document.querySelectorAll(".comuls-tile-bank button")]
        .find(node => !node.disabled && node.textContent === token.text);
      assert.ok(button, exercise.id + ": every reconstruction token is available");
      button.click();
    }
    getButton(view, "Check answer").click();
    same(events(view, "attempt")[0].selected_ids.length, api.tokensFor(exercise).length,
      exercise.id + ": tile IDs are captured");
  } else {
    getButton(view, "Show answer").click();
  }
  same(view.messages.filter(message => message === "ans").length, 1, exercise.id + ": exactly one native reveal");
  assertNoGrade(view, exercise.id);
  return shell;
}

check(pack.exercises.length >= 90, "Canonical tester has at least 90 authored exercises");
same(new Set(pack.exercises.map(exercise => exercise.type)).size, 13, "All 13 exercise types are represented");
for (const exercise of pack.exercises) {
  const front = openCard(exercise);
  same(front.errors, [], exercise.id + ": front scripts execute without errors");
  check(front.document.querySelector(".comuls-card").getAttribute("data-comuls-mounted") === "true",
    exercise.id + ": enhanced shell mounts");
  check(front.document.querySelector(".comuls-reference") === null, exercise.id + ": no front reference answer");
  same(front.window.getComputedStyle(front.document.querySelector("#comuls-data")).display, "none",
    exercise.id + ": answer-bearing JSON remains hidden");
  for (const support of front.document.querySelectorAll(".comuls-support-content")) {
    same(front.window.getComputedStyle(support).display, "none", exercise.id + ": support begins hidden");
  }
  const shown = visibleText(front);
  if (exercise.explanation && !exercise.prompt.includes(exercise.explanation)) {
    check(!shown.includes(exercise.explanation.replace(/\s+/g, " ")), exercise.id + ": feedback explanation remains hidden");
  }
  if (exercise.type !== "sentence_reconstruction" && exercise.audio_text && !exercise.prompt.includes(exercise.audio_text) &&
      !(exercise.choices || []).some(choice => String(choice.text).includes(exercise.audio_text))) {
    check(!shown.includes(exercise.audio_text.replace(/\s+/g, " ")), exercise.id + ": transcript is not exposed");
  }
  const shell = completeCorrectly(front, exercise);
  const back = openCard(exercise, "back", {stored: stored(front)});
  same(back.errors, [], exercise.id + ": back scripts execute without errors");
  same(back.document.querySelector(".comuls-reference").textContent, exercise.answer,
    exercise.id + ": reference answer preserved");
  same(back.document.querySelector(".comuls-feedback").getAttribute("data-status"),
    shell === "reveal" ? "self_compare" : "correct", exercise.id + ": correct response feedback");
  same(events(back, "attempt").length, 1, exercise.id + ": answer side recovers attempt");
  assertNoGrade(back, exercise.id + " back");
  front.close(); back.close();
}

const typedExercise = pack.exercises.find(exercise => exercise.type === "french_form_recall");
{
  const front = openCard(typedExercise);
  enterText(front, typedExercise.answer, false);
  same(front.messages.length, 0, "Typing alone emits no reveal or grade");
  const back = openCard(typedExercise, "back", {stored: stored(front)});
  same(events(back, "attempt")[0].response, typedExercise.answer, "Native Show Answer recovers typed candidate");
  same(back.document.querySelector(".comuls-feedback").getAttribute("data-status"), "correct", "Recovered response evaluated");
  front.close(); back.close();
}
{
  const front = openCard(typedExercise);
  enterText(front, typedExercise.answer);
  getButton(front, "Check answer").click();
  same(front.messages.filter(message => message === "ans").length, 1, "Repeated Check cannot reveal or grade twice");
  front.close();
}
{
  const back = openCard(typedExercise, "back");
  same(back.errors, [], "Answer opens without a front-side attempt");
  same(back.document.querySelector(".comuls-feedback").getAttribute("data-status"), "self_compare",
    "Missing attempt never becomes an incorrect answer");
  same(events(back, "attempt").length, 0, "Missing attempt emits no invented response");
  back.close();
}
{
  const front = openCard(typedExercise);
  enterText(front, typedExercise.answer, false);
  const record = JSON.parse(stored(front));
  const wrongNonce = openCard(typedExercise, "back", {
    stored: JSON.stringify(record), context: {nonce: "different-review"}
  });
  same(events(wrongNonce, "attempt").length, 0, "Another review nonce cannot reuse an answer");
  record.created_at = Date.now() - 3 * 60 * 60 * 1000;
  const expired = openCard(typedExercise, "back", {stored: JSON.stringify(record)});
  same(events(expired, "attempt").length, 0, "Expired transient answers are ignored");
  record.created_at = Date.now(); record.exercise_id = "some-other-exercise";
  const otherExercise = openCard(typedExercise, "back", {stored: JSON.stringify(record)});
  same(events(otherExercise, "attempt").length, 0, "Another exercise cannot reuse an answer");
  front.close(); wrongNonce.close(); expired.close(); otherExercise.close();
}
{
  const exercise = pack.exercises.find(item => item.target_meaning && item.carrier_meaning && item.type !== "meaning_recall");
  const front = openCard(exercise);
  getButton(front, "Meaning support").click();
  same(events(front, "hint")[0].kind, "carrier", "Carrier help is recorded separately");
  getButton(front, "Answer hint").click();
  same(events(front, "hint")[1].reveals_target, true, "Target hint records answer exposure");
  getButton(front, "Answer hint").click();
  getButton(front, "Answer hint").click();
  same(events(front, "hint").length, 2, "Hint toggling does not duplicate first exposure");
  const back = openCard(exercise, "back", {stored: stored(front)});
  check(back.document.querySelector(".comuls-feedback").textContent.includes("Again is recommended"),
    "Target hint changes guidance while retaining native rating choice");
  assertNoGrade(back, "Hint guidance");
  front.close(); back.close();
}
{
  const exercise = pack.exercises.find(item => item.type === "sentence_transcription");
  const front = openCard(exercise);
  getButton(front, "Replay audio").click();
  same(events(front, "replay").length, 1, "Replay event captured without grading");
  check(!JSON.parse(stored(front)).target_hint, "Replay is not treated as target hint");
  const back = openCard(exercise, "back", {stored: stored(front)});
  const repair = getButton(back, "Hide text and listen again");
  repair.click();
  same(back.window.getComputedStyle(back.document.querySelector(".comuls-reference")).display, "none",
    "Auditory repair hides reference");
  check(!visibleText(back).includes(exercise.audio_text), "Auditory repair masks transcript");
  getButton(back, "Report this card").click();
  same(events(back, "report").length, 1, "Card report uses constrained bridge event");
  getButton(back, "Show text again").click();
  check(back.window.getComputedStyle(back.document.querySelector(".comuls-reference")).display !== "none",
    "Report does not strand a hidden answer");
  front.close(); back.close();
}
{
  const front = openCard(typedExercise, "front", {noContext: true});
  enterText(front, typedExercise.answer);
  same(front.messages, [], "Synced card without add-on does not send unsupported native commands");
  check(getButton(front, "Use Anki’s Show Answer").disabled, "Portable fallback explains native reveal");
  front.close();
}
{
  const hostile = {
    ...typedExercise, id: "hostile-payload",
    prompt: "<img src=x onerror='window.__attack=true'>",
    answer: "</div><script>window.__attack=true</script>&é",
    explanation: "<svg onload='window.__attack=true'>explanation</svg>",
    target_meaning: "<script>window.__attack=true</script>",
    carrier_meaning: "</div><img src=x onerror='window.__attack=true'>"
  };
  const front = openCard(hostile), back = openCard(hostile, "back");
  same(front.window.__attack, false, "Escaped JSON and prompt cannot execute markup");
  same(back.window.__attack, false, "Answer and explanation cannot execute markup");
  same(front.document.querySelectorAll("img, svg").length, 0, "Hostile text creates no front elements");
  same(back.document.querySelectorAll("img, svg").length, 0, "Hostile text creates no back elements");
  same(back.document.querySelector(".comuls-reference").textContent, hostile.answer, "Escaped answer remains readable text");
  same(JSON.parse(front.document.getElementById("comuls-data").textContent).answer, hostile.answer,
    "Payload round-trip preserves apostrophes, entities, accents and markup-like strings");
  same(front.errors, [], "Hostile input does not break front scripts");
  same(back.errors, [], "Hostile input does not break back scripts");
  front.close(); back.close();
}

// A translation can reveal the assessed meaning even when it is labelled carrier help.
{
  const exercise = {
    ...pack.exercises.find(item => item.type === "audio_meaning_choice"),
    id: "carrier-help-exposes-meaning", carrier_meaning: "The meaning being assessed.",
    carrier_help_reveals_target: true
  };
  const front = openCard(exercise);
  getButton(front, "Meaning support").click();
  const exposure = events(front, "hint")[0];
  same(exposure.kind, "target", "Meaning-revealing carrier support uses the target-exposure bridge path");
  same(exposure.reveals_target, true, "Meaning-revealing carrier support records target exposure");
  same(exposure.carrier_help, true, "Exposure still records that carrier support was used");
  const record = JSON.parse(stored(front));
  same(record.target_hint, true, "Meaning-revealing translation excludes independent retrieval evidence");
  same(record.carrier_help, true, "Meaning-revealing translation remains classified as support usage");
  const back = openCard(exercise, "back", {stored: stored(front)});
  check(back.document.querySelector(".comuls-feedback").textContent.includes("Again is recommended"),
    "Meaning-revealing translation recommends independent retrieval next time");
  assertNoGrade(back, "Meaning-revealing support");
  front.close(); back.close();
}

// Persist the core helper checks so CI protects normalization and stable IDs.
{
  const view = openCard(typedExercise), api = view.window.COMULSCard;
  same(api.normalize(" L ’ été ! "), "l'été", "Curly apostrophe and spacing normalization");
  same(api.normalize("va – t – il…"), "va-t-il", "Typographic dashes normalize");
  check(api.normalize("é") !== api.normalize("e"), "Accents remain assessed");
  same(api.normalize("Oui!", "punctuation"), "oui!", "Punctuation policy preserves final marks");
  same(api.evaluate({type: "grammar_cloze", answer: "est"}, ""), "self_compare", "Empty attempt is not failure");
  same(api.evaluate({type: "french_form_recall", answer: "le travail", accepted: ["travail"]}, "Travail."),
    "correct", "Accepted variants are allowed");
  same(api.evaluate({type: "audio_meaning_choice", choices: [{id: "a", correct: true}, {id: "b", correct: false}]}, "a"),
    "correct", "Choice uses ID");
  same(api.evaluate({type: "connected_word_recognition", choices: [{id: "word-a", text: "arrive", correct: true}, {id: "word-b", text: "arrivée", correct: false}]}, "word-a"),
    "correct", "Connected-word recognition uses stable choice ID");
  same(api.evaluate({type: "sound_discrimination", choices: [{id: "a", correct: true}, {id: "b", correct: false}]}, "b"),
    "incorrect", "Incorrect choice identified");
  same(api.evaluate({type: "sentence_transformation", answer: "Je partirai."}, "Je vais partir."),
    "self_compare", "Unlisted transformation is manually assessed");
  const repeated = {type: "sentence_reconstruction", answer: "le chat et le chien",
    tokens: [{id: "1", text: "le"}, {id: "2", text: "chat"}, {id: "3", text: "et"},
      {id: "4", text: "le"}, {id: "5", text: "chien"}]};
  same(api.evaluate(repeated, "le chat et le chien", ["4", "2", "3", "1", "5"]), "correct",
    "Identical tokens may exchange positions");
  same(api.evaluate(repeated, "le chat et le chien", ["1", "2", "3", "1", "5"]), "incorrect",
    "Duplicate token IDs cannot be reused");
  same(JSON.stringify(api.shuffled([1, 2, 3, 4], "seed")), JSON.stringify(api.shuffled([1, 2, 3, 4], "seed")),
    "Presentation shuffle is reproducible");
  view.close();
}
console.log("COMULS frontend: " + assertions + " assertions passed across " + pack.exercises.length +
  " cards / 13 exercise types. DOM contract only; live Anki playback remains a separate smoke test.");
