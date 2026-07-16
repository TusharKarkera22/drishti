// Kannada translations for the Agentic Data Intake / cleaning pipeline page.
// Keys are all prefixed `intake.`. English fallbacks live inline at each
// call site via t("intake.key", "English"), so a missing key safely renders
// English and the UI never breaks.
export const intakeKn: Record<string, string> = {
  // Shell title
  "intake.title": "ದತ್ತಾಂಶ ಸ್ವೀಕಾರ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "intake.pageIntro":
    "ಅಸ್ತವ್ಯಸ್ತ ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ ಮತ್ತು DRISHTI ಯ ಸ್ವಚ್ಛಗೊಳಿಸುವ ಏಜೆಂಟ್ ಸ್ವರೂಪಗಳನ್ನು ಸರಿಪಡಿಸುತ್ತದೆ, ನಕಲುಗಳನ್ನು ವಿಲೀನಗೊಳಿಸುತ್ತದೆ ಮತ್ತು ಕೆಟ್ಟ ಸಾಲುಗಳನ್ನು ನಿರ್ಬಂಧಿಸುತ್ತದೆ — ನಂತರ ಫಲಿತಾಂಶವನ್ನು ನಿಮ್ಮ ದತ್ತಾಂಶಕ್ಕೆ ಸೇರಿಸುತ್ತದೆ.",

  // ── STAGES ──────────────────────────────────────────────────────────────
  "intake.stage.profile": "ವಿವರ",
  "intake.stage.plan": "ಯೋಜನೆ",
  "intake.stage.execute": "ಕಾರ್ಯಗತ",
  "intake.stage.assess": "ಮೌಲ್ಯಮಾಪನ",
  "intake.stage.report": "ವರದಿ",

  "intake.stage.hint.profile": "ಕಾಲಂ ವಿಶ್ಲೇಷಣೆ",
  "intake.stage.hint.plan": "AI ಸರಿಪಡಿಸುವ ಯೋಜನೆ ರೂಪಿಸುತ್ತದೆ",
  "intake.stage.hint.execute": "ಸ್ವಚ್ಛಗೊಳಿಸುವ ಕ್ರಿಯೆಗಳು ನಡೆಯುತ್ತಿವೆ",
  "intake.stage.hint.assess": "AI ಪರಿಶೀಲಿಸುತ್ತದೆ",
  "intake.stage.hint.report": "ಲೆಕ್ಕಪರಿಶೋಧನೆ + ಸಾರಾಂಶ",

  // ── OP_META labels ───────────────────────────────────────────────────────
  "intake.op.normalize_dates": "ದಿನಾಂಕಗಳನ್ನು ಸಾಮಾನ್ಯಗೊಳಿಸಿ",
  "intake.op.normalize_phones": "ಫೋನ್ ಸಂಖ್ಯೆಗಳನ್ನು ಸಾಮಾನ್ಯಗೊಳಿಸಿ",
  "intake.op.normalize_money": "ಮೊತ್ತಗಳನ್ನು ಸಾಮಾನ್ಯಗೊಳಿಸಿ",
  "intake.op.standardize_values": "ಮೌಲ್ಯಗಳನ್ನು ಪ್ರಮಾಣೀಕರಿಸಿ",
  "intake.op.resolve_persons": "ಗುರುತುಗಳನ್ನು ಒಂದುಗೂಡಿಸಿ",
  "intake.op.handle_missing": "ಕಾಣೆಯಾದ ಮೌಲ್ಯ ನಿರ್ವಹಣೆ",
  "intake.op.dedupe_rows": "ನಕಲುಗಳನ್ನು ತೆಗೆದುಹಾಕಿ",

  // ── OP_META verbs ────────────────────────────────────────────────────────
  "intake.verb.normalize_dates": "ಪಾರ್ಸ್ ಮಾಡಲಾಯಿತು",
  "intake.verb.normalize_phones": "ಸರಿಪಡಿಸಲಾಯಿತು",
  "intake.verb.normalize_money": "ಪಾರ್ಸ್ ಮಾಡಲಾಯಿತು",
  "intake.verb.standardize_values": "ಪ್ರಮಾಣೀಕರಿಸಲಾಯಿತು",
  "intake.verb.resolve_persons": "ವಿಲೀನಗೊಳಿಸಲಾಯಿತು",
  "intake.verb.handle_missing": "ಗುರುತಿಸಲಾಯಿತು",
  "intake.verb.dedupe_rows": "ತೆಗೆದುಹಾಕಲಾಯಿತು",

  // ── Upload screen ────────────────────────────────────────────────────────
  "intake.heading": "ಏಜೆಂಟಿಕ್ ದತ್ತಾಂಶ ಸ್ವೀಕಾರ",
  "intake.intro":
    "ಕಚ್ಚಾ, ಅಸ್ತವ್ಯಸ್ತ CSV ಅಥವಾ Excel ಫೈಲ್ ಹಾಕಿ. AI ಏಜೆಂಟ್ ಅದನ್ನು ವಿಶ್ಲೇಷಿಸಿ, ಸ್ವಚ್ಛಗೊಳಿಸುವ ಯೋಜನೆ ರೂಪಿಸಿ, ನಿರ್ಣಾಯಕ ಕ್ರಿಯೆಗಳನ್ನು ನಡೆಸಿ, ತನ್ನ ಕೆಲಸವನ್ನು ತಾನೇ ಪರಿಶೀಲಿಸಿ ಸ್ವಯಂ ಸರಿಪಡಿಸಿಕೊಳ್ಳುತ್ತದೆ — ಪ್ರತಿ ಬದಲಾವಣೆ ಪರಿಶೀಲಿಸಬಹುದಾಗಿದ್ದು, ಯಾವುದನ್ನೂ ಮೌನವಾಗಿ ಅಳಿಸಲಾಗುವುದಿಲ್ಲ.",
  "intake.dropHint": "CSV / Excel ಎಳೆದು ಬಿಡಿ, ಅಥವಾ ಬ್ರೌಸ್ ಮಾಡಲು ಕ್ಲಿಕ್ ಮಾಡಿ",
  "intake.namePlaceholder": "ಸ್ವಚ್ಛ ದತ್ತಾಂಶದ ಹೆಸರು",
  "intake.cleanBtn": "ಎಐ ಮೂಲಕ ಸ್ವಚ್ಛಗೊಳಿಸಿ",
  "intake.pipelineWorks": "ಪೈಪ್‌ಲೈನ್ ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ",

  // ── Destination toggle (append to current dataset vs. new dataset) ──────
  "intake.destAppend": "ಸ್ವಚ್ಛಗೊಳಿಸಿದ ಸಾಲುಗಳನ್ನು ಪ್ರಸ್ತುತ ದತ್ತಾಂಶಕ್ಕೆ ಸೇರಿಸಿ",
  "intake.destNew": "ಹೊಸ ದತ್ತಾಂಶ ರಚಿಸಿ",

  // ── Running screen ───────────────────────────────────────────────────────
  "intake.newFile": "← ಹೊಸ ಫೈಲ್",
  "intake.pipelineComplete": "ಪೈಪ್‌ಲೈನ್ ಪೂರ್ಣ",
  "intake.starting": "ಪ್ರಾರಂಭವಾಗುತ್ತಿದೆ…",
  "intake.profiling": "ಕಾಲಂಗಳನ್ನು ವಿಶ್ಲೇಷಿಸಿ ಏಜೆಂಟ್‌ನಿಂದ ಸ್ವಚ್ಛಗೊಳಿಸುವ ಯೋಜನೆ ಕೋರಲಾಗುತ್ತಿದೆ…",

  // ── IterationCard ────────────────────────────────────────────────────────
  "intake.pass": "ಹಂತ",
  "intake.changes": "ಬದಲಾವಣೆಗಳು",
  "intake.quarantined": "ನಿರ್ಬಂಧಿತ",
  "intake.verdictDone": "AI ನಿರ್ಣಯ: ಸಾಕಷ್ಟು ಸ್ವಚ್ಛ — ಮುಗಿಯಿತು.",
  "intake.verdictCorrective": "AI ಉಳಿಕೆ ಸಮಸ್ಯೆಗಳನ್ನು ಕಂಡಿದೆ — ಸರಿಪಡಿಕೆ ಹಂತ ಸರದಿಯಲ್ಲಿದೆ.",
  "intake.assessing": "ಮೌಲ್ಯಮಾಪನ ನಡೆಯುತ್ತಿದೆ…",

  // ── Results / Cleaning Complete ──────────────────────────────────────────
  "intake.cleaningComplete": "ಸ್ವಚ್ಛಗೊಳಿಸುವಿಕೆ ಪೂರ್ಣ",
  "intake.statRowsIn": "ಒಳಗಿನ ಸಾಲುಗಳು",
  "intake.statRowsOut": "ಹೊರಗಿನ ಸಾಲುಗಳು",
  "intake.statDuplicates": "ತೆಗೆದ ನಕಲುಗಳು",
  "intake.statQuarantined": "ನಿರ್ಬಂಧಿತ",
  "intake.aiReport": "AI ಸ್ವಚ್ಛಗೊಳಿಸುವ ವರದಿ",
  "intake.openDashboard": "ಸ್ವಚ್ಛ ದತ್ತಾಂಶದ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್ ತೆರೆಯಿರಿ",

  // ── Append-to-existing-dataset result ────────────────────────────────────
  "intake.appendAdded": "ಸಾಲುಗಳನ್ನು ಸೇರಿಸಲಾಗಿದೆ",
  "intake.appendDuplicates": "ನಕಲುಗಳನ್ನು ಬಿಟ್ಟುಬಿಡಲಾಗಿದೆ",
  "intake.openData": "ದತ್ತಾಂಶ ತೆರೆಯಿರಿ",
};
