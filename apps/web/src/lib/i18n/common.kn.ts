// Shared strings used across multiple surfaces: the Freshness chip
// (common.*) and the first-visit guided Tour (tour.*). Keys are prefixed
// accordingly. English fallbacks live inline at each call site via
// t("key", "English"), so a missing key safely renders English.
export const commonKn: Record<string, string> = {
  // ── Freshness chip ───────────────────────────────────────────────────────
  "common.computed": "ಲೆಕ್ಕಹಾಕಲಾಗಿದೆ",
  "common.cached": "ಕ್ಯಾಶ್ ಮಾಡಲಾಗಿದೆ",
  "common.refresh": "ಪುನಶ್ಚೇತನಗೊಳಿಸಿ",
  "common.dismiss": "ವಜಾಗೊಳಿಸಿ",

  // ── EmptyState (generic "open a dataset" panel) ──────────────────────────
  "common.noDatasetTitle": "ಯಾವುದೇ ದತ್ತಾಂಶ ತೆರೆದಿಲ್ಲ",
  "common.goHome": "ಪ್ರಾರಂಭಿಸಲು ಮುಖಪುಟದಿಂದ ದತ್ತಾಂಶ ತೆರೆಯಿರಿ",

  // ── Shell header buttons ─────────────────────────────────────────────────
  "shell.showIntro": "ಈ ಪುಟದ ಬಗ್ಗೆ",
  "shell.openTour": "ಪ್ರವಾಸ",

  // ── Tour steps ───────────────────────────────────────────────────────────
  "tour.stepOf": "ಹಂತ",
  "tour.skip": "ಬಿಟ್ಟುಬಿಡಿ",
  "tour.back": "ಹಿಂದೆ",
  "tour.next": "ಮುಂದೆ",
  "tour.finish": "ಮುಗಿಸಿ",

  "tour.navTitle": "ಪೈಪ್‌ಲೈನ್",
  "tour.navText":
    "ಕಚ್ಚಾ ಫೈಲ್‌ಗಳಿಂದ ಮುದ್ರಿಸಬಹುದಾದ ವರದಿಯವರೆಗಿನ ಪ್ರತಿ ಹಂತ — ಅನುಕ್ರಮವಾಗಿ ಕೆಲಸ ಮಾಡಿ, ಅಥವಾ ನಿಮಗೆ ಬೇಕಾದುದಕ್ಕೆ ನೇರವಾಗಿ ಹೋಗಿ.",

  "tour.datasetTitle": "ನಿಮ್ಮ ದತ್ತಾಂಶ",
  "tour.datasetText":
    "ನೀವು ಪ್ರಸ್ತುತ ಅನ್ವೇಷಿಸುತ್ತಿರುವ ದತ್ತಾಂಶ. ಪರದೆಯ ಮೇಲಿನ ಎಲ್ಲವೂ — ಕೆಪಿಐ, ನಕ್ಷೆಗಳು, ಅಂಶಗಳು — ಇದಕ್ಕೆ ಸೀಮಿತವಾಗಿದೆ.",

  "tour.adddataTitle": "ಇನ್ನಷ್ಟು ದತ್ತಾಂಶ ಸೇರಿಸಿ",
  "tour.adddataText":
    "ಯಾವಾಗ ಬೇಕಾದರೂ ಹೊಸ ಫೈಲ್‌ಗಳನ್ನು ಹಾಕಿ — ಹೊಂದಾಣಿಕೆಯ ಕಾಲಂಗಳು ಸ್ವಯಂಚಾಲಿತವಾಗಿ ವಿಲೀನಗೊಳ್ಳುತ್ತವೆ ಮತ್ತು ನಕಲುಗಳನ್ನು ಬಿಟ್ಟುಬಿಡಲಾಗುತ್ತದೆ.",

  "tour.langTitle": "English / ಕನ್ನಡ",
  "tour.langText":
    "ಇಡೀ ಇಂಟರ್ಫೇಸ್ ಅನ್ನು ಬದಲಿಸಿ — AI ಬರೆದ ವರದಿಗಳು ಮತ್ತು ಕೈಪಿಡಿಗಳು ಸೇರಿದಂತೆ — ಇಂಗ್ಲಿಷ್ ಮತ್ತು ಕನ್ನಡದ ನಡುವೆ.",

  "tour.alertsTitle": "ಸೆಂಟಿನೆಲ್ ಎಚ್ಚರಿಕೆಗಳು",
  "tour.alertsText":
    "DRISHTI ನಿಮ್ಮ ದತ್ತಾಂಶವನ್ನು ನಿರಂತರವಾಗಿ ಗಮನಿಸುತ್ತದೆ ಮತ್ತು ಸಂಖ್ಯಾಶಾಸ್ತ್ರೀಯ ಏರಿಕೆಗಳು ಕಂಡುಬಂದ ತಕ್ಷಣ ಇಲ್ಲಿ ಗುರುತಿಸುತ್ತದೆ.",

  "tour.doneTitle": "ಸಿದ್ಧವಾಗಿದೆ",
  "tour.doneText":
    "ಯಾವುದೇ ಪುಟದ ಬಗ್ಗೆ ತ್ವರಿತ ನೆನಪಿಗಾಗಿ (i) ಐಕಾನ್ ನೋಡಿ. ಈ ಪ್ರವಾಸವನ್ನು ಹೆಡರ್‌ನಿಂದ ಯಾವಾಗ ಬೇಕಾದರೂ ಮತ್ತೆ ತೆರೆಯಿರಿ.",
};
