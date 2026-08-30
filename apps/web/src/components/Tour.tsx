"use client";

// First-visit guided tour: a lightweight custom overlay (no new dependency)
// that walks a new user across the Shell's chrome — sidebar nav, dataset
// chip, +Add data, language toggle, alerts bell — using the same
// getBoundingClientRect positioning technique as the Shell's AlertBell
// dropdown. Auto-opens once per browser (localStorage "tour.done") when a
// dataset is open; the Shell's "Tour" header button re-opens it anytime.
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLang } from "@/lib/i18n";

const STORAGE_KEY = "tour.done";

interface TourStep {
  anchor: string | null;
  titleKey: string;
  titleEn: string;
  textKey: string;
  textEn: string;
}

const STEPS: TourStep[] = [
  {
    anchor: "nav",
    titleKey: "tour.navTitle",
    titleEn: "The pipeline",
    textKey: "tour.navText",
    textEn: "Every step from raw files to a printable report — work through them in order, or jump straight to what you need.",
  },
  {
    anchor: "dataset",
    titleKey: "tour.datasetTitle",
    titleEn: "Your dataset",
    textKey: "tour.datasetText",
    textEn: "The dataset you're currently exploring. Everything on screen — KPIs, maps, findings — is scoped to it.",
  },
  {
    anchor: "adddata",
    titleKey: "tour.adddataTitle",
    titleEn: "Add more data",
    textKey: "tour.adddataText",
    textEn: "Drop in new files anytime — matching columns merge automatically and duplicates are skipped.",
  },
  {
    anchor: "lang",
    titleKey: "tour.langTitle",
    titleEn: "English / ಕನ್ನಡ",
    textKey: "tour.langText",
    textEn: "Switch the whole interface — including AI-written briefs and reports — between English and Kannada.",
  },
  {
    anchor: "alerts",
    titleKey: "tour.alertsTitle",
    titleEn: "Sentinel alerts",
    textKey: "tour.alertsText",
    textEn: "DRISHTI watches your data continuously and flags statistical spikes here the moment they appear.",
  },
  {
    anchor: null,
    titleKey: "tour.doneTitle",
    titleEn: "You're set",
    textKey: "tour.doneText",
    textEn: "Look for the (i) icon on any page for a quick reminder of what it does. Reopen this tour anytime from the header.",
  },
];

export default function Tour() {
  const { t } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [cardStyle, setCardStyle] = useState<React.CSSProperties>({});
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-open once per browser, only once a dataset is actually open.
  useEffect(() => {
    if (!ds) return;
    const timer = window.setTimeout(() => {
      try {
        if (window.localStorage.getItem(STORAGE_KEY) === "1") return;
      } catch {
        /* if localStorage is unavailable, fall through and show the tour */
      }
      setStep(0);
      setOpen(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [ds]);

  // Re-open on demand via the Shell's "Tour" button.
  useEffect(() => {
    const handler = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener("drishti:opentour", handler);
    return () => window.removeEventListener("drishti:opentour", handler);
  }, []);

  // Position the card + highlight against the current step's anchor.
  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      const anchor = STEPS[step]?.anchor;
      if (!anchor) {
        setTargetRect(null);
        setCardStyle({
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        });
        return;
      }
      const el = document.querySelector(`[data-tour="${anchor}"]`);
      if (!el) {
        setTargetRect(null);
        setCardStyle({ position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)" });
        return;
      }
      const rect = el.getBoundingClientRect();
      setTargetRect(rect);

      const cardWidth = 320;
      const margin = 12;
      let left = rect.right + margin;
      let top = rect.top;
      if (left + cardWidth > window.innerWidth - margin) {
        left = rect.left;
        top = rect.bottom + margin;
      }
      left = Math.min(left, window.innerWidth - cardWidth - margin);
      left = Math.max(left, margin);
      top = Math.min(top, window.innerHeight - 220);
      top = Math.max(top, margin);

      setCardStyle({ position: "fixed", top, left, width: cardWidth });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, step]);

  const finish = () => {
    setOpen(false);
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
  };

  const skip = () => finish();
  const next = () => {
    if (step >= STEPS.length - 1) {
      finish();
      return;
    }
    setStep((s) => s + 1);
  };
  const back = () => setStep((s) => Math.max(0, s - 1));

  if (!open) return null;
  const current = STEPS[step];
  const last = step === STEPS.length - 1;

  return (
    <>
      {/* dim overlay */}
      <div className="fixed inset-0 z-[9997] bg-ink/60" onClick={skip} />

      {/* highlight ring around the active anchor */}
      {targetRect && (
        <div
          className="fixed z-[9998] pointer-events-none"
          style={{
            top: targetRect.top - 4,
            left: targetRect.left - 4,
            width: targetRect.width + 8,
            height: targetRect.height + 8,
            outline: "2px solid var(--amber)",
            outlineOffset: "2px",
            borderRadius: "3px",
            transition: "all 0.15s ease-out",
          }}
        />
      )}

      {/* step card */}
      <div
        ref={cardRef}
        style={{ ...cardStyle, zIndex: 9999 }}
        className="panel p-4 shadow-2xl sweep-in"
      >
        <div className="label-hud text-amber mb-1.5">
          {t("tour.stepOf", "Step")} {step + 1} / {STEPS.length}
        </div>
        <div className="font-display text-sm uppercase tracking-wider text-text mb-1.5">
          {t(current.titleKey, current.titleEn)}
        </div>
        <p className="text-xs text-dim leading-relaxed mb-4">
          {t(current.textKey, current.textEn)}
        </p>
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={skip}
            className="value-mono text-[10px] text-dim hover:text-amber transition-colors"
          >
            {t("tour.skip", "Skip")}
          </button>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button
                type="button"
                onClick={back}
                className="value-mono text-[10px] px-3 py-1.5 border border-line text-dim hover:text-text hover:border-amber/50 transition-colors"
              >
                {t("tour.back", "Back")}
              </button>
            )}
            <button
              type="button"
              onClick={next}
              className="value-mono text-[10px] px-3 py-1.5 bg-amber text-ink hover:bg-amber-dim transition-colors"
            >
              {last ? t("tour.finish", "Finish") : t("tour.next", "Next")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
