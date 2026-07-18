import { describe, expect, it } from "vitest";
import { checkRow, toRequest } from "@/routes/intake/imports/IntakeImports";

describe("intake bulk-import row validation", () => {
  const valid = {
    case_kind: "fir_standard", registration_date: "2025-06-01", station_id: "5",
    registering_officer_id: "10", major_head_id: "1", brief_facts: "A reported incident",
    complainant_name: "Ravi Kumar",
  };

  it("accepts a complete row", () => {
    expect(checkRow(valid)).toEqual([]);
  });

  it("flags every missing required field", () => {
    const errs = checkRow({});
    expect(errs).toEqual(expect.arrayContaining([
      "registration_date required", "station_id required",
      "registering_officer_id required", "major_head_id required",
      "brief_facts required", "complainant_name required (reporter)",
    ]));
  });

  it("rejects an unknown case_kind", () => {
    expect(checkRow({ ...valid, case_kind: "banana" })).toContain("invalid case_kind 'banana'");
  });

  it("maps a row to a draft request with a canonical complainant party", () => {
    const req = toRequest(valid);
    expect(req.case_kind).toBe("fir_standard");
    expect(req.payload.registration.station_id).toBe(5);
    expect(req.payload.source.source_system_code).toBe("CSV_IMPORT");
    expect(req.parties).toHaveLength(1);
    expect(req.parties[0]).toMatchObject({ role_type: "complainant", display_name: "Ravi Kumar" });
  });
});
