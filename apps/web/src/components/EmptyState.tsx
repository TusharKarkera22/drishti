"use client";

// Generic centered "nothing here yet" panel — generalized from the Network
// page's "not available" pattern. Used by /data and any page when !ds, and
// anywhere else a surface has nothing to show but wants a consistent look
// with an actionable CTA instead of a bare text line.
import Link from "next/link";
import { Database } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export default function EmptyState({
  title,
  text,
  ctaHref,
  ctaLabel,
  Icon = Database,
}: {
  title: string;
  text: string;
  ctaHref?: string;
  ctaLabel?: string;
  Icon?: LucideIcon;
}) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="panel p-8 max-w-md w-full text-center">
        <Icon size={28} className="mx-auto mb-3 text-dim" />
        <div className="font-display text-lg uppercase tracking-wider text-text mb-2">
          {title}
        </div>
        <p className="text-dim text-sm leading-relaxed mb-5">{text}</p>
        {ctaHref && ctaLabel && (
          <Link
            href={ctaHref}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber text-ink font-display uppercase tracking-wider text-sm hover:bg-amber-dim transition-colors"
          >
            {ctaLabel}
          </Link>
        )}
      </div>
    </div>
  );
}
