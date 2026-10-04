import { useSyncExternalStore } from "react";

const PHONE = "(max-width: 639px)";

/** Whether the window is phone-sized now; false on the server. */
export function isPhone(): boolean {
  return typeof window !== "undefined" && window.matchMedia(PHONE).matches;
}

function subscribePhone(onChange: () => void) {
  const query = window.matchMedia(PHONE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Whether the window is phone-sized, following resizes; false until hydrated. */
export function usePhone(): boolean {
  return useSyncExternalStore(subscribePhone, isPhone, () => false);
}

/** Subscribes to nothing: for a value read once the page has hydrated. */
export const subscribeNothing = () => () => {};

/** True once the page has hydrated; false in the server render and the first client one. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribeNothing,
    () => true,
    () => false,
  );
}

/** Place a popover under its button, as wide as it fits beside the window's edges. */
export function placeBelow(
  panel: HTMLElement,
  anchor: DOMRect,
  width: number,
  gap: number,
  gutter = 12,
) {
  const fitted = Math.min(width, window.innerWidth - gutter * 2);
  panel.style.width = `${fitted}px`;
  panel.style.left = `${Math.min(Math.max(gutter, anchor.left), window.innerWidth - fitted - gutter)}px`;
  panel.style.top = `${anchor.bottom + gap}px`;
}
