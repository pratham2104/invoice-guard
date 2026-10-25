// Read an invoice PDF: all text (for field checks) plus any text a person can't see
// (tiny, white-on-white, invisible render mode, off-page) — the prompt-injection hiding spots.
import { readFileSync } from "node:fs";
import { getDocument, OPS } from "pdfjs-dist/legacy/build/pdf.mjs";

export interface TextRun { text: string; x: number; y: number; size: number; rgb: [number, number, number]; renderMode: number; page: number }
export interface HiddenRun extends TextRun { reasons: string[] }
export interface PdfScan { text: string; runs: TextRun[]; hidden: HiddenRun[] }

const TINY_PT = 4;

function isNearWhite([r, g, b]: [number, number, number]) {
  return r > 235 && g > 235 && b > 235;
}

interface FilledRect { x: number; y: number; w: number; h: number; rgb: [number, number, number] }

export async function scanPdf(path: string): Promise<PdfScan> {
  const data = new Uint8Array(readFileSync(path));
  const doc = await getDocument({ data, verbosity: 0, isEvalSupported: false }).promise;
  const runs: TextRun[] = [];
  const hidden: HiddenRun[] = [];

  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const [, , pw, ph] = page.view;
    const ops = await page.getOperatorList();
    let rgb: [number, number, number] = [0, 0, 0];
    let size = 12, x = 0, y = 0, renderMode = 0;
    let pendingRects: { x: number; y: number; w: number; h: number }[] = [];
    const rects: FilledRect[] = [];
    const pageRuns: TextRun[] = [];

    for (let i = 0; i < ops.fnArray.length; i++) {
      const fn = ops.fnArray[i];
      const args = ops.argsArray[i] as any;
      switch (fn) {
        case OPS.setFillRGBColor: rgb = [args[0], args[1], args[2]]; break;
        case OPS.setFillGray: { const g = Math.round(args[0] * 255); rgb = [g, g, g]; break; }
        case OPS.setFont: size = Math.abs(args[1]); break;
        case OPS.beginText: x = 0; y = 0; break;
        case OPS.moveText: x += args[0]; y += args[1]; break;
        case OPS.setTextMatrix: x = args[4]; y = args[5]; size = size * Math.hypot(args[0], args[1]); break;
        case OPS.setTextRenderingMode: renderMode = args[0]; break;
        case OPS.constructPath: {
          const [subOps, coords] = args as [number[], number[]];
          let k = 0;
          for (const op of subOps) {
            if (op === OPS.rectangle) { pendingRects.push({ x: coords[k], y: coords[k + 1], w: coords[k + 2], h: coords[k + 3] }); k += 4; }
            else if (op === OPS.moveTo || op === OPS.lineTo) k += 2;
            else if (op === OPS.curveTo) k += 6;
            else if (op === OPS.curveTo2 || op === OPS.curveTo3) k += 4;
          }
          break;
        }
        case OPS.fill: case OPS.eoFill:
          for (const r of pendingRects) rects.push({ ...r, rgb: [...rgb] as [number, number, number] });
          pendingRects = [];
          break;
        case OPS.stroke: case OPS.endPath: pendingRects = []; break;
        case OPS.showText: case OPS.nextLineShowText: case OPS.nextLineSetSpacingShowText: {
          const glyphs = (fn === OPS.showText ? args[0] : args[args.length - 1]) as any[];
          const text = glyphs.map((g) => (typeof g === "object" && g ? g.unicode ?? "" : "")).join("");
          if (text.trim()) pageRuns.push({ text, x, y, size, rgb: [...rgb] as [number, number, number], renderMode, page: p });
          break;
        }
      }
    }

    for (const run of pageRuns) {
      runs.push(run);
      const reasons: string[] = [];
      if (run.size < TINY_PT) reasons.push(`tiny font (${run.size}pt)`);
      if (run.renderMode === 3) reasons.push("invisible render mode");
      if (run.x < 0 || run.y < 0 || run.x > pw || run.y > ph) reasons.push("positioned off the page");
      if (isNearWhite(run.rgb)) {
        // white text is fine on a dark filled box (e.g. a logo); suspicious on the bare page
        const onDarkBox = rects.some((r) => !isNearWhite(r.rgb) && run.x >= r.x && run.x <= r.x + r.w && run.y >= r.y && run.y <= r.y + r.h);
        if (!onDarkBox) reasons.push("white text on a white page");
      }
      if (reasons.length) hidden.push({ ...run, reasons });
    }
  }
  await doc.destroy();
  return { text: runs.map((r) => r.text).join("\n"), runs, hidden };
}
