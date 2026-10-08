// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAnchoredPopover } from "./browser";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const place = vi.fn();
const chosen = vi.fn();

/** A button and its popover panel, wired the way the three menus are. */
function Menu() {
  const popover = useAnchoredPopover(place);
  return createElement(
    "div",
    null,
    createElement("button", { ref: popover.button, type: "button", popoverTarget: popover.id }, "Open"),
    createElement(
      "div",
      { ref: popover.panel, id: popover.id, popover: "auto", onBeforeToggle: popover.onBeforeToggle },
      createElement("button", { type: "button", onClick: () => popover.close(chosen) }, "Pick"),
    ),
  );
}

let root: Root | null = null;
let host: HTMLElement | null = null;

function mount() {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => root!.render(createElement(Menu)));
  const [button, pick] = Array.from(host.querySelectorAll("button"));
  const panel = host.querySelector("[popover]") as HTMLElement;
  // jsdom has no popover API; the hook calls the panel's hidePopover.
  const hidden = vi.fn();
  Object.assign(panel, { hidePopover: hidden });
  return { button, pick, panel, hidden };
}

function toggle(panel: HTMLElement, newState: string) {
  act(() => {
    panel.dispatchEvent(Object.assign(new Event("beforetoggle", { bubbles: false }), { newState }));
  });
}

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  vi.clearAllMocks();
});

describe("useAnchoredPopover", () => {
  it("links the button to the panel by one id", () => {
    const { button, panel } = mount();
    expect(panel.id).not.toBe("");
    expect(button.getAttribute("popovertarget")).toBe(panel.id);
  });

  it("places the panel against the button's rectangle as it opens, and not as it closes", () => {
    const { button, panel } = mount();
    const rect = { left: 40, right: 76, top: 10, bottom: 46 } as DOMRect;
    button.getBoundingClientRect = () => rect;
    toggle(panel, "closed");
    expect(place).not.toHaveBeenCalled();
    toggle(panel, "open");
    expect(place).toHaveBeenCalledTimes(1);
    expect(place).toHaveBeenCalledWith(panel, rect);
  });

  it("hides the panel before running the chosen action", () => {
    const { pick, hidden } = mount();
    const order: string[] = [];
    hidden.mockImplementation(() => order.push("hidden"));
    chosen.mockImplementation(() => order.push("chosen"));
    act(() => pick.click());
    expect(order).toEqual(["hidden", "chosen"]);
  });
});
