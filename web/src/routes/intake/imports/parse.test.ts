import { describe, expect, it } from "vitest";
import { parseCsv, parseJson } from "@/routes/intake/imports/parse";

describe("intake import parsers", () => {
  it("parses CSV with a header row into objects", () => {
    const csv = "case_kind,brief_facts\nfir_standard,A theft was reported\nudr,Body found";
    const rows = parseCsv(csv);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ case_kind: "fir_standard", brief_facts: "A theft was reported" });
    expect(rows[1].case_kind).toBe("udr");
  });

  it("honours quoted fields containing commas and quotes", () => {
    const csv = 'case_kind,brief_facts\nfir_standard,"Theft of ""cash"", jewellery"';
    const rows = parseCsv(csv);
    expect(rows[0].brief_facts).toBe('Theft of "cash", jewellery');
  });

  it("skips blank lines", () => {
    expect(parseCsv("a,b\n1,2\n\n3,4\n")).toHaveLength(2);
  });

  it("parses a JSON array of rows", () => {
    expect(parseJson('[{"case_kind":"fir_standard"},{"case_kind":"ncr"}]')).toHaveLength(2);
  });

  it("wraps a single JSON object into one row", () => {
    expect(parseJson('{"case_kind":"par"}')).toEqual([{ case_kind: "par" }]);
  });

  it("rejects non-array/object JSON", () => {
    expect(() => parseJson("42")).toThrow();
  });
});
