"use client";

// One-line contextual banner shown under a page's title, explaining what the
// page does in plain language. Dismissible (persists per page id in
// localStorage), and re-shown by the Shell's (i) button via a
// `drishti:showintro` window CustomEvent (optionally scoped to one page id).
import { useEffect, useState } from "react";
import { Info, X } from "lucide-react";
import { useLang } from "@/lib/i18n";

const STORAGE_PREFIX = "intro.";

export default function PageIntro({ id, text }: { id: string; text: string }) {
  const { t } = useLang();
  const [dismissed, setDismissed] = useState(true); // default hidden until we check localStorage (avoids SSR flash)

  useEffect(() => {
    let timer: number | undefined = window.setTimeout(() => {
      try {
        setDismissed(window.localStorage.getItem(`${STORAGE_PREFIX}${id}`) === "1");
      } catch {
        setDismissed(false);
      }
    }, 0);
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ id?: string } | undefined>).detail;
      // If the event names a specific page id, only react when it matches us;
      // an event with no detail re-shows the intro on every mounted page.
      if (detail?.id && detail.id !== id) return;
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      setDismissed(false);
      try {
        window.localStorage.removeItem(`${STORAGE_PREFIX}${id}`);
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("drishti:showintro", handler);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener("drishti:showintro", handler);
    };
  }, [id]);

  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(`${STORAGE_PREFIX}${id}`, "1");
    } catch {
      /* ignore */
    }
  };

  if (dismissed) return null;

  return (
    <div className="panel flex items-start gap-2.5 px-3.5 py-2.5 mb-4 border-l-2 border-teal/50 sweep-in">
      <Info size={15} className="text-teal shrink-0 mt-0.5" />
      <p className="flex-1 text-xs text-dim leading-relaxed">{text}</p>
      <button
        type="button"
        onClick={dismiss}
        className="shrink-0 text-dim hover:text-amber transition-colors"
        aria-label={t("common.dismiss", "Dismiss")}
      >
        <X size={14} />
      </button>
    </div>
  );
}
