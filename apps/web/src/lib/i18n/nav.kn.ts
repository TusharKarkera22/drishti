// Sidebar navigation + Shell chrome (header, alert inbox). Keys: nav.<CODE> match
// the (legacy) NAV item codes; nav.<step> / nav.sub.<step> match the current
// pipeline-step NAV array in Shell.tsx (01 Data … 08 Report). shell.* are the
// surrounding chrome strings. Legacy nav.INS-style keys are kept working even
// though Shell.tsx no longer reads them, in case other surfaces still do.
export const navKn: Record<string, string> = {
  "nav.INS": "ಒಳನೋಟ",
  "nav.INT": "ದತ್ತಾಂಶ ಸ್ವೀಕಾರ",
  "nav.OVW": "ಅವಲೋಕನ",
  "nav.GEO": "ಭೌಗೋಳಿಕ",
  "nav.NET": "ಜಾಲ ವಿಶ್ಲೇಷಣೆ",
  "nav.AGT": "ಸಹಾಯಕರು",
  "nav.RPT": "ಕೈಪಿಡಿ",

  // ── Pipeline nav (Shell.tsx NAV array: step "01".."08") ──────────────────
  "nav.01": "ದತ್ತಾಂಶ",
  "nav.02": "ಸ್ವಚ್ಛ",
  "nav.03": "ಸಾರಾಂಶ",
  "nav.04": "ಅನ್ವೇಷಣೆ",
  "nav.05": "ನಕ್ಷೆ",
  "nav.06": "ಜಾಲ",
  "nav.07": "ಕೇಳಿ",
  "nav.08": "ವರದಿ",

  "nav.sub.01": "ಫೈಲ್‌ಗಳು ಮತ್ತು ದಾಖಲೆಗಳು",
  "nav.sub.02": "ಅಸ್ತವ್ಯಸ್ತ ಫೈಲ್‌ಗಳನ್ನು ಸರಿಪಡಿಸಿ",
  "nav.sub.03": "ಪ್ರಮುಖ ಸಮಸ್ಯೆಗಳು, ಶ್ರೇಣೀಕೃತ",
  "nav.sub.04": "ಕೆಪಿಐ ಮತ್ತು ಚಾರ್ಟ್‌ಗಳು",
  "nav.sub.05": "ಹಾಟ್‌ಸ್ಪಾಟ್ ಮತ್ತು ಅಪಾಯ",
  "nav.sub.06": "ಯಾರು ಸಂಪರ್ಕ ಹೊಂದಿದ್ದಾರೆ",
  "nav.sub.07": "ದತ್ತಾಂಶವನ್ನು ಪ್ರಶ್ನಿಸಿ",
  "nav.sub.08": "ಮುದ್ರಿಸಬಹುದಾದ ಸಾರಾಂಶ",

  "shell.tagline": "ಅಪರಾಧ ಗುಪ್ತಚರ",
  "shell.subtitle": "ಕೆಎಸ್‌ಪಿ · ಡೇಟಾಥಾನ್ 2026",
  "shell.noDataset": "ದತ್ತಾಂಶವಿಲ್ಲ",
  "shell.lang": "ಭಾಷೆ",
  "shell.addData": "+ ದತ್ತಾಂಶ ಸೇರಿಸಿ",
  "shell.alertsTooltip": "ಸೆಂಟಿನೆಲ್ ಎಚ್ಚರಿಕೆಗಳು",
  "shell.alertsInbox": "ಸೆಂಟಿನೆಲ್ ಎಚ್ಚರಿಕೆ ಪೆಟ್ಟಿಗೆ",
  "shell.markAllRead": "ಎಲ್ಲವನ್ನೂ ಓದಿದೆ ಎಂದು ಗುರುತಿಸಿ",
  "shell.noAlerts":
    "ಇನ್ನೂ ಎಚ್ಚರಿಕೆಗಳಿಲ್ಲ — ಸೆಂಟಿನೆಲ್ ಸಂಖ್ಯಾಶಾಸ್ತ್ರೀಯ ಏರಿಕೆಗಳನ್ನು ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಪರಿಶೀಲಿಸುತ್ತದೆ.",
};
