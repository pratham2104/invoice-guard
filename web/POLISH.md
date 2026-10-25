# Halberd dashboard: polish spec

Owner: tyler-3 (design). Applies to `web/` only. It changes how things look, never what they do.
Class names match tyler-2's rebuild as of 15:20 (`App.tsx`, `Sidebar.tsx`, `CaseMain.tsx`, `Paper.tsx`,
`InvoiceMain.tsx`). If a name moves, keep the treatment.

The screen is judged in a 2-minute screen recording at 1600×1000. Anyone watching should be able to
read three things without pausing: **what Halberd held, why, and what a person does next.** Every rule
below serves that.

---

## 0. What we took from the references

| Reference | Trait | How Halberd uses it |
|---|---|---|
| Pitch (editor) | White work sits on a light grey canvas, like a slide on a desk. Chrome stays white and quiet. | Top bar and sidebar are white, the main area is a grey canvas, and cards are white on top of it. Invoices sit in a sunken well as paper sheets. |
| Pitch (marketing) | Tight display tracking (−0.04em at 48px, −0.02em on body), body line-height 1.6, 150ms transitions. | Negative tracking that scales with size; generous line-height on the one sentence that matters. |
| Mercury (demo app) | Weight 360–400 body text, hairlines at `rgba(112,115,147,.22)`, selected nav `rgba(112,115,147,.10)` at 8px radius, every hover at `160ms ease-out`, smaller cents (`$213.11`), a struck-through amount for a failed payment. | Faint selection tints instead of boxes, smaller cents on the headline amount, a struck amount on stopped payments, one 160ms hover curve everywhere. |
| Linear | Sidebar rows 28–32px with 8px radius, weight 510, sentence-case group labels in the tertiary grey, the main panel raised one step from the frame. | Sidebar groups (Held, Stopped, Cleared) as quiet labels, rows that tint rather than outline, the main area one tone off the chrome. |
| Halberd icon set | 1.75 stroke, square caps, 45° chamfers, `currentColor`. | Small radii (paper 3px, cards 10px), square risk markers, icons always in the grey of the text beside them. |

Taken together, the page should look like a calm ledger, with color used only as an alarm.

---

## 1. Tokens

Replace the whole `:root` block in `styles.css`. **Delete `--purple*`, `--ok*` and `--black-hover`.**
No other hue exists in the UI.

```css
:root {
  /* surfaces */
  --canvas: #f6f6f5;          /* main area behind the cards */
  --surface: #ffffff;         /* top bar, sidebar, cards, paper */
  --sunken: #f1f1ef;          /* the well the invoice papers sit in */
  --subtle: #fafaf9;          /* pay-to block inside a paper, button hover */

  /* ink */
  --ink: #111111;
  --ink-2: #4f5157;           /* secondary text, 8.1:1 on white */
  --ink-3: #74767c;           /* metadata, 4.6:1 on white: the floor for text */
  --ink-4: #b4b5b8;           /* icons at rest, disabled, arrows. Never body text */

  /* lines + states (alpha so they read on white and on canvas) */
  --line: rgba(15, 15, 15, 0.08);
  --line-2: rgba(15, 15, 15, 0.14);
  --hover: rgba(15, 15, 15, 0.035);
  --selected: rgba(15, 15, 15, 0.06);

  /* risk: the only color */
  --fraud: #c8261b;
  --fraud-tint: #fcf1f0;
  --fraud-line: rgba(200, 38, 27, 0.28);
  --confirm: #a15c07;
  --confirm-tint: #fbf5eb;
  --confirm-line: rgba(161, 92, 7, 0.28);

  /* depth */
  --shadow-card: 0 0 0 1px rgba(15, 15, 15, 0.06), 0 1px 2px rgba(15, 15, 15, 0.04);
  --shadow-paper: 0 0 0 1px rgba(15, 15, 15, 0.05), 0 1px 1px rgba(15, 15, 15, 0.03),
                  0 6px 16px -6px rgba(15, 15, 15, 0.10), 0 18px 36px -18px rgba(15, 15, 15, 0.10);
  --shadow-pop: 0 0 0 1px rgba(15, 15, 15, 0.06), 0 10px 28px -6px rgba(15, 15, 15, 0.18);
  --shadow-btn: 0 0 0 1px rgba(15, 15, 15, 0.12), 0 1px 2px rgba(15, 15, 15, 0.05);
  --shadow-btn-primary: 0 0 0 1px #111111, inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
  --ring: 0 0 0 2px #ffffff, 0 0 0 4px #111111;

  /* radii */
  --r-paper: 3px;
  --r-xs: 4px;     /* field highlight, pill */
  --r-sm: 6px;     /* buttons, pills */
  --r: 8px;        /* sidebar rows, wells */
  --r-lg: 10px;    /* cards */

  /* motion */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --t-hover: 120ms;
  --t-state: 200ms;
  --t-enter: 320ms;

  /* type */
  --sans: "Geist Variable", "Geist", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --mono: "Geist Mono Variable", "Geist Mono", ui-monospace, "SF Mono", Menlo, monospace;
  color-scheme: light;
}
```

