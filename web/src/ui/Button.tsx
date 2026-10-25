import type { ReactNode } from "react";
import { Icon } from "./Icon";

/** The one Halberd primary button: purple fill, white inner ring, raised, with an arrow. */
export function PrimaryButton({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button className="btn primary" disabled={disabled} onClick={onClick}>
      <span>{children}</span>
      <Icon name="Arrow" size={16} className="btn-arrow" />
    </button>
  );
}
