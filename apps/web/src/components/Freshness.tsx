"use client";

// Small "as of HH:MM" chip + manual refresh button, shown next to a page/panel
// title wherever the API returns computed_at/cached on its response (insights
// bundle, brief, dashboard queries). Renders nothing if computedAt is missing
// so older/unaffected responses never show a broken chip.
import { RefreshCw } from "lucide-react";
import { useLang } from "@/lib/i18n";

export default function Freshness({
  computedAt,
  cached,
  onRefresh,
}: {
  computedAt?: string;
  cached?: boolean;
  onRefresh?: () => void;
}) {
  const { t } = useLang();
  if (!computedAt) return null;

  const hhmm = new Date(computedAt).toLocaleTimeString("en-IN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="flex items-center gap-1.5 value-mono text-[10px] text-dim">
      <span>
        {t("common.computed", "Computed")} {hhmm}
        {cached ? ` · ${t("common.cached", "cached")}` : ""}
      </span>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          title={t("common.refresh", "Refresh")}
          className="flex items-center justify-center w-5 h-5 text-dim hover:text-amber transition-colors"
        >
          <RefreshCw size={11} />
        </button>
      )}
    </div>
  );
}
