import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { FaceScanner, type FaceConfirmation } from "./FaceScanner";
import type { FaceOrigin } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  origin?: FaceOrigin;
  intakeDraftKey?: string | null;
  caseId?: number | null;
  existingCanonicalPersonId?: number | null;
  onConfirm?: (c: FaceConfirmation) => void | Promise<void>;
  confirmLabel?: string;
  onNoMatch?: () => void;
  title?: string;
  description?: string;
}

/** The face scanner in a modal, for use inside an existing workflow (FIR intake,
 *  a case file) without navigating away from it.
 *
 *  Mounted only while open, which also guarantees the camera stream is released
 *  when the dialog closes (the useCamera hook stops its tracks on unmount). */
export function FaceScanDialog({
  open, onOpenChange, title = "Face recognition",
  description = "Check a photo against existing person records before creating a new identity.",
  ...rest
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[72vh] overflow-y-auto pr-1">
          {open && (
            <FaceScanner
              {...rest}
              onClose={() => onOpenChange(false)}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
