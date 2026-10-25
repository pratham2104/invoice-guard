// The only icon source: the custom set in src/icons (owned by agent tyler-2a). Loaded with an eager glob so
// the dashboard still builds while that set is being drawn; a name that isn't there yet renders a neutral
// placeholder of the same size, and picks up the real glyph as soon as the file lands.
import type { ComponentType, CSSProperties } from "react";

const modules = import.meta.glob("../icons/**/*.{ts,tsx}", { eager: true }) as Record<string, Record<string, unknown>>;
const SET: Record<string, ComponentType<any>> = {};
for (const mod of Object.values(modules)) {
  for (const [name, value] of Object.entries(mod)) {
    if (typeof value === "function" || (typeof value === "object" && value !== null && "$$typeof" in value)) {
      if (name !== "default") SET[name] = value as ComponentType<any>;
    }
  }
}

export type IconName =
  | "HalberdMark" | "Inbox" | "Vendor" | "School" | "Invoice" | "Bank" | "Phone" | "PhoneCall" | "Fingerprint"
  | "Vision" | "Rules" | "Agent" | "Lock" | "Unlock" | "Shield" | "ShieldCheck" | "Alert" | "Check" | "Cross"
  | "Clock" | "Chain" | "User" | "Users" | "CloudOff" | "Chip" | "Sandbox" | "Message" | "Arrow" | "ChevronDown"
  | "Filter" | "Search" | "Pause" | "Play" | "Dollar" | "Calendar" | "Mail" | "Upload" | "Download" | "Refresh"
  | "External" | "ArrowUpRight" | "Exclaim";

export function Icon({ name, size = 16, className, style, title }: {
  name: IconName; size?: number; className?: string; style?: CSSProperties; title?: string;
}) {
  const C = SET[name] ?? SET[`${name}Icon`];
  const cls = `icon${className ? ` ${className}` : ""}`;
  if (C) {
    return (
      <span className={cls} style={{ width: size, height: size, ...style }} aria-hidden={title ? undefined : true} title={title}>
        <C size={size} width={size} height={size} />
      </span>
    );
  }
  return (
    <span className={cls} style={{ width: size, height: size, ...style }} aria-hidden title={title}>
      <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
        <rect x="3" y="3" width="10" height="10" rx="2.5" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </span>
  );
}