Spacing runs on a 4px base: **4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48**. Use no other values except the
optical nudges named below.

---

## 2. Type

The fonts are Geist (sans) and Geist Mono. Only three weights are used: 400, 500 and 600. **No 700.**
Nothing is smaller than 12px, because the screen is shown in a video.

| Role | Size / line | Weight | Tracking | Color |
|---|---|---|---|---|
| Vendor name (`h1`) | 28 / 34 | 600 | −0.022em | ink |
| Headline amount (`.head-amt`) | 32 / 36 | 600 | −0.02em | tone (open) or ink |
| "Why" sentence (`.lead` in the split card) | 18 / 28 | 400 | −0.011em | ink |
| Card title (`h2`) | 13 / 18 | 600 | 0 | ink-2 |
| Next-step title (`.next-title`) | 16 / 24 | 600 | −0.011em | ink |
| Body | 14 / 20 | 400 | −0.006em | ink |
| Small / meta | 13 / 18 | 400 | 0 | ink-3 |
| Micro (captions, column heads, counts) | 12 / 16 | 500 | +0.005em | ink-3 |
| Phone number | 22 / 28 mono | 500 | 0 | ink |

```css
body {
  font: 400 14px/20px var(--sans);
  letter-spacing: -0.006em;
  color: var(--ink);
  background: var(--canvas);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  font-feature-settings: normal;          /* remove the global "tnum": tabular digits look clumsy in prose */
}
.mono {
  font-family: var(--mono);
  font-size: 0.93em;                       /* optical match: Geist Mono reads ~7% larger than Geist */
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}
.num { font-variant-numeric: tabular-nums; }  /* any sans number that stacks in a column */
h1, h2, p { margin: 0; }
p, li, .lead { text-wrap: pretty; }
h1 { text-wrap: balance; }
```

**Mono is for identifiers only:** invoice numbers, account and routing last-4, phone numbers, sender
domains and email addresses. Mono is also the right face for the homoglyph case: `acme-supp1y.com`
in Geist Mono shows the `1` plainly. Amounts use Geist with tabular figures, except inside the invoice
papers, where mono gives the ledger feel.

**Number formatting**
- **Headline amount:** show smaller cents. `$4,200` at 32px, then `.00` at `0.56em`, weight 500, raised
  with `vertical-align: 0.62em`, and `margin-left: 1px`. Mercury does this, and it makes a large number
  look deliberate rather than printed.
- **Masked digits:** use `••3378` with two bullets. Set the bullets at 0.8em with letter-spacing 0.05em
  so they don't crowd the digits (`.mask { font-size: .8em; letter-spacing: .05em; margin-right: 1px }`).
