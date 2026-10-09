# Native Anki application verification

Run from the repository root after verifying media and building the installable add-on:

    xvfb-run -a -s "-screen 0 1440x1000x24" python tools/run_anki_e2e.py --addon dist/comuls-imperial-demo.ankiaddon

For a release, build with `python tools/build_addon.py --require-clean` and pass
`--expect-source "$(git rev-parse HEAD)"` to every native run. The archive embeds
source commit, clean/dirty status and individual packaged-source hashes. The
runner checks those hashes before installation and again inside Anki. Native
reports identify the exact installer SHA-256 and source tree.

The command uses official Anki 26.09.3 from the aqt package. Install Xvfb,
xauth, an X11 window manager such as Openbox, the Qt/XCB runtime libraries,
mpv, and PulseAudio. Start Openbox in the Xvfb display and provide a real or
null PulseAudio sink. Do not use Qt's offscreen platform: this verification
uses the application's actual QWebEngine renderer.

The harness creates disposable profiles with native ProfileManager, launches
aqt.run, installs the exact archive with AddonManager.install, restarts Anki
to load it normally, and drives actual Qt widgets and webview DOM events.
It does not replace mw, CollectionOp, Reviewer, the scheduler, the bridge,
or the AV player. The separate driver add-on is test infrastructure and is
never included in the released COMULS package.

B1 and B2 each cover all thirteen formats. Formats sharing a unit or an
exposure group are placed in different fresh profiles. Each profile admits
at most six new units and at most one above-entry-level preview. Consequently
the format sweep does not disable normal admission gates. The six-unit cap
is also exercised explicitly by attempting another admission.

Each student scenario verifies explicit level selection, settings, actual
bundled audio playback begin/end hooks and elapsed playback duration (a crashed
player ending immediately is rejected), supported familiarisation, native
admission, actual rendered front controls, answer submission through the
nonce bridge, answer exposure, native learner-selected Again/Hard/Good/Easy grading, native
revlog, Undo/Redo through Anki's menu actions, and a full shutdown/reopen.
The four-shell onboarding, content-manager pause/restore, an editorial JSON import and study-data export are driven through real file
choosers in the first profile. Native IDs, scheduler state and review history
are compared before/after import and application restart. Settings, fatigue and the unchanged native FSRS setting are also verified.
Both manual cohort changes are exercised after review. The first student profile
then undergoes another real AddonManager installation and application restart;
its imported content, settings and native history must survive. Pass
`--upgrade-addon dist/comuls-imperial-b2.ankiaddon` when testing the B1 installer
(and the reverse for B2) to verify replacement preserves the existing course.

Use --smoke --stages B1 (or B2) to verify a cohort installer's initial course suggestion and two native formats without repeating the entire sweep.

Artifacts under artifacts/anki-e2e contain JSON reports, subprocess logs,
and actual course/preparation/reviewer/file-chooser screenshots. Every
report distinguishes the automated UI checks from language-quality
assessment: a successful native player invocation cannot establish that a
recording has clear or correct French pronunciation.

The only fixtures are disposable native preferences/profiles and the
explicit editorial import JSON. No time travel, admission-policy overrides,
native scheduler mutation, or fake grading is used. Existing Python and DOM
tests remain responsible for additional deterministic policy edge cases.

Publication is gated twice: after verification and again in the release job.
`tools/build_addon.py --verify-release dist --source-commit <commit>` checks the
downloadable package bytes against clean-commit native evidence for the full
B1/B2 format sweep and each separate cohort installer. Smoke tests alone do not
satisfy that gate. CI uploads failure evidence but publishes installers only
after all required native, content, collection and card-interface checks pass.
