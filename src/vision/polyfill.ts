// pdf.js needs browser drawing classes to render in Node. Provide them from @napi-rs/canvas
// (prebuilt for macOS and linux-arm64, so nothing compiles on the GB10).
import { DOMMatrix, ImageData, Path2D } from "@napi-rs/canvas";

const g = globalThis as any;
g.DOMMatrix ??= DOMMatrix;
g.ImageData ??= ImageData;
g.Path2D ??= Path2D;
