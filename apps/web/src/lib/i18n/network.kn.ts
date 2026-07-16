// Kannada translations for the Network / Link-analysis page.
// Keys are all prefixed `network.`. English fallbacks live inline at each
// call site via t("network.key", "English"), so a missing key safely renders
// English and the UI never breaks.
export const networkKn: Record<string, string> = {
  // Shell title
  "network.title": "ಅಪರಾಧ ಜಾಲ ವಿಶ್ಲೇಷಣೆ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "network.intro":
    "ಯಾರು ಸಂಪರ್ಕ ಹೊಂದಿದ್ದಾರೆ — ಹಂಚಿದ ಫೋನ್, ವಿಳಾಸ ಮತ್ತು UPI ಐಡಿಗಳ ಮೂಲಕ ಜನರನ್ನು ಜೋಡಿಸಲಾಗಿದೆ. ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಯ ಪ್ರೊಫೈಲ್ ಮತ್ತು MO ನೋಡಲು ಕ್ಲಿಕ್ ಮಾಡಿ.",

  // Search panel
  "network.searchLabel": "ಘಟಕಗಳು / ಪ್ರಕರಣಗಳನ್ನು ಹುಡುಕಿ",
  "network.searchPlaceholder": "ಹೆಸರು, FIR ಸಂಖ್ಯೆ…",
  "network.searchButton": "ಹುಡುಕಿ",

  // Network summary panel
  "network.networkSummary": "ಜಾಲ",
  "network.nodes": "ನೋಡ್‌ಗಳು",
  "network.links": "ಕೊಂಡಿಗಳು",
  "network.majorClusters": "ಪ್ರಮುಖ ಗುಂಪುಗಳು",

  // Repeat Offenders panel
  "network.repeatOffenders": "ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು",
  "network.cases": "ಪ್ರಕರಣಗಳು",

  // Key Players panel
  "network.keyPlayers": "ಪ್ರಮುಖ ವ್ಯಕ್ತಿಗಳು · ಕೇಂದ್ರೀಯತೆ",

  // Graph header / instruction state
  "network.selectEntity": "ಜಾಲ ನಕ್ಷೆ ಮಾಡಲು ಒಂದು ಘಟಕ ಆರಿಸಿ",
  "network.linkAnalysis": "ಕೊಂಡಿ ವಿಶ್ಲೇಷಣೆ",
  "network.hiddenLink": "ಗುಪ್ತ ಕೊಂಡಿ",

  // Legend labels
  "network.legendAccused": "ಆರೋಪಿ",
  "network.legendVictim": "ಬಾಧಿತ",
  "network.legendCase": "ಪ್ರಕರಣ",
  "network.legendSharedPhoneAddress": "ಹಂಚಿದ ಫೋನ್/ವಿಳಾಸ",
  "network.legendMoneyTrail": "ಹಂಚಿದ UPI (ಹಣದ ಜಾಡು)",
  "network.legendPossibleSamePerson": "ಒಂದೇ ವ್ಯಕ್ತಿ ಇರಬಹುದು",

  // Offender profile card
  "network.profileTitle": "ಅಪರಾಧಿ ಪ್ರೊಫೈಲ್",
  "network.profileCases": "ಪ್ರಕರಣಗಳು",
  "network.profileMO": "ಎಂಒ",

  // "Not available" state
  "network.unavailableTitle": "ಈ ದತ್ತಾಂಶಕ್ಕೆ ಜಾಲ ವಿಶ್ಲೇಷಣೆ ಲಭ್ಯವಿಲ್ಲ",
  "network.unavailableDesc":
    "ಜಾಲ ವಿಶ್ಲೇಷಣೆ ವ್ಯಕ್ತಿಗಳು ಮತ್ತು ಹಂಚಿದ ಗುರುತುಗಳ (ಹೆಸರು, ಫೋನ್ ಸಂಖ್ಯೆ, ವಿಳಾಸ) ಮೂಲಕ ದಾಖಲೆಗಳನ್ನು ಜೋಡಿಸುತ್ತದೆ. ಈ ದತ್ತಾಂಶದಲ್ಲಿ ಅವು ಇಲ್ಲ, ಆದ್ದರಿಂದ ನಕ್ಷೆ ಮಾಡಲು ಯಾವುದೇ ಜಾಲವಿಲ್ಲ.",
  "network.switchDataset": "← ಜೋಡಿಸಬಹುದಾದ ವ್ಯಕ್ತಿಗಳಿರುವ ದತ್ತಾಂಶ ತೆರೆಯಿರಿ (ಉದಾ. ಅಪರಾಧ ದತ್ತಾಂಶ)",
};