- **Dates:** never show an ISO date such as `2026-10-14`. Format it as `Oct 14` (or `Oct 14, 2026` when
  the year differs). This currently leaks through the "Billing day" change row.

---

## 3. Layout at 1600×1000

```
┌──────────────────────────────────────────────────────────────── 52px top bar (white) ─┐
│ [mark] Halberd │ School District                                                          │
├──────────── 336px sidebar (white) ─┬──────────── main: canvas #f6f6f5 ─────────────────┤
│ Held 4                              │      ┌─ column max 880px, centered ───────────┐   │
│  rows…                              │      │ header (on canvas, no card)            │   │
│ Cleared 27                          │      │ card: Why Halberd held it | What it did│   │
│  rows…                              │      │ card: What changed                     │   │
│                                     │      │ card: Invoice (papers in sunken well)  │   │
│                                     │      │ card: Next step                        │   │
└─────────────────────────────────────┴──────┴────────────────────────────────────────┴───┘
```

```css
.app  { height: 100%; display: grid; grid-template-rows: 52px 1fr; }
.body { display: grid; grid-template-columns: 336px 1fr; min-height: 0; }
.side { background: var(--surface); border-right: 1px solid var(--line); overflow-y: auto; padding-bottom: 24px; }
.main { overflow-y: auto; padding: 32px 48px 80px; scroll-padding-top: 32px; }
.stack { max-width: 880px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.side, .main { scrollbar-width: thin; scrollbar-color: rgba(15,15,15,.16) transparent; }
```

---

## 4. Top bar

The bar holds exactly two things: the mark with the name, and the org. Nothing else goes in it.

```css
.top { display: flex; align-items: center; gap: 12px; padding: 0 20px; background: var(--surface);
       border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 8px; font: 600 15px/20px var(--sans); letter-spacing: -0.012em; }
.brand svg { color: var(--ink); }                         /* mark at 20px, not 22 */
.org { display: flex; align-items: center; gap: 12px; color: var(--ink-2); font-size: 14px; }
.org::before { content: ""; width: 1px; height: 16px; background: var(--line-2); }
```

**Optical alignment:** the mark's left edge sits at x=20, the same x as the text in every sidebar row
(8px row inset + 12px row padding). The vertical seam from the top bar to the first row then reads as
one line.

---

## 5. Sidebar

### Group label (`.side-label`)
```css
.side-sec + .side-sec { margin-top: 8px; }
.side-label { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px;
  padding: 16px 20px 8px; font: 500 12px/16px var(--sans); letter-spacing: .005em; color: var(--ink-3);
  background: rgba(255,255,255,.92); backdrop-filter: blur(8px); }
.side-label svg { color: var(--ink-4); }
.side-count { margin-left: auto; color: var(--ink-4); font-variant-numeric: tabular-nums; }
```
The labels stay in sentence case: "Held", "Stopped", "Cleared". **No uppercase.**

### Row anatomy (`.srow`)
```
 ┌ 8px inset ─────────────────────────────────────────── radius 8 ┐
 │ 12px  Acme School Supply              ■  $4,200.00   12px      │  name 14/20 500 ink · amount 14/20 mono 500 ink
 │       ACME-1052 · 3:14 PM                                       │  sub 12/16 ink-3 · id in mono
 └────────────────────────────────────────────────── min-h 56px ──┘
```
```css
.srow { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px;
  width: calc(100% - 16px); margin: 0 8px; min-height: 56px; padding: 10px 12px;
  border: 0; border-radius: var(--r); background: transparent; text-align: left; cursor: pointer;
  transition: background-color var(--t-hover) ease-out; }
.srow + .srow { margin-top: 2px; }
.srow-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.srow-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srow-sub { font-size: 12px; line-height: 16px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srow-amt { display: flex; align-items: center; gap: 8px; font-weight: 500; color: var(--ink); }
.srow-amt .mono { font-size: 13px; }
.srow-bank { font-size: 13px; color: var(--ink-2); font-weight: 400; }
```

