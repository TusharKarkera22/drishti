"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Info, Compass } from "lucide-react";
import { getAlerts, markAlertsRead, type SentinelAlert } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import Tour from "@/components/Tour";

const NAV = [
  { href: "/data",      label: "Data",       sub: "files & records",     step: "01" },
  { href: "/intake",    label: "Clean",      sub: "fix messy files",     step: "02" },
  { href: "/insights",  label: "Brief",      sub: "top problems, ranked", step: "03" },
  { href: "/dashboard", label: "Explore",    sub: "KPIs & charts",       step: "04" },
  { href: "/map",       label: "Map",        sub: "hotspots & risk",     step: "05" },
  { href: "/network",   label: "Network",    sub: "who's connected",     step: "06" },
  { href: "/agents",    label: "Ask",        sub: "question the data",   step: "07" },
  { href: "/report",    label: "Report",     sub: "printable summary",   step: "08" },
];

function Clock() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(new Date().toLocaleString("en-IN", { hour12: false }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);
  return <span className="value-mono text-xs text-dim">{now}</span>;
}

function AlertBell({ ds }: { ds: string }) {
  const [alerts, setAlerts] = useState<SentinelAlert[]>([]);
  const [open, setOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { t } = useLang();

  useEffect(() => {
    if (!ds) return;
    const load = () => getAlerts(ds).then(setAlerts).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [ds]);

  // Position the dropdown directly below the bell button using fixed coords
  const openDropdown = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownStyle({
        position: "fixed",
        top: rect.bottom + 8,
        right: window.innerWidth - rect.right,
      });
    }
    setOpen((o) => !o);
  };

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  if (!ds) return null;
  const unread = alerts.filter((a) => !a.read).length;

  return (
    <>
    <div className="relative w-8 h-8 shrink-0">
      <button
        ref={buttonRef}
        onClick={openDropdown}
        title={t("shell.alertsTooltip", "Sentinel alerts")}
        data-tour="alerts"
        className="flex items-center justify-center w-full h-full text-dim hover:text-amber transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      </button>
      {unread > 0 && (
        <span
          className="absolute rounded-full bg-signal text-ink text-[9px] value-mono flex items-center justify-center pulse-red leading-none pointer-events-none"
          style={{ width: "16px", height: "16px", top: "-4px", right: "-4px" }}
        >
          {unread}
        </span>
      )}
    </div>

      {open && (
        <div
          ref={dropdownRef}
          style={{ ...dropdownStyle, zIndex: 9999, width: "24rem" }}
          className="bg-ink-2 border border-line shadow-2xl"
        >
          <div className="flex items-center justify-between px-3 py-2 border-b border-line">
            <span className="label-hud text-signal">{t("shell.alertsInbox", "Sentinel Alert Inbox")}</span>
            {unread > 0 && (
              <button
                onClick={() => {
                  markAlertsRead(ds).then(() =>
                    setAlerts((as) => as.map((a) => ({ ...a, read: true })))
                  );
                }}
                className="value-mono text-[10px] text-dim hover:text-amber"
              >
                {t("shell.markAllRead", "mark all read")}
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {!alerts.length && (
              <div className="p-3 text-dim text-xs">
                {t("shell.noAlerts", "No alerts yet — the sentinel scans automatically for statistical spikes.")}
              </div>
            )}
            {alerts.map((a) => (
              <Link
                key={a.id}
                href={`/dashboard/?ds=${ds}`}
                onClick={() => setOpen(false)}
                className={`block px-3 py-2 border-b border-line/50 hover:bg-ink-3 ${
                  a.read ? "opacity-50" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  {!a.read && <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-signal shrink-0" />}
                  <div className="flex flex-row items-baseline justify-between gap-4 w-full">
                    <span className="text-xs text-text leading-snug">{a.title}</span>
                    <span className="value-mono text-[9px] text-dim shrink-0">
                      {new Date(a.at).toLocaleString("en-IN", { hour12: false })}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function ShellInner({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const { t, lang, toggle } = useLang();

  return (
    <div className="flex min-h-screen">
      <aside className="w-48 shrink-0 border-r border-line bg-ink-2/60 flex flex-col print:hidden">
        <Link href="/" className="flex items-center gap-2.5 px-4 py-5 border-b border-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/app/drishti-emblem.png" alt="DRISHTI" width={34} height={34} className="shrink-0" />
          <div className="min-w-0">
            <div className="font-display text-2xl font-bold tracking-[0.12em] text-amber leading-none">
              DRISHTI
            </div>
            <div className="label-hud mt-1">{t("shell.tagline", "Crime Intelligence")}</div>
          </div>
        </Link>
        <nav className="flex-1 py-3" data-tour="nav">
          {NAV.map((n) => {
            const active = pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={`${n.href}/?ds=${ds}`}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm border-l-2 transition-colors ${
                  active
                    ? "border-amber text-amber bg-ink-3"
                    : "border-transparent text-dim hover:text-text hover:bg-ink-3/50"
                }`}
              >
                <span className="value-mono text-[10px] opacity-70">{n.step}</span>
                <div className="min-w-0">
                  <div className="font-display uppercase tracking-wider leading-tight">
                    {t(`nav.${n.step}`, n.label)}
                  </div>
                  <div className="value-mono text-[9px] text-dim leading-tight truncate">
                    {t(`nav.sub.${n.step}`, n.sub)}
                  </div>
                </div>
              </Link>
            );
          })}
        </nav>
        <div className="px-4 py-3 border-t border-line label-hud">
          KSP · Datathon 2026
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between border-b border-line px-6 py-3 bg-ink-2/40 print:hidden">
          <h1 className="font-display text-lg uppercase tracking-[0.15em]">{title}</h1>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("drishti:showintro"))}
              title={t("shell.showIntro", "About this page")}
              className="flex items-center justify-center w-7 h-7 text-dim hover:text-teal transition-colors"
            >
              <Info size={15} />
            </button>
            {ds && (
              <button
                type="button"
                onClick={() => window.dispatchEvent(new CustomEvent("drishti:opentour"))}
                title={t("shell.openTour", "Tour")}
                className="flex items-center gap-1 value-mono text-[10px] border border-line px-2 py-1 hover:border-amber/60 hover:text-amber text-dim transition-colors"
              >
                <Compass size={12} /> {t("shell.openTour", "Tour")}
              </button>
            )}
            {ds && (
              <Link
                href={`/intake/?ds=${ds}`}
                data-tour="adddata"
                className="flex items-center gap-1 value-mono text-[10px] border border-amber/60 text-amber px-2 py-1 hover:bg-amber/10 transition-colors"
              >
                {t("shell.addData", "+ Add data")}
              </Link>
            )}
            <button
              type="button"
              onClick={toggle}
              title="Switch language / ಭಾಷೆ ಬದಲಿಸಿ"
              data-tour="lang"
              className="flex items-center gap-1 value-mono text-[10px] border border-line px-2 py-1 hover:border-amber/60 transition-colors"
            >
              <span className={lang === "en" ? "text-amber" : "text-dim"}>EN</span>
              <span className="text-line">·</span>
              <span className={`font-display ${lang === "kn" ? "text-amber" : "text-dim"}`}>ಕನ್ನಡ</span>
            </button>
            <AlertBell ds={ds} />
            <span data-tour="dataset" className="value-mono text-xs text-teal">
              {ds || t("shell.noDataset", "no dataset")}
            </span>
            <Clock />
          </div>
        </header>
        <main className="flex-1 p-6 overflow-auto print:p-0 print:overflow-visible">
          {children}
        </main>
      </div>
      <Tour />
    </div>
  );
}

export default function Shell(props: { title: string; children: React.ReactNode }) {
  return (
    <Suspense>
      <ShellInner {...props} />
    </Suspense>
  );
}
