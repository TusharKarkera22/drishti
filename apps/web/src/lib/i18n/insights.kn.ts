// Kannada translations for the Insights / Command Brief page.
// Keys are all prefixed `insights.`. English fallbacks live inline at each
// call site via t("insights.key", "English"), so a missing key safely renders
// English and the UI never breaks.
export const insightsKn: Record<string, string> = {
  // Shell title
  "insights.title": "ಒಳನೋಟ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "insights.pageIntro":
    "DRISHTI ಯ ಉತ್ತರ-ಮೊದಲ ನೋಟ: ನಿಮ್ಮ ದತ್ತಾಂಶದಲ್ಲಿನ ಪ್ರಮುಖ ಸಮಸ್ಯೆಗಳು, ತೀವ್ರತೆಯ ಪ್ರಕಾರ ಶ್ರೇಣೀಕೃತ. ಅದರ ಪುರಾವೆಗೆ ಹೋಗಲು ಯಾವುದೇ ಅಂಶವನ್ನು ಕ್ಲಿಕ್ ಮಾಡಿ.",

  // ── Staged loading narration ─────────────────────────────────────────────
  "insights.load1": "ಏರಿಕೆಗಳಿಗಾಗಿ ಸ್ಕ್ಯಾನ್ ಮಾಡಲಾಗುತ್ತಿದೆ…",
  "insights.load2": "ಜಿಲ್ಲಾ ಅಪಾಯಕ್ಕೆ ಅಂಕ ನೀಡಲಾಗುತ್ತಿದೆ…",
  "insights.load3": "ಅಸಂಗತತೆಗಳನ್ನು ಪತ್ತೆ ಮಾಡಲಾಗುತ್ತಿದೆ…",
  "insights.load4": "ಅಂಶಗಳನ್ನು ಶ್ರೇಣೀಕರಿಸಲಾಗುತ್ತಿದೆ…",

  // Commander's Brief panel
  "insights.commandersBrief": "ಕಮಾಂಡರ್ ವರದಿ",
  "insights.drafting": "ರಚಿಸಲಾಗುತ್ತಿದೆ…",
  "insights.noBrief": "ಯಾವುದೇ ವರದಿ ಲಭ್ಯವಿಲ್ಲ.",

  // Priority findings section
  "insights.priorityFindings": "ಪ್ರಮುಖ ಅಂಶಗಳು",
  "insights.noProblems":
    "ಯಾವುದೇ ಗಮನಾರ್ಹ ಸಮಸ್ಯೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ — ದತ್ತಾಂಶ ಸ್ಪಷ್ಟ ಮತ್ತು ಸ್ಥಿರವಾಗಿದೆ.",

  // Finding type tags
  "insights.tagSpike": "ಏರಿಕೆ",
  "insights.tagRisingRisk": "ಹೆಚ್ಚುತ್ತಿರುವ ಅಪಾಯ",
  "insights.tagNetwork": "ಜಾಲ",
  "insights.tagAnomaly": "ಅಸಂಗತತೆ",
  "insights.tagDataGap": "ದತ್ತಾಂಶ ಕೊರತೆ",
  "insights.tagSpatiotemporal": "ಸಮಯ-ಸ್ಥಳ",
  "insights.tagSocioEcon": "ಸಾಮಾಜಿಕ-ಆರ್ಥಿಕ",
  "insights.tagEmerging": "ಉದಯೋನ್ಮುಖ",
  "insights.tagMO": "ಎಂಒ ಸಹಿ",
  "insights.tagPredUndetected": "ಪತ್ತೆ ಅಪಾಯ",
  "insights.tagPredStall": "ವಿಳಂಬ ಅಪಾಯ",

  // FindingCard — "View →"
  "insights.view": "ತೆರೆಯಿರಿ",

  // 7-Day Outlook (ForecastPanel)
  "insights.sevenDayOutlook": "7-ದಿನಗಳ ಮುನ್ನೋಟ",
  "insights.confidence": "ವಿಶ್ವಾಸ",
  "insights.confidenceHigh": "ಹೆಚ್ಚು",
  "insights.confidenceMedium": "ಮಧ್ಯಮ",
  "insights.confidenceLow": "ಕಡಿಮೆ",
  "insights.risk": "ಅಪಾಯ",

  // COMP_META forecast component labels
  "insights.compVolume": "ಪ್ರಮಾಣ",
  "insights.compTrend": "ಪ್ರವೃತ್ತಿ",
  "insights.compSpike": "ಏರಿಕೆ",
  "insights.compExposure": "ಒಡ್ಡಿಕೆ",

  // Credibility check (Credibility component)
  "insights.credibilityCheck": "ವಿಶ್ವಾಸಾರ್ಹತೆ ಪರಿಶೀಲನೆ",
  "insights.credibilityOver": "ಕಳೆದ",
  "insights.credibilityWeeks": "ವಾರ(ಗಳಲ್ಲಿ), ಮೇಲ್ಭಾಗದ",
  "insights.credibilityFlaggedAreas": "ಗುರುತಿಸಿದ ಪ್ರದೇಶಗಳು",
  "insights.credibilityCaptured": "ನಿಜವಾದ ಘಟನೆಗಳನ್ನು ಸೆರೆಹಿಡಿದವು",
  "insights.credibilityInFollowing": "ಮುಂದಿನ",
  "insights.credibilityDays": "ದಿನಗಳಲ್ಲಿ (ಈ ದತ್ತಾಂಶದ ಇತಿಹಾಸದ ಮೇಲೆ ಹಿಂಪಾವತಿ).",
  "insights.credibilityNotEnough":
    "ವಿಶ್ವಾಸಾರ್ಹ ಪರೀಕ್ಷೆಗೆ ಸಾಕಷ್ಟು ಇತಿಹಾಸವಿಲ್ಲ",

  // Loading / empty states
  "insights.synthesizing": "ಆದೇಶ ವರದಿ ಸಂಶ್ಲೇಷಿಸಲಾಗುತ್ತಿದೆ…",
  "insights.noDataset": "ಯಾವುದೇ ದತ್ತಾಂಶ ಆಯ್ಕೆಯಾಗಿಲ್ಲ — ಮುಖಪುಟದಿಂದ ಒಂದನ್ನು ಆರಿಸಿ.",
  "insights.apiError": "— API ಚಾಲನೆಯಲ್ಲಿದೆಯೇ?",

  // Socio-economic correlation scatter
  "insights.corrTitle": "ಸಾಮಾಜಿಕ-ಆರ್ಥಿಕ ಸಂಬಂಧ — ಅಪರಾಧದ ಹಿಂದಿನ ಕಾರಣ",
  "insights.corrSubtitle": "ಅಪರಾಧ ದರ ಮತ್ತು ನಗರೀಕರಣ",
  "insights.corrXAxis": "ನಗರೀಕರಣ %",
  "insights.corrYAxis": "ಅಪರಾಧ ದರ / ಲಕ್ಷ",

  // Predictive Case Triage panel
  "insights.triageTitle": "ಮುನ್ಸೂಚಕ ಪ್ರಕರಣ ವಿಂಗಡಣೆ",
  "insights.triageAdvisory": "ಸಲಹಾ",
  "insights.triageAucLabel": "ಪತ್ತೆ ಮಾದರಿ AUC",
  "insights.triageOpenCasesScored": "ಬಾಕಿ ಪ್ರಕರಣಗಳಿಗೆ ಅಂಕ ನೀಡಲಾಗಿದೆ",
  "insights.triageByAreaTitle": "ಪ್ರದೇಶವಾರು ಮುನ್ಸೂಚಿತ ಪತ್ತೆ ದರ",
  "insights.triageDetectionRate": "ಮುನ್ಸೂಚಿತ ಪತ್ತೆ ದರ",
  "insights.triageFlaggedTitle": "ಮೇಲ್ಭಾಗದ ಗುರುತಿಸಲಾದ ಪ್ರಕರಣಗಳು",
  "insights.triageUndetectedRisk": "ಪತ್ತೆಯಾಗದ-ಅಪಾಯ",
  "insights.triageDaysStall": "ದಿನ, ಸ್ಥಗಿತ",
  "insights.triageGovernance":
    "ಪ್ರಕರಣ ಆದ್ಯತೆಗಾಗಿ AI ಸಲಹಾ ಸಾಧನ — ಇದು ವೈಯಕ್ತಿಕ ಅಪಾಯದ ಅಂಕವಲ್ಲ; ಮಾನವ ಪರಿಶೀಲನೆ ಅಗತ್ಯ.",
};