| State | Treatment |
|---|---|
| default | transparent |
| hover | `background: var(--hover)` |
| selected (`.on`) | `background: var(--selected); box-shadow: inset 0 0 0 1px rgba(15,15,15,.04)` |
| focus-visible | `outline: none; box-shadow: inset 0 0 0 2px var(--ink)` |
| active (mouse down) | `background: rgba(15,15,15,.08)` |

**Risk marker (`.mk`):** an 8px square with a 2px radius. It echoes the square caps of the icon set and
sits before the amount. The marker carries the color; **the amount stays ink**. A list of red numbers
shouts, while a red square next to a black number reads as a flag.
```css
.mk { position: relative; flex: none; width: 8px; height: 8px; border-radius: 2px; background: currentColor; }
.srow-amt.fraud .mk, .mk.fraud { color: var(--fraud); }
.srow-amt.confirm .mk, .mk.confirm { color: var(--confirm); }
.srow-amt.fraud, .srow-amt.confirm { color: var(--ink); }   /* tone is on the marker, not the number */
```

**Stopped rows:** the name is ink-2 and the amount is ink-3, struck through with
`text-decoration: line-through; text-decoration-thickness: 1px; text-decoration-color: var(--ink-4)`.
That reads as a payment that never went out. **Cleared rows:** use `min-height: 48px` and an ink-2
amount. There are 27 of them, and they should read as calm history below the held rows.

### New invoice arriving (`.srow.fresh`, the signature moment)

The motion should feel alive but calm: one breath, never a flash. `fresh` is set for 2400ms and the row
is auto-selected, so every animation here finishes within **2200ms** and ends on the selected state.

1. **0–360ms. The row opens its own space.** The rows below slide down, rather than jumping, as the new
   row's height grows from 0.
2. **120–480ms. The content fades up 4px** inside that space.
3. **360–2200ms. A tint washes out.** The row starts at its risk tint (`--fraud-tint` or
   `--confirm-tint`) and settles to `--selected`.
4. **400–2000ms. The marker breathes twice.** A 1.5px ring in the risk color scales 1 → 2.2 while
   fading 0.5 → 0.
5. **The detail pane** runs the normal enter (section 11) at the same moment, so the row and its story
   arrive together.

```css
@keyframes srow-open { from { max-height: 0; min-height: 0; padding-block: 0; margin-top: 0; } to { max-height: 72px; } }
@keyframes srow-rise { from { opacity: 0; transform: translateY(-4px); } }
@keyframes srow-wash-fraud   { from { background-color: var(--fraud-tint); } }
@keyframes srow-wash-confirm { from { background-color: var(--confirm-tint); } }
@keyframes mk-breathe { 0% { opacity: .5; transform: scale(1); } 100% { opacity: 0; transform: scale(2.2); } }

.srow.fresh { overflow: hidden; animation: srow-open 360ms var(--ease-out) both; }
.srow.fresh > * { animation: srow-rise 360ms var(--ease-out) 120ms both; }
.srow.fresh:has(.srow-amt.fraud)   { animation: srow-open 360ms var(--ease-out) both, srow-wash-fraud 1840ms ease-out 360ms both; }
.srow.fresh:has(.srow-amt.confirm) { animation: srow-open 360ms var(--ease-out) both, srow-wash-confirm 1840ms ease-out 360ms both; }
.srow.fresh .mk::after { content: ""; position: absolute; inset: -1px; border-radius: 3px;
  border: 1.5px solid currentColor; opacity: 0; animation: mk-breathe 800ms var(--ease-out) 400ms 2; }
```
The wash keyframes have only a `from` step, so each animates to whatever background the row already
has (selected or transparent), and removing `fresh` never snaps.

