import { money } from "../format";

/** Headline amount: dollars at full size, cents smaller and raised. */
export function Amount({ n }: { n: number }) {
  const s = money(n);
  const i = s.lastIndexOf(".");
  return (
    <span className="amt">
      {i === -1 ? s : <>{s.slice(0, i)}<span className="cents">{s.slice(i)}</span></>}
    </span>
  );
}

const ID = /([\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b[\w-]+(?:\.[a-z]{2,})+\b)/gi;

/** Plain text with sender addresses and domains set in mono, so lookalike letters read plainly. */
export function WithIds({ text }: { text: string }) {
  const parts = text.split(ID);
  if (parts.length === 1) return <>{text}</>;
  return <>{parts.map((p, i) => (i % 2 ? <span key={i} className="mono">{p}</span> : p))}</>;
}
