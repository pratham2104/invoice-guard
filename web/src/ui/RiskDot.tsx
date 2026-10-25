import { Icon } from "./Icon";

/** The one risk marker: a solid red circle with a white exclamation mark. */
export function RiskDot({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <span className={`risk-dot${className ? ` ${className}` : ""}`} style={{ width: size, height: size }} aria-hidden>
      <Icon name="Exclaim" size={Math.round(size * 0.82)} />
    </span>
  );
}