**Group count:** give `.side-count` `key={rows.length}` so it remounts when the number changes, and fade
it in: `@keyframes count-in { from { opacity: 0; transform: translateY(-3px); } }` at
`240ms var(--ease-out)`. This is the one JSX change in the sidebar.

---

## 6. Header (`.card.head`)

The header is **not a card**. It sits directly on the canvas, like a slide title above the slide.

```
[■ Fraud risk]                                              $8,940.00
Acme School Supply                                        (tone color while held)
ACME-1052 · Oct 14, 2026 · Payment held
```
```css
.card.head { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px;
  background: none; box-shadow: none; padding: 8px 4px 16px; }
.head-l { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.head-sub { font-size: 13px; line-height: 18px; color: var(--ink-3); }
.head-amt { font: 600 32px/36px var(--sans); letter-spacing: -0.02em; font-variant-numeric: tabular-nums;
  white-space: nowrap; color: var(--ink); }
.head-amt.fraud { color: var(--fraud); } .head-amt.confirm { color: var(--confirm); }
.head-bank { font: 500 20px/28px var(--sans); color: var(--ink-2); letter-spacing: -0.01em; }
```

**Risk pill.** Recommended JSX reorder: move the risk word *above* the `h1` as a pill, and fold "Payment
held" into `.head-sub`. A viewer reads the risk first, then the vendor.
```css
.pill { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; height: 24px; padding: 0 8px;
  border-radius: var(--r-sm); font: 500 12px/16px var(--sans); letter-spacing: .005em; }
.pill.fraud   { color: var(--fraud);   background: var(--fraud-tint);   box-shadow: inset 0 0 0 1px var(--fraud-line); }
.pill.confirm { color: var(--confirm); background: var(--confirm-tint); box-shadow: inset 0 0 0 1px var(--confirm-line); }
.pill .mk { width: 6px; height: 6px; border-radius: 1.5px; }
```
Once a case is resolved, drop the pill and turn the amount ink. For a stopped payment, strike the
headline amount the same way as the sidebar (thickness 2px, color `--ink-4`).

---

## 7. Cards (shared)

```css
.card { background: var(--surface); border-radius: var(--r-lg); box-shadow: var(--shadow-card); padding: 24px 28px; }
.card h2 { font: 600 13px/18px var(--sans); color: var(--ink-2); margin-bottom: 12px; }
.quiet { font-size: 13px; line-height: 18px; color: var(--ink-3); }
```
The card has no border on top of its shadow: the 1px ring in `--shadow-card` *is* the border. A card is
never tinted red or amber.

### "Why Halberd held it" + "What Halberd did" (`.card.split`)
```css
.card.split { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: 0; padding: 0; }
.card.split > div { padding: 24px 28px; }
.card.split > div + div { border-left: 1px solid var(--line); }
.card.split .lead { font-size: 18px; line-height: 28px; letter-spacing: -0.011em; max-width: 46ch; }
.did { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.did li { position: relative; padding-left: 22px; color: var(--ink-2); }
.did li::before { content: ""; position: absolute; left: 3px; top: 7px; width: 6px; height: 6px;
  border-radius: 1.5px; background: var(--ink-4); }
```
The "why" sentence is the sentence the demo is built around: it is the largest body text on the page,
in ink, with nothing else beside it on its side of the card.

### "What changed" (`.chg-*`)
```
              Usually                          This time
Sender        acme-supply.com           →      acme-supp1y.com        ← tone, 500
Bank account  First Valley Bank ••3378  →      Pacific Coast ••9921
```
```css
.chg-head, .chg-row { display: grid; grid-template-columns: 148px minmax(0,1fr) 24px minmax(0,1fr); gap: 16px; align-items: baseline; }
.chg-head { padding-bottom: 8px; font: 500 12px/16px var(--sans); color: var(--ink-3); }
.chg-row { padding: 14px 0; border-top: 1px solid var(--line); }
.chg-label { font-size: 13px; color: var(--ink-3); }
.chg-was { color: var(--ink-2); }
.chg-arrow { color: var(--ink-4); align-self: center; display: flex; }
.chg-now { font-weight: 500; color: var(--ink); }
.chg-now.fraud { color: var(--fraud); } .chg-now.confirm { color: var(--confirm); }
```
Any value that is a domain, an email address or a masked account goes in `.mono`, so lookalike letters
read plainly (a small render helper: wrap when `/@|\.[a-z]{2,}\b|••/i` matches). The last row has no
bottom border. Cap the table at three rows, which is what `changes()` already does.

