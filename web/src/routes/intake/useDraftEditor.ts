import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type {
  IntakeDraftPayload,
  IntakePartyInput,
  IntakeValidationResponse,
} from "@/api/types";
import type { SaveState } from "@/routes/intake/components";

const EDITABLE = new Set(["draft", "returned_for_correction"]);

export function emptyPayload(): IntakeDraftPayload {
  return {
    source: {},
    registration: {},
    incident: {},
    classification: { acts_sections: [], category_specific: {} },
    narrative: { restricted: false, language: "en" },
  };
}

type Section = keyof IntakeDraftPayload;

/** Draft wizard state: hydrate, debounced autosave, validation, party CRUD. */
export function useDraftEditor(draftKey: string, actor?: string) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["intake", "draft", draftKey],
    queryFn: ({ signal }) => api.intake.getDraft(draftKey, signal),
    enabled: !!draftKey,
  });

  const [payload, setPayload] = useState<IntakeDraftPayload>(emptyPayload());
  const [caseKind, setCaseKindState] = useState<string>("fir_standard");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [validation, setValidation] = useState<IntakeValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const revisionRef = useRef(0);
  const hydrated = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // hydrate local state once from the loaded draft
  useEffect(() => {
    if (q.data && !hydrated.current) {
      setPayload({ ...emptyPayload(), ...q.data.payload });
      setCaseKindState(q.data.case_kind);
      revisionRef.current = q.data.revision_no;
      setValidation(q.data.validation ?? null);
      hydrated.current = true;
    }
  }, [q.data]);

  const status = q.data?.status ?? "draft";
  const isEditable = EDITABLE.has(status);

  const doSave = useCallback(
    async (nextPayload: IntakeDraftPayload, nextKind: string) => {
      setSaveState("saving");
      try {
        const res = await api.intake.updateDraft(draftKey, {
          payload: nextPayload,
          case_kind: nextKind,
          expected_revision_no: revisionRef.current,
          autosave: true,
          actor,
        });
        revisionRef.current = res.revision_no;
        setSaveState("saved");
        qc.setQueryData(["intake", "draft", draftKey], res);
      } catch (e) {
        setSaveState("error");
        console.warn("intake autosave failed:", errorMessage(e));
      }
    },
    [draftKey, actor, qc],
  );

  const schedule = useCallback(
    (nextPayload: IntakeDraftPayload, nextKind: string) => {
      setSaveState("dirty");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void doSave(nextPayload, nextKind), 1100);
    },
    [doSave],
  );

  const update = useCallback(
    <S extends Section>(section: S, patch: Partial<IntakeDraftPayload[S]>) => {
      setPayload((prev) => {
        const next = { ...prev, [section]: { ...prev[section], ...patch } };
        schedule(next, caseKind);
        return next;
      });
    },
    [schedule, caseKind],
  );

  const setCaseKind = useCallback(
    (kind: string) => {
      setCaseKindState(kind);
      setPayload((prev) => {
        schedule(prev, kind);
        return prev;
      });
    },
    [schedule],
  );

  const saveNow = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    await doSave(payload, caseKind);
  }, [doSave, payload, caseKind]);

  const refetch = useCallback(async () => {
    const fresh = await api.intake.getDraft(draftKey);
    revisionRef.current = fresh.revision_no;
    qc.setQueryData(["intake", "draft", draftKey], fresh);
    return fresh;
  }, [draftKey, qc]);

  // party CRUD (operate on the persisted draft, then refresh)
  const addParty = useCallback(async (p: IntakePartyInput) => {
    const res = await api.intake.addParty(draftKey, p);
    revisionRef.current = res.revision_no;
    qc.setQueryData(["intake", "draft", draftKey], res);
  }, [draftKey, qc]);

  const updateParty = useCallback(async (id: number, p: IntakePartyInput) => {
    const res = await api.intake.updateParty(draftKey, id, p);
    qc.setQueryData(["intake", "draft", draftKey], res);
  }, [draftKey, qc]);

  const removeParty = useCallback(async (id: number) => {
    const res = await api.intake.removeParty(draftKey, id);
    qc.setQueryData(["intake", "draft", draftKey], res);
  }, [draftKey, qc]);

  const validate = useCallback(async () => {
    await saveNow();
    setValidating(true);
    try {
      const v = await api.intake.validateDraft(draftKey);
      setValidation(v);
      return v;
    } finally {
      setValidating(false);
    }
  }, [draftKey, saveNow]);

  // unsaved-change protection on hard reload / tab close
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (saveState === "dirty" || saveState === "saving") {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [saveState]);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const parties = q.data?.parties ?? [];

  return useMemo(
    () => ({
      loading: q.isLoading,
      error: q.error,
      draft: q.data,
      payload, caseKind, status, isEditable, saveState, validation, validating,
      parties, revisionNo: revisionRef.current,
      update, setCaseKind, saveNow, refetch,
      addParty, updateParty, removeParty, validate,
    }),
    [q.isLoading, q.error, q.data, payload, caseKind, status, isEditable, saveState,
     validation, validating, parties, update, setCaseKind, saveNow, refetch,
     addParty, updateParty, removeParty, validate],
  );
}
