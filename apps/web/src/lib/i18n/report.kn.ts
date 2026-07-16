// Kannada translations for the Report / Digital Handbook page.
// Keys are all prefixed `report.`. English fallbacks live inline at each
// call site via t("report.key", "English"), so a missing key safely renders
// English and the UI never breaks.
export const reportKn: Record<string, string> = {
  // Shell title
  "report.title": "ಕೈಪಿಡಿ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "report.intro":
    "ಈ ದತ್ತಾಂಶದ ಮುದ್ರಿಸಬಹುದಾದ ಡಿಜಿಟಲ್ ಕೈಪಿಡಿ — ಕೆಪಿಐಗಳು, ಪ್ರವೃತ್ತಿಗಳು, ಅಪಾಯ ಮತ್ತು ಜಾಲದ ಮುಖ್ಯಾಂಶಗಳು. PDF ಗಾಗಿ ನಿಮ್ಮ ಬ್ರೌಸರ್‌ನ ಮುದ್ರಣ ಬಳಸಿ.",

  // Toolbar
  "report.print": "ಮುದ್ರಿಸಿ / PDF ಉಳಿಸಿ",
  "report.toolbarTagline": "ಸ್ಥಿರ ವಾರ್ಷಿಕ ಕೈಪಿಡಿ, ಬದಲಾಯಿಸಲ್ಪಟ್ಟಿದೆ: ಲೈವ್, ಡ್ರಿಲ್ ಮಾಡಬಹುದಾದ, ಮುದ್ರಿಸಬಹುದಾದ.",

  // Executive Summary panel
  "report.executiveSummary": "ಕಾರ್ಯನಿರ್ವಾಹಕ ಸಾರಾಂಶ · AI-ರಚಿತ",
  "report.summaryLoading": "ಸಾರಾಂಶ ರಚಿಸಲಾಗುತ್ತಿದೆ…",
  "report.summaryError": "LLM ಸೇವೆ ಲಭ್ಯವಿಲ್ಲ — ಕೈಪಿಡಿ ಅದಿಲ್ಲದೆ ಸಂಪೂರ್ಣ ಬಳಕೆಯೋಗ್ಯ.",

  // Monthly trend panel
  "report.monthlyTrend": "ಮಾಸಿಕ ಪ್ರವೃತ್ತಿ",

  // Emerging trends panel
  "report.emergingTrends": "ಉದಯೋನ್ಮುಖ ಪ್ರವೃತ್ತಿಗಳು · ಸ್ವಂತ ಆಧಾರರೇಖೆ ವಿರುದ್ಧ ಅಂಕಿಅಂಶ ಏರಿಕೆಗಳು",

  // Risk board panel
  "report.riskBoard": "ಸಂಯೋಜಿತ ಅಪಾಯ ಫಲಕ · ಮುಂದಿನ 7 ದಿನಗಳು",
  "report.riskBoardWithDemo": "· ಸಾಮಾಜಿಕ-ಜನಸಂಖ್ಯಾ ಒಡ್ಡುವಿಕೆ ಸೇರಿಸಲಾಗಿದೆ",

  // Risk board column headers
  "report.colArea": "ಪ್ರದೇಶ",
  "report.colRisk": "ಅಪಾಯ",
  "report.colDailyAvg": "ದೈನಿಕ ಸರಾಸರಿ",
  "report.colPerLakh": "1ಲ ಜನಸಂಖ್ಯೆ/ದಿನ",
  "report.colForecast": "ಮುನ್ಸೂಚನೆ/ದಿನ",

  // StatTable section titles (when label comes from a static string)
  "report.byArea": "ಪ್ರದೇಶವಾರು",
  "report.byCategory": "ವರ್ಗವಾರು",
  "report.byStatus": "ಸ್ಥಿತಿವಾರು",
  "report.perCapita": "· ತಲಾ ಸೇರಿದಂತೆ",

  // StatTable extra column header
  "report.per1LPop": "1ಲ ಜನಸಂಖ್ಯೆಗೆ",

  // Network highlights panel
  "report.networkHighlights": "ಜಾಲ ಮುಖ್ಯಾಂಶಗಳು",
  "report.networkRepeatOffenders": "ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳು",
  "report.networkKeyPlayers": "ಪ್ರಮುಖ ಆಟಗಾರರು · ಕೇಂದ್ರೀಯತೆ",

  // Loading / empty states
  "report.pickDataset": "ಮುಖಪುಟದಿಂದ ದತ್ತಾಂಶ ಆಯ್ಕೆಮಾಡಿ.",
  "report.assembling": "ಕೈಪಿಡಿ ಸಿದ್ಧಪಡಿಸಲಾಗುತ್ತಿದೆ…",

  // Footer
  "report.footer":
    "DRISHTI ಡಿಜಿಟಲ್ ಕೈಪಿಡಿ — ಸ್ಥಿರ ವಾರ್ಷಿಕ ಅಪರಾಧ ಕೈಪಿಡಿಯನ್ನು ಲೈವ್, ಮ್ಯಾನಿಫೆಸ್ಟ್-ಚಾಲಿತ ದಾಖಲೆಯೊಂದಿಗೆ ಬದಲಾಯಿಸಲಾಗಿದೆ.",
};
