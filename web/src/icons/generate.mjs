// Halberd icon generator: one geometry source -> index.tsx + preview.html. Run: node web/src/icons/generate.mjs
import { writeFileSync } from "node:fs";

const OUT = new URL(".", import.meta.url).pathname.replace(/\/$/, "");

// ---------- geometry helpers ----------
const r = (n) => Math.round(n * 100) / 100;
const fmt = (pts, closed) =>
  pts.map(([x, y], i) => `${i ? "L" : "M"}${r(x)} ${r(y)}`).join(" ") + (closed ? " Z" : "");

// cut every corner (or chosen ones) at distance d along both edges -> 45deg-style chamfer
function cham(pts, d, closed = true) {
  const n = pts.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    const di = Array.isArray(d) ? d[i] : d;
    const end = !closed && (i === 0 || i === n - 1);
    if (!di || end) { out.push(pts[i]); continue; }
    const p = pts[i], a = pts[(i - 1 + n) % n], b = pts[(i + 1) % n];
    const ua = unit(a, p), ub = unit(b, p);
    out.push([p[0] + ua[0] * di, p[1] + ua[1] * di]);
    out.push([p[0] + ub[0] * di, p[1] + ub[1] * di]);
  }
  return out;
}
function unit(to, from) {
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const l = Math.hypot(dx, dy);
  return [dx / l, dy / l];
}
const rect = (x1, y1, x2, y2) => [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
const crect = (x1, y1, x2, y2, d) => fmt(cham(rect(x1, y1, x2, y2), d), true);
const poly = (pts, closed = false) => fmt(pts, closed);
const map = (pts, f) => pts.map(f);
// solid accent notch (filled)
const notch = (x, y, w, h = w) => ({ fill: true, d: `M${r(x)} ${r(y)} H${r(x + w)} V${r(y + h)} H${r(x)} Z` });
const diamond = (cx, cy, s) => `M${r(cx)} ${r(cy - s)} L${r(cx + s)} ${r(cy)} L${r(cx)} ${r(cy + s)} L${r(cx - s)} ${r(cy)} Z`;
const fillD = (d) => ({ fill: true, d });

// split a polyline/polygon wherever it passes within `gap` of the line a->b (for slashed icons)
function breakAround(pts, closed, a, b, gap) {
  const seq = closed ? [...pts, pts[0]] : pts;
  const dist = ([x, y]) => {
    const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
    return Math.abs(dy * x - dx * y + b[0] * a[1] - b[1] * a[0]) / Math.hypot(dx, dy);
  };
  const runs = [];
  let cur = [];
  let lastOk = null;
  const STEPS = 400;
  for (let i = 0; i < seq.length - 1; i++) {
    const p = seq[i], q = seq[i + 1];
    for (let s = 0; s <= STEPS; s++) {
      const t = s / STEPS;
      const pt = [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
      if (dist(pt) > gap) {
        if (!cur.length || s === STEPS) cur.push(pt);
        lastOk = pt;
      } else if (cur.length) {
        cur.push(lastOk);
        runs.push(cur);
        cur = [];
      }
    }
  }
  if (cur.length) runs.push(cur);
  // merge wrap-around for closed shapes
  if (closed && runs.length > 1) {
    const first = runs[0], last = runs[runs.length - 1];
    const f0 = first[0], s0 = seq[0];
    if (Math.abs(f0[0] - s0[0]) < 1e-6 && Math.abs(f0[1] - s0[1]) < 1e-6) {
      runs[0] = [...last, ...first.slice(1)];
      runs.pop();
    }
  }
  return runs.filter((run) => run.length > 1).map((run) => poly(dedupe(run)));
}
function dedupe(run) {
  return run.filter((p, i) => !i || Math.hypot(p[0] - run[i - 1][0], p[1] - run[i - 1][1]) > 1e-3);
}

// ---------- the icons ----------
// Grid 24x24, live area 2..22, stroke 1.75, square caps, miter joins.
// House chamfer: C=2 on large outer corners, c=1.5 on small shapes.
const C = 2, c = 1.5;
const I = {};

// Logo: spear point, axe blade with chamfered beard, back spike, shaft, butt cap.
I.HalberdMark = [
  poly([[10, 2.75], [11.75, 6], [10, 9], [8.25, 6]], true), // spear point
  poly([[10, 9], [10, 19]]), // shaft
  // axe blade: narrow neck, short top horn, long bearded lower edge, flat cutting edge
  poly([[10, 9.5], [14, 9.5], [17.5, 6], [19.75, 8.25], [19.75, 16], [17.25, 19.75], [14, 13.5], [10, 13.5]]),
  poly([[9.25, 10.5], [6, 11.5], [9.25, 12.5]]), // back spike
  fillD(`M8.75 19.5 H11.25 V22 H8.75 Z`), // butt ferrule
  fillD(diamond(17, 12.25, 1.25)), // blade rivet
];

I.Inbox = [
  poly(cham([[3, 13], [6, 4], [18, 4], [21, 13], [21, 20], [3, 20]], [0, 0, 0, 0, C, C]), true),
  poly([[3, 13], [8, 13], [9.5, 15.5], [14.5, 15.5], [16, 13], [21, 13]]),
];

I.Vendor = [
  poly(cham([[4, 21], [4, 3], [14, 3], [14, 21]], [0, C, 0, 0], false)),
  poly(cham([[14, 9], [20, 9], [20, 21]], [0, C, 0], false)),
  poly([[2, 21], [22, 21]]),
  poly([[7, 7], [11, 7]]),
  poly([[7, 10.5], [11, 10.5]]),
  poly([[7, 14], [11, 14]]),
  poly([[16.5, 12.5], [17.5, 12.5]]),
  poly([[8, 21], [8, 17.5], [10, 17.5], [10, 21]]),
  poly([[16.5, 16], [17.5, 16]]),
];

I.School = [
  poly([[7, 21], [7, 10.5], [12, 7], [17, 10.5], [17, 21]]),
  poly([[7, 13.5], [3, 13.5], [3, 21]]),
  poly([[17, 13.5], [21, 13.5], [21, 21]]),
  poly([[2, 21], [22, 21]]),
  poly([[10.5, 21], [10.5, 17], [13.5, 17], [13.5, 21]]),
  poly([[12, 7], [12, 2.5], [15.5, 2.5], [14.5, 3.75], [15.5, 5], [12, 5]]),
  fillD(diamond(12, 12, 1.4)),
];

I.Invoice = [
  poly([[5, 3], [14.5, 3], [19, 7.5], [19, 21], [5, 21]], true),
  poly([[14.5, 3], [14.5, 7.5], [19, 7.5]]),
  poly([[8, 11], [16, 11]]),
  poly([[8, 14], [16, 14]]),
  poly([[8, 17], [12, 17]]),
];

I.Bank = [
  poly(cham([[3, 8], [12, 3], [21, 8]], [1.25, 0, 1.25]), true),
  poly([[6, 11], [6, 17.5]]),
  poly([[10, 11], [10, 17.5]]),
  poly([[14, 11], [14, 17.5]]),
  poly([[18, 11], [18, 17.5]]),
  poly([[3, 21], [21, 21]]),
  fillD(diamond(12, 6, 1)),
];

// handset, symmetric about the bottom-left/top-right diagonal
const HANDSET = [[3, 5], [5, 3], [8.5, 3], [10, 7.5], [8, 9.5], [14.5, 16], [16.5, 14], [21, 15.5], [21, 19], [19, 21], [15, 21], [3, 9]];
I.Phone = [poly(HANDSET, true)];
const small = map(HANDSET, ([x, y]) => [2 + (x - 3) * 0.78, 22 - (21 - y) * 0.78]);
I.PhoneCall = [
  poly(small, true),
  poly(cham([[13, 7], [17, 7], [17, 11]], [0, 1.5, 0], false)),
  poly(cham([[13, 3], [21, 3], [21, 11]], [0, 3, 0], false)),
];

I.Fingerprint = [
  poly([[4, 16], [4, 9], [9, 4], [15, 4], [20, 9], [20, 13]]),
  poly([[20, 16.5], [20, 18]]),
  poly([[7.5, 20], [7.5, 10.5], [10.5, 7.5], [13.5, 7.5], [16.5, 10.5], [16.5, 16], [14.5, 18], [14.5, 20.5]]),
  poly([[12, 11], [12, 16], [11, 17], [11, 19.5]]),
]

I.Vision = [
  poly([[2, 7], [2, 2], [7, 2]]),
  poly([[17, 2], [22, 2], [22, 7]]),
  poly([[22, 17], [22, 22], [17, 22]]),
  poly([[7, 22], [2, 22], [2, 17]]),
  poly([[5.5, 12], [9, 8.5], [15, 8.5], [18.5, 12], [15, 15.5], [9, 15.5]], true),
  fillD(diamond(12, 12, 2)),
];

I.Rules = [
  poly([[3, 6], [4.75, 7.75], [8, 4.5]]),
  poly([[12, 6], [21, 6]]),
  poly([[3, 12.5], [4.75, 14.25], [8, 11]]),
  poly([[12, 12.5], [21, 12.5]]),
  notch(3.5, 17.25, 3.5),
  poly([[12, 19], [21, 19]]),
];

const hex = (cx, cy, R) => [0, 60, 120, 180, 240, 300].map((a) => {
  const t = ((a - 90) * Math.PI) / 180;
  return [cx + R * Math.cos(t), cy + R * Math.sin(t)];
});
I.Agent = [
  poly(hex(12, 12, 9.5), true),
  poly(hex(12, 12, 4), true),
  poly([[12, 2.5], [12, 8]]),
  poly([[12, 16], [12, 21.5]]),
  fillD(diamond(12, 12, 1.4)),
];

const LOCK_BODY = crect(4.5, 10, 19.5, 21, c);
I.Lock = [
  LOCK_BODY,
  poly([[8, 10], [8, 6], [10, 4], [14, 4], [16, 6], [16, 10]]),
  poly([[12, 14.25], [12, 16.75]]),
];
I.Unlock = [
  LOCK_BODY,
  poly([[8, 10], [8, 6], [10, 4], [14, 4], [16, 6], [16, 7]]),
  poly([[12, 14.25], [12, 16.75]]),
];

const SHIELD = [[4, 5], [12, 2.5], [20, 5], [20, 12.5], [12, 21.5], [4, 12.5]];
I.Shield = [poly(SHIELD, true), poly([[12, 3.25], [12, 20.25]])];
I.ShieldCheck = [poly(SHIELD, true), poly([[8.25, 11.75], [11, 14.5], [15.75, 9.75]])];

I.Alert = [
  poly(cham([[12, 2.5], [21.5, 20], [2.5, 20]], 1.75), true),
  poly([[12, 9], [12, 13.5]]),
  notch(11.125, 15.75, 1.75),
];

I.Check = [poly([[4, 12.5], [9.5, 18], [20, 7]])];
I.Cross = [poly([[5.5, 5.5], [18.5, 18.5]]), poly([[18.5, 5.5], [5.5, 18.5]])];

I.Clock = [crect(3, 3, 21, 21, 5.25), poly([[12, 7], [12, 12], [16, 12]])];

const rot = (pts, deg, cx = 12, cy = 12) => {
  const t = (deg * Math.PI) / 180, co = Math.cos(t), si = Math.sin(t);
  return pts.map(([x, y]) => [cx + (x - cx) * co - (y - cy) * si, cy + (x - cx) * si + (y - cy) * co]);
};
const linkPts = (x1, y1, x2, y2, d) => cham(rect(x1, y1, x2, y2), d);
I.Chain = [
  poly(rot(linkPts(2, 8.25, 11, 15.75, 2.5), -45), true),
  poly(rot(linkPts(13, 8.25, 22, 15.75, 2.5), -45), true),
  poly(rot([[7.5, 12], [16.5, 12]], -45)),
]

I.User = [
  crect(8.5, 3, 15.5, 10, 2),
  poly([[4, 21], [4, 18], [7, 15], [17, 15], [20, 18], [20, 21]]),
];
I.Users = [
  crect(4.5, 5, 10.5, 11, 1.75),
  poly([[2, 21], [2, 18.5], [4.5, 16], [10.5, 16], [13, 18.5], [13, 21]]),
  poly([[14, 4], [17.5, 4], [19, 5.5], [19, 9], [17.5, 10.5], [14, 10.5]]),
  poly([[16, 14.5], [19.5, 14.5], [22, 17], [22, 21]]),
];

const CLOUD = [[6.5, 19], [3, 15.5], [3, 13], [6, 10], [7.5, 10], [10, 6], [15, 6], [17.5, 10], [18.5, 10], [21, 12.5], [21, 16.5], [18.5, 19]];
I.CloudOff = [
  ...breakAround(CLOUD, true, [3, 3], [21, 21], 2.4),
  poly([[3, 3], [21, 21]]),
];

const pins = [];
for (const p of [9, 12, 15]) {
  pins.push(poly([[p, 2.5], [p, 5]]), poly([[p, 19], [p, 21.5]]), poly([[2.5, p], [5, p]]), poly([[19, p], [21.5, p]]));
}
I.Chip = [crect(5, 5, 19, 19, C), ...pins, fillD(`M8 8 H11 L8 11 Z`), crect(10.5, 10.5, 15.5, 15.5, 1)];

I.Sandbox = [
  // dashed boundary drawn as explicit segments: chamfered corner brackets + mid dashes
  poly([[2, 6.5], [2, 4], [4, 2], [6.5, 2]]),
  poly([[17.5, 2], [20, 2], [22, 4], [22, 6.5]]),
  poly([[22, 17.5], [22, 20], [20, 22], [17.5, 22]]),
  poly([[6.5, 22], [4, 22], [2, 20], [2, 17.5]]),
  poly([[10.5, 2], [13.5, 2]]),
  poly([[10.5, 22], [13.5, 22]]),
  poly([[2, 10.5], [2, 13.5]]),
  poly([[22, 10.5], [22, 13.5]]),
  // isometric box
  poly(hex(12, 12, 5.5), true),
  poly([[hex(12, 12, 5.5)[5][0], hex(12, 12, 5.5)[5][1]], [12, 12], [hex(12, 12, 5.5)[1][0], hex(12, 12, 5.5)[1][1]]]),
  poly([[12, 12], [12, 17.5]]),
];

I.Message = [
  poly([[3, 6], [5, 4], [19, 4], [21, 6], [21, 14], [19, 16], [10.5, 16], [6.5, 20], [6.5, 16], [5, 16], [3, 14]], true),
  poly([[7, 8.5], [17, 8.5]]),
  poly([[7, 12], [13, 12]]),
];

I.Arrow = [poly([[4, 12], [18.5, 12]]), poly([[13, 6], [19, 12], [13, 18]])];
I.ChevronDown = [poly([[6, 9], [12, 15], [18, 9]])];
I.Filter = [poly(cham([[3, 4], [21, 4], [14, 12], [14, 19], [10, 21], [10, 12]], [1.25, 1.25, 0, 0, 0, 0]), true)];
I.Search = [crect(3.5, 3.5, 16.5, 16.5, 3.75), poly([[15.6, 15.6], [20.5, 20.5]])];
I.Pause = [crect(6, 4, 10, 20, 1), crect(14, 4, 18, 20, 1)];
I.Play = [poly(cham([[7, 4], [19.5, 12], [7, 20]], [1.5, 1.75, 1.5]), true)];

I.Dollar = [
  poly([[17, 6.5], [9, 6.5], [7, 8.5], [7, 10], [9, 12], [15, 12], [17, 14], [17, 15.5], [15, 17.5], [7, 17.5]]),
  poly([[12, 3], [12, 6.5]]),
  poly([[12, 17.5], [12, 21]]),
];

I.Calendar = [
  crect(3, 5, 21, 21, C),
  poly([[3, 10], [21, 10]]),
  poly([[8, 3], [8, 7]]),
  poly([[16, 3], [16, 7]]),
  notch(14, 14, 3),
];

I.Mail = [
  crect(3, 5, 21, 19, C),
  poly([[3.6, 7.4], [12, 13.5], [20.4, 7.4]]),
];

const TRAY = poly([[3, 15], [3, 18.5], [5, 20.5], [19, 20.5], [21, 18.5], [21, 15]]);
I.Upload = [TRAY, poly([[12, 15.5], [12, 4.5]]), poly([[7, 9], [12, 4], [17, 9]])];
I.Download = [TRAY, poly([[12, 3.5], [12, 14]]), poly([[7, 9.5], [12, 14.5], [17, 9.5]])];

I.Refresh = [
  poly([[4, 12], [4, 9], [9, 4], [15, 4], [19.5, 8.5]]),
  poly([[20, 3.5], [20, 8.5], [15, 8.5]]),
  poly([[20, 12], [20, 15], [15, 20], [9, 20], [4.5, 15.5]]),
  poly([[4, 20.5], [4, 15.5], [9, 15.5]]),
];

I.External = [
  poly([[10, 4], [6, 4], [4, 6], [4, 18], [6, 20], [18, 20], [20, 18], [20, 14]]),
  poly([[14, 4], [20, 4], [20, 10]]),
  poly([[19.5, 4.5], [11, 13]]),
];

I.ArrowUpRight = [poly([[6, 18], [17.5, 6.5]]), poly([[8.5, 6], [18, 6], [18, 15.5]])];
// exclamation mark alone, drawn to sit inside a solid risk circle
I.Exclaim = [poly([[12, 6], [12, 13.5]]), notch(11, 16.5, 2)];

// ---------- emit ----------
const ORDER = [
  ["Brand + entities", ["HalberdMark", "Inbox", "Vendor", "School", "Invoice", "Bank", "User", "Users", "Message", "Mail"]],
  ["Verification", ["Phone", "PhoneCall", "Fingerprint", "Vision", "Rules", "Agent", "Chain", "Chip", "Sandbox", "CloudOff"]],
  ["Security + status", ["Lock", "Unlock", "Shield", "ShieldCheck", "Alert", "Check", "Cross", "Clock", "Pause", "Play"]],
  ["Interface", ["Arrow", "ChevronDown", "Filter", "Search", "Dollar", "Calendar", "Upload", "Download", "Refresh", "External"]],
  ["Added", ["ArrowUpRight", "Exclaim"]],
];
const ALL = ORDER.flatMap(([, n]) => n);
if (new Set(ALL).size !== ALL.length) throw new Error("duplicate");
for (const k of Object.keys(I)) if (!ALL.includes(k)) throw new Error("unordered " + k);
for (const k of ALL) if (!I[k]) throw new Error("missing " + k);

const norm = (el) => (typeof el === "string" ? { d: el } : el);

function svgInner(name) {
  return I[name].map(norm).map((e) =>
    e.fill ? `<path d="${e.d}" fill="currentColor" stroke="none"/>` : `<path d="${e.d}"/>`
  ).join("");
}
const SVG_ATTRS = `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="miter" stroke-miterlimit="10"`;
const svg = (name, size, extra = "") =>
  `<svg width="${size}" height="${size}" ${SVG_ATTRS} ${extra} aria-hidden="true">${svgInner(name)}</svg>`;

// ---- index.tsx ----
let tsx = `/**
 * Halberd icon set.
 *
 * 24x24 grid, 2px live-area margin, 1.75 stroke, square caps, mitred joins,
 * corners chamfered at 45deg (armor plate / blade cut) instead of rounded.
 * Stroke-only; the few solid shapes are small accent notches and rivets.
 * Colour comes from CSS via currentColor (ink #0E0D12, active purple #5B2BE0).
 *
 * Generated by generate.mjs (same folder), which also writes preview.html. Edit geometry there and rerun.
 */
import * as React from "react";

export type IconProps = {
  /** Rendered width and height in px (or any CSS length). Default 20. */
  size?: number | string;
  className?: string;
  /** Accessible name. Without it the icon is decorative and aria-hidden. */
  title?: string;
} & Omit<React.SVGProps<SVGSVGElement>, "children" | "width" | "height" | "title">;

function Svg({ size = 20, className, title, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeMiterlimit={10}
      className={className}
      focusable="false"
      {...(title ? { role: "img", "aria-label": title } : { "aria-hidden": true })}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

`;
for (const name of ALL) {
  const kids = I[name].map(norm).map((e) =>
    e.fill ? `<path d="${e.d}" fill="currentColor" stroke="none" />` : `<path d="${e.d}" />`
  );
  tsx += `export const ${name} = (props: IconProps) => (\n  <Svg {...props}>\n${kids.map((k) => "    " + k).join("\n")}\n  </Svg>\n);\n\n`;
}
tsx += `/** Every icon by name, e.g. for pickers or a dynamic \`<Icon name="Shield" />\`. */
export const icons = {\n${ALL.map((n) => `  ${n},`).join("\n")}\n} as const;

export type IconName = keyof typeof icons;

export function Icon({ name, ...props }: IconProps & { name: IconName }) {
  const Component = icons[name];
  return <Component {...props} />;
}
`;
writeFileSync(`${OUT}/index.tsx`, tsx);

// ---- preview.html ----
const cell = (name) => `
      <figure class="cell">
        <div class="sizes">
          <span class="s s16">${svg(name, 16)}</span>
          <span class="s s24">${svg(name, 24)}</span>
          <span class="s s48">${svg(name, 48)}</span>
        </div>
        <figcaption>${name}</figcaption>
      </figure>`;

// construction plate: grid + margin + glyph at 240px
function plate(name, label) {
  let grid = "";
  for (let i = 0; i <= 24; i++) {
    const strong = i === 0 || i === 24;
    grid += `<path d="M${i} 0 V24 M0 ${i} H24" stroke="${strong ? "#C9C7D1" : "#ECEBF0"}" stroke-width="${strong ? 0.06 : 0.04}"/>`;
  }
  return `
      <div class="plate">
        <svg width="232" height="232" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          ${grid}
          <rect x="2" y="2" width="20" height="20" fill="none" stroke="#5B2BE0" stroke-opacity=".35" stroke-width="0.06" stroke-dasharray="0.3 0.3"/>
          <g stroke="currentColor" stroke-width="1.75" stroke-linecap="square" stroke-linejoin="miter" stroke-miterlimit="10" fill="none">${svgInner(name)}</g>
        </svg>
        <div class="plate-label">${label}</div>
      </div>`;
}

const sections = ORDER.map(([group, names]) => `
    <section>
      <h2><span class="idx">${String(ORDER.findIndex(([g]) => g === group) + 1).padStart(2, "0")}</span>${group}<span class="count">${names.length}</span></h2>
      <div class="grid">${names.map(cell).join("")}
      </div>
    </section>`).join("");

const NAV = [["Inbox", "Inbox", false], ["Pause", "Held", true], ["Vendor", "Vendors", false], ["Chain", "Audit chain", false], ["Agent", "Agent", false]];
const navItems = NAV.map(([icon, label, on]) => `<span class="nav-i${on ? " on" : ""}">${svg(icon, 20)}${label}</span>`).join("");
const purpleRow = ALL.map((n) => `<span title="${n}">${svg(n, 24)}</span>`).join("");
const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Halberd Icon Set</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap">
<style>
  :root { --ink:#0E0D12; --mute:#6B6875; --line:#E6E4EB; --soft:#F6F5F8; --purple:#5B2BE0; }
  * { box-sizing:border-box; }
  html,body { margin:0; background:#fff; color:var(--ink); }
  body { font-family:Geist, ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif; -webkit-font-smoothing:antialiased; }
  .page { width:1280px; margin:0 auto; padding:56px 64px 64px; }
  .mono { font-family:"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
  header { display:grid; grid-template-columns: 1fr auto; gap:48px; align-items:end; padding-bottom:32px; border-bottom:1.5px solid var(--ink); }
  .brand { display:flex; align-items:center; gap:16px; }
  .brand svg { color:var(--ink); }
  h1 { font-size:40px; line-height:1; letter-spacing:-0.03em; font-weight:600; margin:0; }
  .kicker { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--mute); margin:0 0 14px; }
  .lede { margin:14px 0 0; font-size:15px; line-height:1.5; color:var(--mute); max-width:560px; }
  .spec { display:grid; grid-template-columns:repeat(3, auto); gap:0; border:1px solid var(--line); }
  .spec div { padding:12px 18px; border-right:1px solid var(--line); border-bottom:1px solid var(--line); }
  .spec div:nth-child(3n) { border-right:0; }
  .spec div:nth-last-child(-n+3) { border-bottom:0; }
  .spec dt { font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--mute); margin:0 0 4px; }
  .spec dd { margin:0; font-size:13px; font-weight:500; }
  .intro { display:grid; grid-template-columns: auto auto 1fr; gap:24px; margin:40px 0 8px; align-items:stretch; }
  .plate { border:1px solid var(--line); padding:20px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px; color:var(--ink); }
  .plate-label { font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--mute); }
  .principles { border:1px solid var(--line); padding:24px 28px; display:grid; grid-template-columns:1fr 1fr; gap:18px 32px; align-content:start; }
  .principles h3 { grid-column:1/-1; margin:0; font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:var(--mute); font-weight:500; }
  .principles p { margin:0; font-size:13.5px; line-height:1.5; }
  .principles b { display:block; font-weight:600; margin-bottom:2px; }
  .logo-sizes { grid-column:1/-1; display:flex; gap:28px; align-items:end; padding-top:14px; border-top:1px solid var(--line); }
  .logo-sizes figure { margin:0; display:flex; flex-direction:column; align-items:center; gap:8px; }
  .logo-sizes figcaption { font-size:11px; color:var(--mute); }
  .badge { width:56px; height:56px; background:var(--ink); color:#fff; display:grid; place-items:center;
           clip-path:polygon(10px 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px), 0 10px); }
  section { margin-top:40px; }
  h2 { display:flex; align-items:baseline; gap:12px; font-size:18px; font-weight:600; letter-spacing:-0.01em; margin:0 0 14px; }
  h2 .idx { font-family:"Geist Mono", ui-monospace, monospace; font-size:12px; color:var(--purple); font-weight:500; }
  h2 .count { margin-left:auto; font-size:12px; color:var(--mute); font-weight:400; font-family:"Geist Mono", ui-monospace, monospace; }
  .grid { display:grid; grid-template-columns:repeat(5, 1fr); border-top:1px solid var(--line); border-left:1px solid var(--line); }
  .cell { margin:0; border-right:1px solid var(--line); border-bottom:1px solid var(--line); padding:22px 18px 14px; display:flex; flex-direction:column; gap:16px; }
  .sizes { display:flex; align-items:center; justify-content:center; gap:26px; height:56px; color:var(--ink); }
  .s { display:grid; place-items:center; }
  .s48 { padding:3px; background:
         linear-gradient(var(--soft),var(--soft)); }
  figcaption { font-size:12.5px; font-weight:500; display:flex; justify-content:space-between; }
  .row { margin-top:40px; display:grid; grid-template-columns:1fr auto; gap:24px; align-items:stretch; }
  .panel { border:1px solid var(--line); padding:20px 24px; }
  .panel h3 { margin:0 0 14px; font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--mute); font-weight:500; display:flex; gap:10px; align-items:center; }
  .swatch { width:10px; height:10px; display:inline-block; }
  .purple { display:flex; flex-wrap:wrap; gap:14px 17px; color:var(--purple); }
  .nav { display:flex; gap:6px; margin-top:22px; padding-top:18px; border-top:1px solid var(--line); }
  .nav-i { display:inline-flex; align-items:center; gap:9px; height:38px; padding:0 14px 0 12px; font-size:13.5px; font-weight:500; color:var(--ink); }
  .nav-i.on { color:var(--purple); background:#F1ECFD; box-shadow:inset 2px 0 0 var(--purple); }
  .buttons { display:flex; flex-direction:column; gap:12px; align-items:flex-start; }
  .btn { display:inline-flex; align-items:center; gap:10px; height:44px; padding:0 20px 0 16px; background:var(--ink); color:#fff; font:600 14px/1 Geist, ui-sans-serif, system-ui, sans-serif; border:0; letter-spacing:-0.005em;
         clip-path:polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
  .btn.ghost { background:#fff; color:var(--ink); box-shadow:inset 0 0 0 1.5px var(--ink); }
  .btn.violet { background:var(--purple); }
  footer { margin-top:36px; padding-top:16px; border-top:1px solid var(--line); display:flex; justify-content:space-between; font-size:12px; color:var(--mute); }
</style>
</head>
<body>
<div class="page">
  <header>
    <div>
      <p class="kicker mono">Halberd / Interface iconography / v1.0</p>
      <div class="brand">${svg("HalberdMark", 44)}<h1>Halberd Icon Set</h1></div>
      <p class="lede">${ALL.length} stroke glyphs for an always-on guard that holds fraudulent vendor invoices. Cut corners instead of rounded ones: every bend is a 45° chamfer, like armor plate or a blade edge.</p>
    </div>
    <dl class="spec">
      <div><dt>Grid</dt><dd class="mono">24 × 24</dd></div>
      <div><dt>Live area</dt><dd class="mono">2 – 22</dd></div>
      <div><dt>Stroke</dt><dd class="mono">1.75</dd></div>
      <div><dt>Caps / joins</dt><dd class="mono">square / miter</dd></div>
      <div><dt>Corners</dt><dd class="mono">45° chamfer</dd></div>
      <div><dt>Colour</dt><dd class="mono">currentColor</dd></div>
    </dl>
  </header>

  <div class="intro">
    ${plate("HalberdMark", "Mark · construction")}
    ${plate("ShieldCheck", "Glyph · construction")}
    <div class="principles">
      <h3>Principles</h3>
      <p><b>Chamfer, never round</b>Outer corners cut at 2u, small parts at 1.5u. Diagonals run at 45° wherever the form allows.</p>
      <p><b>One weight</b>1.75 stroke at every size, square caps, mitred joins. No fills, no gradients, no glow.</p>
      <p><b>Solid notches</b>A filled rivet or notch only where it carries meaning: a pin-1 marker, an alert dot, a date.</p>
      <p><b>Colour by context</b>Ink #0E0D12 at rest, purple #5B2BE0 when active, white on solid buttons.</p>
      <div class="logo-sizes">
        <figure>${svg("HalberdMark", 16)}<figcaption>16</figcaption></figure>
        <figure>${svg("HalberdMark", 24)}<figcaption>24</figcaption></figure>
        <figure>${svg("HalberdMark", 32)}<figcaption>32</figcaption></figure>
        <figure>${svg("HalberdMark", 48)}<figcaption>48</figcaption></figure>
        <figure><div class="badge">${svg("HalberdMark", 32)}</div><figcaption>badge</figcaption></figure>
        <figure style="color:var(--purple)">${svg("HalberdMark", 32)}<figcaption>active</figcaption></figure>
      </div>
    </div>
  </div>
${sections}

  <div class="row">
    <div class="panel">
      <h3><span class="swatch" style="background:var(--purple)"></span>Active state · #5B2BE0 · 24px</h3>
      <div class="purple">${purpleRow}</div>
      <nav class="nav">${navItems}</nav>
    </div>
    <div class="panel">
      <h3><span class="swatch" style="background:var(--ink)"></span>On solid · 20px</h3>
      <div class="buttons">
        <button class="btn">${svg("Pause", 20)}Hold payment</button>
        <button class="btn violet">${svg("PhoneCall", 20)}Call number on file</button>
        <button class="btn">${svg("ShieldCheck", 20)}Mark verified</button>
      </div>
    </div>
  </div>

  <footer><span class="mono">web/src/icons/index.tsx</span><span>Each icon at 16 · 24 · 48 px</span></footer>
</div>
</body>
</html>
`;
writeFileSync(`${OUT}/preview.html`, html);
console.log("icons:", ALL.length);
