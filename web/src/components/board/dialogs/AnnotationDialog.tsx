import { useEffect, useState } from "react";
import { Frame, StickyNote, Type } from "lucide-react";
import type { AnnotationKind } from "@/api/endpoints/board";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

type EditableKind = Extract<AnnotationKind, "sticky" | "frame" | "text">;

export interface AnnotationDraft {
  kind: EditableKind;
  content: string;
  width?: number;
  height?: number;
  color?: string;
}

const META = {
  sticky: {
    title: "Add sticky note",
    description: "Capture an observation, question or follow-up directly on the board.",
    placeholder: "Enter the note text…",
    icon: StickyNote,
  },
  frame: {
    title: "Add frame",
    description: "Create a labelled grouping area for related objects and evidence.",
    placeholder: "Frame label",
    icon: Frame,
  },
  text: {
    title: "Add text",
    description: "Add a clear heading or explanatory text without a note background.",
    placeholder: "Enter the board text…",
    icon: Type,
  },
} satisfies Record<EditableKind, {
  title: string; description: string; placeholder: string; icon: typeof StickyNote;
}>;

export function AnnotationDialog({
  kind,
  onClose,
  onCreate,
}: {
  kind: EditableKind | null;
  onClose: () => void;
  onCreate: (draft: AnnotationDraft) => void;
}) {
  const [content, setContent] = useState("");
  const [width, setWidth] = useState(340);
  const [height, setHeight] = useState(240);
  const [color, setColor] = useState("#fde68a");

  useEffect(() => {
    if (!kind) return;
    setContent(kind === "frame" ? "Evidence group" : "");
    setWidth(340);
    setHeight(240);
    setColor("#fde68a");
  }, [kind]);

  if (!kind) return null;
  const meta = META[kind];
  const Icon = meta.icon;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="size-4 text-primary" /> {meta.title}
          </DialogTitle>
          <DialogDescription>{meta.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-12 font-medium text-content">
              {kind === "frame" ? "Frame label" : kind === "text" ? "Text" : "Note"}
            </span>
            <textarea
              autoFocus
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={kind === "frame" ? 2 : 5}
              placeholder={meta.placeholder}
              className="w-full resize-y rounded-control border border-hairline bg-surface-2 p-2.5 text-13 text-content outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </label>

          {kind === "frame" && (
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="mb-1 block text-12 text-content-dim">Width</span>
                <Input
                  type="number"
                  min={220}
                  max={1200}
                  value={width}
                  onChange={(event) => setWidth(Number(event.target.value))}
                  className="h-9"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-12 text-content-dim">Height</span>
                <Input
                  type="number"
                  min={140}
                  max={900}
                  value={height}
                  onChange={(event) => setHeight(Number(event.target.value))}
                  className="h-9"
                />
              </label>
            </div>
          )}

          {kind === "sticky" && (
            <label className="flex items-center justify-between gap-3 rounded-control border border-hairline p-2.5">
              <span className="text-12 text-content-dim">Note colour</span>
              <input
                type="color"
                value={color}
                onChange={(event) => setColor(event.target.value)}
                className="h-8 w-12 cursor-pointer rounded border-0 bg-transparent p-0"
                aria-label="Sticky note colour"
              />
            </label>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button
              disabled={!content.trim()}
              onClick={() => onCreate({
                kind,
                content: content.trim(),
                width: kind === "frame" ? Math.max(220, width || 340) : undefined,
                height: kind === "frame" ? Math.max(140, height || 240) : undefined,
                color: kind === "sticky" ? color : undefined,
              })}
            >
              Add to board
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
