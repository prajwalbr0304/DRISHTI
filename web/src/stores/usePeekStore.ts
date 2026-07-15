import { create } from "zustand";
import type { ObjectRef } from "@/api/types";
import { useRecentsStore } from "@/stores/useRecentsStore";

/* ============================================================================
   The PEEK RAIL state. A stack of object references so any reference can open
   *within* a peek (peek-within-peek). Pushing the same ref that's already on
   top is a no-op; opening deeper pushes; the header lets you pop back.
   ========================================================================== */

let seq = 0;
export interface PeekEntry extends ObjectRef {
  /** stable key for animation/list rendering */
  _key: string;
}

interface PeekState {
  stack: PeekEntry[];
  isOpen: boolean;
  open: (ref: ObjectRef) => void; // reset stack to a single ref
  push: (ref: ObjectRef) => void; // peek-within-peek
  pop: () => void; // back one level
  popTo: (index: number) => void;
  close: () => void;
}

function sameRef(a: ObjectRef, b: ObjectRef) {
  return a.kind === b.kind && String(a.id) === String(b.id);
}

export const usePeekStore = create<PeekState>((set, get) => ({
  stack: [],
  isOpen: false,

  open: (ref) => {
    useRecentsStore.getState().record(ref);
    set({ stack: [{ ...ref, _key: `pk_${seq++}` }], isOpen: true });
  },

  push: (ref) => {
    const { stack } = get();
    const top = stack[stack.length - 1];
    if (top && sameRef(top, ref)) return; // already peeking this
    useRecentsStore.getState().record(ref);
    set({ stack: [...stack, { ...ref, _key: `pk_${seq++}` }], isOpen: true });
  },

  pop: () => {
    const { stack } = get();
    if (stack.length <= 1) return set({ stack: [], isOpen: false });
    set({ stack: stack.slice(0, -1) });
  },

  popTo: (index) => {
    const { stack } = get();
    if (index < 0) return set({ stack: [], isOpen: false });
    set({ stack: stack.slice(0, index + 1) });
  },

  close: () => set({ stack: [], isOpen: false }),
}));
