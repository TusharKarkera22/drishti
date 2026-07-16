// Kannada translations for the DATA page (composition, history, append
// drop-zone). Keys are all prefixed `data.`. English fallbacks live inline at
// each call site via t("data.key", "English"), so a missing key safely
// renders English and the UI never breaks.
export const dataKn: Record<string, string> = {
  "data.title": "ದತ್ತಾಂಶ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "data.intro":
    "ಈ ದತ್ತಾಂಶ ಒಳಗೊಂಡಿರುವ ಎಲ್ಲವೂ — ಫೈಲ್‌ಗಳು, ಕೋಷ್ಟಕಗಳು ಮತ್ತು ದಾಖಲೆಗಳು. ದತ್ತಾಂಶ ಸೇರಿಸಲು ಹೊಸ Excel/CSV ಫೈಲ್‌ಗಳನ್ನು ಇಲ್ಲಿ ಹಾಕಿ; ನಕಲುಗಳನ್ನು ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಬಿಟ್ಟುಬಿಡಲಾಗುತ್ತದೆ.",

  // ── Summary strip ────────────────────────────────────────────────────────
  "data.totalRecords": "ಒಟ್ಟು ದಾಖಲೆಗಳು",
  "data.tableCount": "ಕೋಷ್ಟಕಗಳು",
  "data.created": "ರಚಿಸಲಾಗಿದೆ",
  "data.updated": "ಕೊನೆಯ ನವೀಕರಣ",

  // ── Table cards ──────────────────────────────────────────────────────────
  "data.tablesHeading": "ಕೋಷ್ಟಕಗಳು",
  "data.columns": "ಕಾಲಂಗಳು",

  // ── Badges ───────────────────────────────────────────────────────────────
  "data.seedBadge": "ಸೀಡ್",
  "data.uploadBadge": "ಅಪ್‌ಲೋಡ್",

  // ── Read-only note (seed datasets) ───────────────────────────────────────
  "data.readonly": "ಪ್ರಾತ್ಯಕ್ಷಿಕೆ ದತ್ತಾಂಶ — ಓದಲು ಮಾತ್ರ",

  // ── Add data drop-zone ───────────────────────────────────────────────────
  "data.addDataHeading": "ದತ್ತಾಂಶ ಸೇರಿಸಿ",
  "data.addDataCta": "ಸೇರಿಸಲು CSV / Excel ಎಳೆದು ಬಿಡಿ",
  "data.addDataHint": "ಹೊಂದಾಣಿಕೆಯ ಕಾಲಂಗಳು ವಿಲೀನಗೊಳ್ಳುತ್ತವೆ — ಹೊಸ ಫೈಲ್‌ಗಳು ಹೊಸ ಕೋಷ್ಟಕಗಳನ್ನೂ ಸೇರಿಸಬಹುದು",
  "data.appending": "ಸಾಲುಗಳನ್ನು ಸೇರಿಸಲಾಗುತ್ತಿದೆ…",

  // ── Append results ───────────────────────────────────────────────────────
  "data.appendSuccess": "ದತ್ತಾಂಶ ಸೇರಿಸಲಾಗಿದೆ",
  "data.rowsTo": "ಸಾಲುಗಳನ್ನು ಇಲ್ಲಿಗೆ ಸೇರಿಸಲಾಗಿದೆ",
  "data.newTable": "ಹೊಸ ಕೋಷ್ಟಕ",
  "data.duplicatesSkipped": "ನಕಲುಗಳನ್ನು ಬಿಟ್ಟುಬಿಡಲಾಗಿದೆ",
  "data.extrasIgnored": "ಹೆಚ್ಚುವರಿ ಕಾಲಂಗಳನ್ನು ನಿರ್ಲಕ್ಷಿಸಲಾಗಿದೆ",
  "data.insightsRefresh": "ಒಳನೋಟಗಳು ಪುನಶ್ಚೇತನಗೊಳ್ಳುತ್ತವೆ",

  // ── History ──────────────────────────────────────────────────────────────
  "data.historyHeading": "ಇತಿಹಾಸ",

  // ── Empty / loading / error states ───────────────────────────────────────
  "data.noDataset": "ದತ್ತಾಂಶ ಆಯ್ಕೆ ಮಾಡಿಲ್ಲ — ಮುಖಪುಟದಿಂದ ಒಂದನ್ನು ಆರಿಸಿ.",
  "data.goHome": "ಮುಖಪುಟಕ್ಕೆ ಹೋಗಿ",
  "data.loading": "ದತ್ತಾಂಶ ಸಂಯೋಜನೆ ಲೋಡ್ ಆಗುತ್ತಿದೆ…",
};