---

## 8. Invoice papers (`.papers`, `.paper`)

Invoices look like paper on a desk: white sheets with a real shadow, sitting in a sunken well. This is
the Pitch move, and the one that most separates the page from a generic admin panel.

```css
.papers { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; padding: 24px; margin: 4px -12px -8px;
  background: var(--sunken); border-radius: var(--r); }
.papers.one { grid-template-columns: minmax(0, 420px); justify-content: center; }
.paper-wrap { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.paper-cap { display: flex; justify-content: space-between; align-items: baseline; padding: 0 2px;
  font: 500 12px/16px var(--sans); color: var(--ink-3); }
.pdf { color: var(--ink-2); text-decoration: none; display: inline-flex; gap: 4px; align-items: center; }
.pdf:hover { color: var(--ink); text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; }
.paper { background: var(--surface); border-radius: var(--r-paper); box-shadow: var(--shadow-paper);
  padding: 24px 24px 20px; font-size: 13px; line-height: 20px; }
.paper-head { display: flex; justify-content: space-between; align-items: baseline; padding-bottom: 12px;
  margin-bottom: 8px; border-bottom: 1px solid var(--line); }
.paper-head .mono { font-weight: 500; color: var(--ink); }
.muted { color: var(--ink-3); }
.pl { display: grid; grid-template-columns: 1fr auto; gap: 16px; padding: 4px 0; color: var(--ink-2); }
.pl-d { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-a { color: var(--ink); }
.paper-total { display: flex; justify-content: space-between; align-items: baseline; margin-top: 8px; padding-top: 10px;
  border-top: 1px solid var(--ink); font-weight: 600; font-size: 14px; }  /* ink rule above the total, like printed invoices */
.payto { margin-top: 16px; padding: 12px 14px; background: var(--subtle); border-radius: var(--r-xs);
  box-shadow: inset 0 0 0 1px var(--line); display: grid; gap: 4px; }
.pt { display: grid; grid-template-columns: 72px minmax(0,1fr); gap: 12px; }
```

**Marking changed fields (`.fld.chg`).** Use a thin tinted box hung outside the text, so marking a field
never moves it. The negative margin cancels the padding, so the value stays aligned with the same field
on the other paper.
```css
.fld { border-radius: var(--r-xs); }
.fld.chg { padding: 1px 5px; margin: -1px -5px; font-weight: 500; }
.fld.chg.fraud   { color: var(--fraud);   background: var(--fraud-tint);   box-shadow: inset 0 0 0 1px var(--fraud-line); }
.fld.chg.confirm { color: var(--confirm); background: var(--confirm-tint); box-shadow: inset 0 0 0 1px var(--confirm-line); }
.fld.chg .mono { color: inherit; }
```
"This invoice" sits a fraction above "Last real invoice":
`.paper-wrap:last-child .paper { transform: translateY(-2px); }`, with its caption in ink-2. The old
invoice stays as the quieter reference.

