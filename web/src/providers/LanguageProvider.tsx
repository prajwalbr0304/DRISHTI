import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "en" | "kn";

export const LANGUAGE_OPTIONS: { value: Language; label: string; nativeLabel: string }[] = [
  { value: "en", label: "English", nativeLabel: "English" },
  { value: "kn", label: "Kannada", nativeLabel: "ಕನ್ನಡ" },
];

const STORAGE_KEY = "drishti.language";
const DEFAULT_LANGUAGE: Language = "en";

const translations: Record<Language, Record<string, string>> = {
  en: {},
  kn: {
    "7 days": "7 ದಿನಗಳು",
    "30 days": "30 ದಿನಗಳು",
    "90 days": "90 ದಿನಗಳು",
    "12 months": "12 ತಿಂಗಳು",
    "ADGP / IGP Range": "ಎಡಿಜಿಪಿ / ಐಜಿಪಿ ರೇಂಜ್",
    "Active alerts": "ಸಕ್ರಿಯ ಎಚ್ಚರಿಕೆಗಳು",
    Admin: "ನಿರ್ವಹಣೆ",
    "All data · all districts": "ಎಲ್ಲಾ ಡೇಟಾ · ಎಲ್ಲಾ ಜಿಲ್ಲೆಗಳು",
    "Analytics & Forecasting": "ವಿಶ್ಲೇಷಣೆ ಮತ್ತು ಮುನ್ಸೂಚನೆ",
    "Ask DRISHTI": "ದೃಷ್ಟಿಯನ್ನು ಕೇಳಿ",
    "Ask DRISHTI, or jump to a destination or record…": "ದೃಷ್ಟಿಯನ್ನು ಕೇಳಿ, ಅಥವಾ ಗಮ್ಯಸ್ಥಾನ/ದಾಖಲೆಗೆ ಹೋಗಿ…",
    "Ask DRISHTI…": "ದೃಷ್ಟಿಯನ್ನು ಕೇಳಿ…",
    "Ask about this view": "ಈ ನೋಟದ ಬಗ್ಗೆ ಕೇಳಿ",
    "Ask:": "ಕೇಳಿ:",
    "Case-Review Workload": "ಪ್ರಕರಣ-ಪರಿಶೀಲನೆ ಕೆಲಸದ ಒತ್ತಡ",
    "Case decision-support: summaries, similar cases, leads.": "ಪ್ರಕರಣ ನಿರ್ಧಾರ ಸಹಾಯ: ಸಾರಾಂಶಗಳು, ಸಮಾನ ಪ್ರಕರಣಗಳು, ಸುಳಿವುಗಳು.",
    Cases: "ಪ್ರಕರಣಗಳು",
    Chat: "ಚಾಟ್",
    "Choose interface language": "ಇಂಟರ್ಫೇಸ್ ಭಾಷೆಯನ್ನು ಆರಿಸಿ",
    Collapse: "ಕುಗ್ಗಿಸು",
    "Collapse sidebar": "ಸೈಡ್‌ಬಾರ್ ಕುಗ್ಗಿಸು",
    "Command Center": "ಕಮಾಂಡ್ ಸೆಂಟರ್",
    Comfortable: "ಆರಾಮದಾಯಕ",
    Compact: "ಸಾಂದ್ರ",
    "Conversational, cited answers grounded in the data.": "ಡೇಟಾದ ಮೇಲೆ ಆಧಾರಿತ ಉಲ್ಲೇಖಗಳೊಂದಿಗೆ ಸಂವಾದಾತ್ಮಕ ಉತ್ತರಗಳು.",
    "Conversational, cited answers grounded in the data — in English or Kannada.": "ಇಂಗ್ಲಿಷ್ ಅಥವಾ ಕನ್ನಡದಲ್ಲಿ ಡೇಟಾದ ಮೇಲೆ ಆಧಾರಿತ ಉಲ್ಲೇಖಗಳೊಂದಿಗೆ ಸಂವಾದಾತ್ಮಕ ಉತ್ತರಗಳು.",
    Crime: "ಅಪರಾಧ",
    "Crime Intelligence": "ಅಪರಾಧ ಗುಪ್ತಚರ",
    "Crime Analyst": "ಅಪರಾಧ ವಿಶ್ಲೇಷಕ",
    "Crime Patterns": "ಅಪರಾಧ ಮಾದರಿಗಳು",
    "Cyber Cell": "ಸೈಬರ್ ಸೆಲ್",
    "Cyber and financial crime: money trail, devices and accounts.": "ಸೈಬರ್ ಮತ್ತು ಆರ್ಥಿಕ ಅಪರಾಧ: ಹಣದ ಹಾದಿ, ಸಾಧನಗಳು ಮತ್ತು ಖಾತೆಗಳು.",
    "Cyber cases · state-wide": "ಸೈಬರ್ ಪ್ರಕರಣಗಳು · ರಾಜ್ಯವ್ಯಾಪಿ",
    Custom: "ಕಸ್ಟಮ್",
    "Custom range": "ಕಸ್ಟಮ್ ಶ್ರೇಣಿ",
    "Dashboard language": "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್ ಭಾಷೆ",
    "Data language": "ಡೇಟಾ ಭಾಷೆ",
    "Demo view": "ಡೆಮೊ ನೋಟ",
    Density: "ಸಾಂದ್ರತೆ",
    "DGP / State Command": "ಡಿಜಿಪಿ / ರಾಜ್ಯ ಕಮಾಂಡ್",
    "District chief: workload, approvals and station performance.": "ಜಿಲ್ಲಾ ಮುಖ್ಯಸ್ಥ: ಕೆಲಸದ ಒತ್ತಡ, ಅನುಮೋದನೆಗಳು ಮತ್ತು ಠಾಣಾ ಕಾರ್ಯಕ್ಷಮತೆ.",
    "District · all stations": "ಜಿಲ್ಲೆ · ಎಲ್ಲಾ ಠಾಣೆಗಳು",
    "DySP / ACP": "ಡಿವೈಎಸ್‌ಪಿ / ಎಸಿಪಿ",
    Emergency: "ತುರ್ತು",
    "Emergency Response": "ತುರ್ತು ಪ್ರತಿಕ್ರಿಯೆ",
    "Expand sidebar": "ಸೈಡ್‌ಬಾರ್ ವಿಸ್ತರಿಸು",
    "FIRs, people, networks, hotspots and forecasting.": "ಎಫ್‌ಐಆರ್‌ಗಳು, ಜನರು, ಜಾಲಗಳು, ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು ಮತ್ತು ಮುನ್ಸೂಚನೆ.",
    "Forecast & Risk": "ಮುನ್ಸೂಚನೆ ಮತ್ತು ಅಪಾಯ",
    Forecasts: "ಮುನ್ಸೂಚನೆಗಳು",
    "Full access, model registry, credentials and governance.": "ಪೂರ್ಣ ಪ್ರವೇಶ, ಮಾದರಿ ರಿಜಿಸ್ಟ್ರಿ, ರುಜುವಾತುಗಳು ಮತ್ತು ಆಡಳಿತ.",
    "Geospatial hotspots, forecasts and red-zone alerts.": "ಭೌಗೋಳಿಕ ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು, ಮುನ್ಸೂಚನೆಗಳು ಮತ್ತು ರೆಡ್-ಜೋನ್ ಎಚ್ಚರಿಕೆಗಳು.",
    "Go to": "ಇಲ್ಲಿಗೆ ಹೋಗಿ",
    "Good afternoon": "ಶುಭ ಮಧ್ಯಾಹ್ನ",
    "Good evening": "ಶುಭ ಸಂಜೆ",
    "Good morning": "ಶುಭೋದಯ",
    Home: "ಮುಖಪುಟ",
    History: "ಇತಿಹಾಸ",
    "Individual case files contain personal data and are not accessible to this role, which works with aggregate views only. See the Command Center and Analytics.": "ವೈಯಕ್ತಿಕ ಪ್ರಕರಣ ಕಡತಗಳಲ್ಲಿ ವೈಯಕ್ತಿಕ ಡೇಟಾ ಇದೆ ಮತ್ತು ಸಮಗ್ರ ನೋಟಗಳಲ್ಲಷ್ಟೇ ಕೆಲಸ ಮಾಡುವ ಈ ಪಾತ್ರಕ್ಕೆ ಅವು ಲಭ್ಯವಿಲ್ಲ. ಕಮಾಂಡ್ ಸೆಂಟರ್ ಮತ್ತು ವಿಶ್ಲೇಷಣೆಯನ್ನು ನೋಡಿ.",
    Intake: "ಸ್ವೀಕೃತಿ",
    "Interface language": "ಇಂಟರ್ಫೇಸ್ ಭಾಷೆ",
    "Investigating Officer": "ತನಿಖಾಧಿಕಾರಿ",
    "Investigation Board": "ತನಿಖಾ ಫಲಕ",
    "Kannada": "ಕನ್ನಡ",
    Language: "ಭಾಷೆ",
    "Live Situation": "ನೇರ ಪರಿಸ್ಥಿತಿ",
    "Live operational overview across the state.": "ರಾಜ್ಯಾದ್ಯಂತ ನೇರ ಕಾರ್ಯಾಚರಣಾ ಅವಲೋಕನ.",
    "Map & Hotspots": "ನಕ್ಷೆ ಮತ್ತು ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು",
    "Model Explainability": "ಮಾದರಿ ವಿವರಣಾಶೀಲತೆ",
    "Model governance": "ಮಾದರಿ ಆಡಳಿತ",
    "Model registry, contract audit and governance.": "ಮಾದರಿ ರಿಜಿಸ್ಟ್ರಿ, ಒಪ್ಪಂದ ಪರಿಶೀಲನೆ ಮತ್ತು ಆಡಳಿತ.",
    "Multi-hazard forecasting, readiness and evacuation.": "ಬಹು-ಅಪಾಯ ಮುನ್ಸೂಚನೆ, ಸಿದ್ಧತೆ ಮತ್ತು ಸ್ಥಳಾಂತರ.",
    "Network Analysis": "ಜಾಲ ವಿಶ್ಲೇಷಣೆ",
    "No active alerts.": "ಸಕ್ರಿಯ ಎಚ್ಚರಿಕೆಗಳಿಲ್ಲ.",
    "No matches. Press Enter to ask DRISHTI.": "ಹೊಂದಾಣಿಕೆ ಇಲ್ಲ. ದೃಷ್ಟಿಯನ್ನು ಕೇಳಲು Enter ಒತ್ತಿ.",
    Now: "ಈಗ",
    "Open case #{{id}}": "ಪ್ರಕರಣ #{{id}} ತೆರೆಯಿರಿ",
    "Open person / entity #{{id}}": "ವ್ಯಕ್ತಿ / ಘಟಕ #{{id}} ತೆರೆಯಿರಿ",
    "Open record": "ದಾಖಲೆ ತೆರೆಯಿರಿ",
    "Ops (dark)": "ಆಪ್ಸ್ (ಗಾಢ)",
    "Patterns, networks, hotspots and forecasts.": "ಮಾದರಿಗಳು, ಜಾಲಗಳು, ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು ಮತ್ತು ಮುನ್ಸೂಚನೆಗಳು.",
    Pause: "ವಿರಾಮ",
    "People & Entities": "ಜನರು ಮತ್ತು ಘಟಕಗಳು",
    Play: "ಪ್ಲೇ",
    Playhead: "ಪ್ಲೇಹೆಡ್",
    "Persons, gangs, vehicles, phones and accounts — with risk.": "ವ್ಯಕ್ತಿಗಳು, ಗುಂಪುಗಳು, ವಾಹನಗಳು, ಫೋನ್‌ಗಳು ಮತ್ತು ಖಾತೆಗಳು - ಅಪಾಯದೊಂದಿಗೆ.",
    "Preview another role workspace. Your authenticated permissions remain unchanged.": "ಇನ್ನೊಂದು ಪಾತ್ರದ ಕಾರ್ಯಸ್ಥಳವನ್ನು ಪೂರ್ವವೀಕ್ಷಿಸಿ. ನಿಮ್ಮ ದೃಢೀಕೃತ ಅನುಮತಿಗಳು ಬದಲಾಗುವುದಿಲ್ಲ.",
    "Quick actions": "ತ್ವರಿತ ಕ್ರಮಗಳು",
    "Range command across districts: comparison and oversight.": "ಜಿಲ್ಲೆಗಳಾದ್ಯಂತ ರೇಂಜ್ ಕಮಾಂಡ್: ಹೋಲಿಕೆ ಮತ್ತು ಮೇಲ್ವಿಚಾರಣೆ.",
    "Register FIRs/cases: guided intake, bulk import and supervisory review.": "ಎಫ್‌ಐಆರ್/ಪ್ರಕರಣಗಳನ್ನು ನೋಂದಾಯಿಸಿ: ಮಾರ್ಗದರ್ಶಿತ ಸ್ವೀಕೃತಿ, ಸಾಮೂಹಿಕ ಆಮದು ಮತ್ತು ಮೇಲ್ವಿಚಾರಣಾ ಪರಿಶೀಲನೆ.",
    "Range · multiple districts": "ರೇಂಜ್ · ಹಲವು ಜಿಲ್ಲೆಗಳು",
    Resources: "ಸಂಪನ್ಮೂಲಗಳು",
    Retry: "ಮರುಪ್ರಯತ್ನಿಸಿ",
    "Response Plans": "ಪ್ರತಿಕ್ರಿಯಾ ಯೋಜನೆಗಳು",
    "Road-safety hotspots, accident patterns and enforcement load.": "ರಸ್ತೆ-ಸುರಕ್ಷತಾ ಹಾಟ್‌ಸ್ಪಾಟ್‌ಗಳು, ಅಪಘಾತ ಮಾದರಿಗಳು ಮತ್ತು ಜಾರಿ ಕೆಲಸದ ಒತ್ತಡ.",
    "Saved Queries": "ಉಳಿಸಿದ ಪ್ರಶ್ನೆಗಳು",
    Service: "ಸೇವೆ",
    SHO: "ಎಸ್‌ಎಚ್‌ಒ",
    "Sign out": "ಸೈನ್ ಔಟ್",
    "Situation Overview": "ಪರಿಸ್ಥಿತಿ ಅವಲೋಕನ",
    "SP / District Command": "ಎಸ್‌ಪಿ / ಜಿಲ್ಲಾ ಕಮಾಂಡ್",
    "Socio-Economic": "ಸಾಮಾಜಿಕ-ಆರ್ಥಿಕ",
    "State-wide command view: priorities, escalations and outcomes.": "ರಾಜ್ಯವ್ಯಾಪಿ ಕಮಾಂಡ್ ನೋಟ: ಆದ್ಯತೆಗಳು, ಏರಿಕೆಗಳು ಮತ್ತು ಫಲಿತಾಂಶಗಳು.",
    "Station · all station cases": "ಠಾಣೆ · ಎಲ್ಲಾ ಠಾಣಾ ಪ್ರಕರಣಗಳು",
    "Station chief: registration, assignment and review queue.": "ಠಾಣಾ ಮುಖ್ಯಸ್ಥ: ನೋಂದಣಿ, ನಿಯೋಜನೆ ಮತ್ತು ಪರಿಶೀಲನಾ ಸಾಲು.",
    "State · all districts": "ರಾಜ್ಯ · ಎಲ್ಲಾ ಜಿಲ್ಲೆಗಳು",
    "State · read-across": "ರಾಜ್ಯ · ಅಡ್ಡ-ಓದು",
    "Sub-division oversight: case review, quality and escalation.": "ಉಪವಿಭಾಗ ಮೇಲ್ವಿಚಾರಣೆ: ಪ್ರಕರಣ ಪರಿಶೀಲನೆ, ಗುಣಮಟ್ಟ ಮತ್ತು ಏರಿಕೆ.",
    "Sub-division · circle stations": "ಉಪವಿಭಾಗ · ವೃತ್ತ ಠಾಣೆಗಳು",
    "Switch to": "ಬದಲಿಸಿ",
    "Switch to {{language}}": "{{language}} ಗೆ ಬದಲಿಸಿ",
    "Switch to Desk (light)": "ಡೆಸ್ಕ್ (ಬೆಳಕು) ಗೆ ಬದಲಿಸಿ",
    "Switch to Ops (dark)": "ಆಪ್ಸ್ (ಗಾಢ) ಗೆ ಬದಲಿಸಿ",
    "System Admin": "ಸಿಸ್ಟಂ ನಿರ್ವಾಹಕ",
    "Time range": "ಸಮಯ ಶ್ರೇಣಿ",
    "Toggle sidebar": "ಸೈಡ್‌ಬಾರ್ ಬದಲಿಸಿ",
    "Toggle theme": "ಥೀಮ್ ಬದಲಿಸಿ",
    "Traffic · district corridors": "ಟ್ರಾಫಿಕ್ · ಜಿಲ್ಲಾ ಮಾರ್ಗಗಳು",
    "Traffic Command": "ಟ್ರಾಫಿಕ್ ಕಮಾಂಡ್",
    Trends: "ಪ್ರವೃತ್ತಿಗಳು",
    "Trends, crime patterns, socio-economic signal, forecasts and model explainability.": "ಪ್ರವೃತ್ತಿಗಳು, ಅಪರಾಧ ಮಾದರಿಗಳು, ಸಾಮಾಜಿಕ-ಆರ್ಥಿಕ ಸೂಚನೆ, ಮುನ್ಸೂಚನೆಗಳು ಮತ್ತು ಮಾದರಿ ವಿವರಣಾಶೀಲತೆ.",
    "Trends, socio-economic correlations, forecasts and model explainability.": "ಪ್ರವೃತ್ತಿಗಳು, ಸಾಮಾಜಿಕ-ಆರ್ಥಿಕ ಸಂಬಂಧಗಳು, ಮುನ್ಸೂಚನೆಗಳು ಮತ್ತು ಮಾದರಿ ವಿವರಣಾಶೀಲತೆ.",
    "Works individual cases, people, evidence and leads.": "ವೈಯಕ್ತಿಕ ಪ್ರಕರಣಗಳು, ಜನರು, ಸಾಕ್ಷ್ಯಗಳು ಮತ್ತು ಸುಳಿವುಗಳ ಮೇಲೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ.",
    checking: "ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ",
    degraded: "ಕುಂದಿದೆ",
    down: "ಡೌನ್",
    ok: "ಸರಿ",
  },
};

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function readInitialLanguage(): Language {
  if (typeof window === "undefined") return DEFAULT_LANGUAGE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "kn" || stored === "en" ? stored : DEFAULT_LANGUAGE;
}

function interpolate(value: string, vars?: Record<string, string | number>) {
  if (!vars) return value;
  return Object.entries(vars).reduce(
    (text, [key, replacement]) => text.split(`{{${key}}}`).join(String(replacement)),
    value,
  );
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(readInitialLanguage);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, language);
    document.documentElement.lang = language === "kn" ? "kn" : "en";
    document.documentElement.dataset.language = language;
  }, [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      t: (key, vars) => interpolate(translations[language][key] ?? key, vars),
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
