"use client";

// Lightweight i18n: a global language context with a t(key, english) helper.
// English text lives INLINE at every call site, so a missing/forgotten key
// safely renders English — the UI can never break. Kannada strings come from
// the merged KN dictionary (one *.kn.ts module per surface). Persisted to
// localStorage so the choice sticks across client-side navigation.

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { KN } from "./kn";

export type Lang = "en" | "kn";

type LangCtxValue = {
  lang: Lang;
  setLang: (l: Lang) => void;
  toggle: () => void;
  /** Returns Kannada for `key` when lang === "kn" (falling back to `en`), else `en`. */
  t: (key: string, en: string) => string;
};

const LangCtx = createContext<LangCtxValue>({
  lang: "en",
  setLang: () => {},
  toggle: () => {},
  t: (_key, en) => en,
});

const STORAGE_KEY = "drishti.lang";

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "kn" || saved === "en") setLangState(saved);
    } catch {
      /* localStorage unavailable — stay on default */
    }
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  };

  const toggle = () => setLang(lang === "en" ? "kn" : "en");
  const t = (key: string, en: string) => (lang === "en" ? en : KN[key] ?? en);

  return <LangCtx.Provider value={{ lang, setLang, toggle, t }}>{children}</LangCtx.Provider>;
}

export const useLang = () => useContext(LangCtx);
