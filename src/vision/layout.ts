// Read where each piece of text sits on an invoice PDF, and render pages to PNG with circles.
// Positions come from the PDF itself, so the circles land exactly on the changed text: no model guessing.
import "./polyfill.js"; // must run before pdf.js loads (DOMMatrix/Path2D/ImageData for rendering)
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { createCanvas } from "@napi-rs/canvas";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";

// The demo PDFs use the standard 14 fonts without embedding them; pdf.js needs its own copies to draw text.
const FONTS = join(dirname(createRequire(import.meta.url).resolve("pdfjs-dist/package.json")), "standard_fonts") + "/";

/** One text item, in PDF points with the origin at the bottom-left of the page. */
export interface TextBox { text: string; page: number; x: number; y: number; w: number; h: number }
export interface Layout { pages: { width: number; height: number }[]; items: TextBox[] }

/** A spot to circle on the new invoice. */
export interface Region {
  page: number; x: number; y: number; w: number; h: number;   // PDF points, bottom-left origin
  label: string;                                              // e.g. "Bank changed"
  severity: "high" | "medium" | "low";
  approximate?: boolean;                                      // true when the box came from the model, not the PDF
}

function open(path: string) {
  return getDocument({ data: new Uint8Array(readFileSync(path)), verbosity: 0, isEvalSupported: false,
                       standardFontDataUrl: FONTS }).promise;
}

export async function readLayout(path: string): Promise<Layout> {
  const doc = await open(path);
  const pages: Layout["pages"] = [];
  const items: TextBox[] = [];
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const [, , width, height] = page.view;
    pages.push({ width, height });
    const content = await page.getTextContent();
    for (const it of content.items as any[]) {
      if (!it.str?.trim()) continue;
      const [a, b, , , e, f] = it.transform;
      const size = Math.hypot(a, b) || it.height || 10;
      items.push({ text: it.str, page: p, x: e, y: f - size * 0.25, w: it.width, h: size * 1.2 });
    }
  }
  await doc.destroy();
  return { pages, items };
}

/** One box per label: "Bank changed" covers the bank name, routing and account lines together. */
export function mergeRegions(regions: Region[]): Region[] {
  const out = new Map<string, Region>();
  for (const r of regions) {
    const key = `${r.page}|${r.label}|${r.severity}|${r.approximate ? 1 : 0}`;
    const m = out.get(key);
    if (!m) { out.set(key, { ...r }); continue; }
    const x = Math.min(m.x, r.x), y = Math.min(m.y, r.y);
    m.w = Math.max(m.x + m.w, r.x + r.w) - x;
    m.h = Math.max(m.y + m.h, r.y + r.h) - y;
    m.x = x; m.y = y;
  }
  return [...out.values()];
}

/** Render one page to PNG. scale 2 ≈ 144 dpi: sharp for people, small enough for the model. */
export async function renderPage(path: string, pageNo = 1, scale = 2, regions: Region[] = []): Promise<Buffer> {
  const doc = await open(path);
  const page = await doc.getPage(pageNo);
  const vp = page.getViewport({ scale });
  const canvas = createCanvas(Math.ceil(vp.width), Math.ceil(vp.height));
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx as any, viewport: vp }).promise;

  const color = { high: [211, 47, 47], medium: [239, 108, 0], low: [123, 31, 162] } as const;
  const rgba = (c: readonly number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  for (const r of mergeRegions(regions.filter((r) => r.page === pageNo))) {
    const [x1, y1] = vp.convertToViewportPoint(r.x - 3, r.y + r.h + 1.5);   // top-left in pixels
    const [x2, y2] = vp.convertToViewportPoint(r.x + r.w + 3, r.y - 1.5);   // bottom-right in pixels
    const c = color[r.severity];
    ctx.fillStyle = rgba(c, 0.12);                                           // highlighter, text stays readable
    ctx.beginPath();
    ctx.roundRect(x1, y1, x2 - x1, y2 - y1, 4 * scale);
    ctx.fill();
    ctx.strokeStyle = rgba(c, 1);
    ctx.lineWidth = 1.8 * scale;
    ctx.setLineDash(r.approximate ? [5 * scale, 3 * scale] : []);
    ctx.stroke();
    ctx.setLineDash([]);
    // Label to the right of the box; above it if the page edge is in the way.
    ctx.font = `bold ${7.5 * scale}px sans-serif`;
    const tw = ctx.measureText(r.label).width;
    const right = x2 + 6 * scale + tw < canvas.width - 4;
    const lx = right ? x2 + 6 * scale : Math.max(4, x2 - tw), ly = right ? (y1 + y2) / 2 + 3 * scale : y1 - 4 * scale;
    ctx.fillStyle = rgba(c, 1);
    ctx.fillText(r.label, lx, ly);
  }
  await doc.destroy();
  return canvas.toBuffer("image/png");
}