**Bank change, no invoice (`.tiles`).** Use the same well and paper treatment: two slips with an arrow
between them.
```css
.tiles { display: grid; grid-template-columns: 1fr 40px 1fr; align-items: center; padding: 24px; margin: 4px -12px -8px;
  background: var(--sunken); border-radius: var(--r); }
.tile { background: var(--surface); border-radius: var(--r-paper); box-shadow: var(--shadow-paper); padding: 20px 24px; }
.tile-cap { font: 500 12px/16px var(--sans); color: var(--ink-3); }
.tile-num { font-size: 24px; line-height: 32px; font-weight: 500; margin-top: 8px; }
.tile-num.fraud { color: var(--fraud); } .tile-num.confirm { color: var(--confirm); }
.tile.chg.fraud { box-shadow: var(--shadow-paper), inset 0 0 0 1px var(--fraud-line); }
.tile.chg.confirm { box-shadow: var(--shadow-paper), inset 0 0 0 1px var(--confirm-line); }
.tile-sub { font-size: 13px; color: var(--ink-2); margin-top: 2px; }
.tile-arrow { color: var(--ink-4); display: flex; justify-content: center; }
```

---

## 9. Next step (`.card.next`)

This is the only place on the page with a black button that does something. Its content lands in a
fixed order: what to do, the number to use, the one caveat, then the answers.
```css
.next-title { display: flex; align-items: center; gap: 10px; font: 600 16px/24px var(--sans); letter-spacing: -0.011em; }
.next-title svg { color: var(--ink-2); }
.phone { font-size: 22px; line-height: 28px; font-weight: 500; margin: 12px 0 2px 30px; }  /* 30px = icon 20 + gap 10: aligns under the title text */
.next .quiet { margin-left: 30px; }
.msg { margin: 12px 0 0 30px; padding: 12px 16px; border-left: 2px solid var(--line-2); background: var(--subtle);
  border-radius: 0 var(--r-xs) var(--r-xs) 0; color: var(--ink-2); font-size: 13px; line-height: 20px; max-width: 60ch; }
.btns { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0 0 30px; }
.btns.tight { margin: 0; }
.release { display: flex; justify-content: space-between; align-items: center; gap: 16px;
  margin: 24px -28px -24px; padding: 16px 28px; border-top: 1px solid var(--line);
  background: var(--subtle); border-radius: 0 0 var(--r-lg) var(--r-lg); }
```
The `.release` strip is a footer to the card, not a second card. The resolved states ("Released",
"Stopped") use the same card with only the `h2` and one `.lead` line at 16px.

---

## 10. Buttons

```css
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 36px; padding: 0 14px;
  border: 0; border-radius: var(--r-sm); background: var(--surface); color: var(--ink); box-shadow: var(--shadow-btn);
  font: 500 14px/20px var(--sans); letter-spacing: -0.006em; cursor: pointer; white-space: nowrap;
  transition: background-color var(--t-hover) ease-out, box-shadow var(--t-hover) ease-out, transform 80ms ease-out, color var(--t-state) ease-out; }
.btn:hover { background: var(--subtle); box-shadow: 0 0 0 1px rgba(15,15,15,.18), 0 1px 2px rgba(15,15,15,.06); }
.btn:active { transform: translateY(0.5px); background: #f3f3f2; }
.btn.primary { background: #111; color: #fff; box-shadow: var(--shadow-btn-primary); }
.btn.primary:hover { background: #262626; }
.btn.primary:active { background: #000; }
.btn:focus-visible { outline: none; box-shadow: var(--ring); }
.btn:disabled { cursor: not-allowed; transform: none; background: #f3f3f2; color: var(--ink-4); box-shadow: inset 0 0 0 1px var(--line); }
.btn svg { width: 16px; height: 16px; }
```
When Approve unlocks (READY_FOR_APPROVAL), it shifts from grey to black over `--t-state`. That change is
the reward beat in the demo, so leave it on the transition and don't add anything on top. Buttons in a
busy state keep their label; there are no spinners.

Global focus ring: `:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }`. It is ink,
never a color.

---

## 11. Moving between invoices (`.enter`)

