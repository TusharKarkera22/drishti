// Kannada translations for the Geospatial / Map page.
// Keys are all prefixed `map.`. English fallbacks live inline at each
// call site via t("map.key", "English"), so a missing key safely renders
// English and the UI never breaks.
export const mapKn: Record<string, string> = {
  // Shell title
  "map.title": "ಭೌಗೋಳಿಕ ಗುಪ್ತಚರ",

  // ── Page intro banner ────────────────────────────────────────────────────
  "map.intro":
    "ಅಪರಾಧ ಎಲ್ಲಿ ಕೇಂದ್ರೀಕೃತವಾಗಿದೆ. ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು ದಿನವಿಡೀ ಹೇಗೆ ಚಲಿಸುತ್ತವೆ ಎಂದು ನೋಡಲು ಗಂಟೆಯ ಬ್ಯಾಂಡ್‌ಗಳನ್ನು ಬಳಸಿ; ಮುಂದಿನ ವಾರದ ಅಪಾಯಕ್ಕಾಗಿ ಜಿಲ್ಲೆಗಳಿಗೆ 0–100 ಅಂಕ ನೀಡಲಾಗಿದೆ.",

  // Filter section labels
  "map.districtOverlay": "ಜಿಲ್ಲೆ ಅಡ್ಡಪದರ:",
  "map.timeBand": "ಸಮಯ ವಲಯ:",
  "map.category": "ವರ್ಗ:",

  // District overlay toggle buttons
  "map.overlayOff": "ಆಫ್",
  "map.overlayCompositeRisk": "ಸಂಯೋಜಿತ ಅಪಾಯ",
  "map.overlayPerCap": "1ಲ ಜನಸಂಖ್ಯೆಗೆ",

  // Time band buttons
  "map.bandAllHours": "ಎಲ್ಲಾ ಗಂಟೆಗಳು",
  "map.bandNight": "ರಾತ್ರಿ 00–06",
  "map.bandMorning": "ಬೆಳಿಗ್ಗೆ 06–12",
  "map.bandDay": "ಹಗಲು 12–18",
  "map.bandEvening": "ಸಂಜೆ 18–23",

  // Category "All" button
  "map.allCategories": "ಎಲ್ಲಾ",

  // Stats line
  "map.hotspotCells": "ಹಾಟ್‌ಸ್ಪಾಟ್ ಕೋಶಗಳು",
  "map.noGeoData": "ಈ ದತ್ತಾಂಶದಲ್ಲಿ ಭೌಗೋಳಿಕ ಮಾಹಿತಿ ಇಲ್ಲ",

  // Legend footer
  "map.legend":
    "ಶಾಖ = ಸ್ಥಳ-ಕಾಲಿಕ ಸಾಂದ್ರತೆ · ಮಿಡಿಯುವ ಕೆಂಪು = ಸ್ವಂತ ಆಧಾರರೇಖೆಗೆ ಹೋಲಿಸಿ ಅಂಕಿಅಂಶ ಏರಿಕೆ ವಲಯಗಳು",
};
