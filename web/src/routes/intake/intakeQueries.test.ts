import { describe, expect, it } from "vitest";
import { subHeadOptions, toOptions } from "@/routes/intake/intakeQueries";
import type { IntakeOptionItem } from "@/api/types";

const subheads: IntakeOptionItem[] = [
  { id: 1, name: "Murder", parent_id: 10 },
  { id: 2, name: "Theft", parent_id: 20 },
  { id: 3, name: "Robbery", parent_id: 20 },
];

describe("intake option helpers", () => {
  it("maps {id,name} to {value,label}", () => {
    expect(toOptions([{ id: 7, name: "Bengaluru City" }])).toEqual([
      { value: "7", label: "Bengaluru City" },
    ]);
  });

  it("falls back to #id when name is null", () => {
    expect(toOptions([{ id: 9, name: null }])[0].label).toBe("#9");
  });

  it("filters sub-heads by the selected head", () => {
    const opts = subHeadOptions(subheads, 20);
    expect(opts.map((o) => o.value)).toEqual(["2", "3"]);
  });

  it("returns all sub-heads when no head is selected", () => {
    expect(subHeadOptions(subheads, null)).toHaveLength(3);
  });
});