`.enter` is keyed by `selectedId`, so this runs when a different invoice is chosen. It does **not** run on
background refreshes (keep it that way: never key it by `detail`).
```css
@keyframes enter { from { opacity: 0; transform: translateY(6px); } }
.enter .stack > * { animation: enter var(--t-enter) var(--ease-out) both; }
.enter .stack > *:nth-child(2) { animation-delay: 40ms; }
.enter .stack > *:nth-child(3) { animation-delay: 80ms; }
.enter .stack > *:nth-child(4) { animation-delay: 120ms; }
.enter .stack > *:nth-child(n+5) { animation-delay: 160ms; }
.fade { animation: fade var(--t-state) ease-out both; }
@keyframes fade { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 1ms !important; animation-delay: 0ms !important; transition-duration: 1ms !important; }
}
```
On select, also reset the main column to the top (`.main` `scrollTop = 0`). Without it, switching from a
long case leaves the next one scrolled to its middle.

---

## 12. Loading and empty

- **Loading (`!loaded`).** Show a skeleton instead of `null`. The sidebar gets five rows (a 9px bar at
  55% width over a 7px bar at 35%, radius 3px, 56px rows). The main pane gets a header block (a 24px bar
  at 40%, plus a 28px bar at 18% on the right) and two empty cards at 120px and 200px.
  `background: linear-gradient(90deg, #efefed 0%, #f6f6f5 50%, #efefed 100%) 0 0 / 200% 100%;`
  `animation: shimmer 1.4s ease-in-out infinite;` with `@keyframes shimmer { to { background-position: -200% 0; } }`.
  This is the only infinite animation allowed.
- **No invoices (`.calm` and `.side-empty`).** Center the main pane at 40% height: the Halberd mark at
  24px, ink-4, inside a 48px `--surface` tile with `--shadow-card` and an 8px radius. Below it, "No
  invoices yet" at 15px/22px 500 ink. Below that, "Halberd checks each one as it arrives." at 13px ink-3.
  The sidebar shows "No invoices yet." at 13px ink-3 with padding `20px`.
- **Nothing selected.** Same layout, with the single line "Select an invoice." at 14px ink-3.
- **Toast.** Fixed, bottom 24px, centered. `#111` background, white 13px/18px 500 text, `padding: 8px 14px`,
  6px radius, `--shadow-pop`. Enters with `opacity 0→1, translateY(6px→0)` over 200ms `--ease-out`. Use
  it for errors only (see the copy notes).

---

## 13. Copy fixes seen in the current build

- The requester message (`rq.text`) ends "(Invoice Guard, Accounts Payable)". Swap it to "Halberd", or
  pass it through `plain()` to drop the aside.
- The "Billing day" change row shows `2026-10-14`. Format it as `Oct 14`.
- The "Email sent" and "Demo reset" toasts are demo-only text that would appear on camera. Drop the
  success message for the N and Shift+R paths, and keep error toasts. *(This is the one behavior-adjacent
  item, so the coordinator should confirm it.)*
- The "View PDF" link is purple. Make it ink-2 with the External icon at 12px.

---

## 14. Do not

1. Add any hue beyond `--fraud` and `--confirm`. That rules out purple links, green "cleared", and
   blue focus rings.
2. Tint a whole card, or color a whole row, red or amber. Color the marker, the pill, the value and
   the headline amount, and nothing else.
3. Stack a border and a shadow on the same box, or use a shadow alpha above 0.18.
4. Use uppercase labels, wide tracking, weight 700, or text under 12px.
5. Use mono for words. Mono is for numbers that identify something.
6. Use radius above 10px, pill-shaped buttons, or round risk markers (the icon set is square-capped).
7. Add gradients, glows, glass, or blur. The one exception is the sticky sidebar label.
8. Bounce, spin, or loop anything except the skeleton. No animation runs longer than 2.2s.
9. Re-run the enter animation on background refreshes. Only a new selection moves the main pane.
10. Use emojis, icon libraries, or icons in any color other than the text beside them.
11. Show anything implementation-shaped: check ids, ISO dates, "(…)" asides, "Invoice Guard", or demo
    controls.
