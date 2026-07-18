import { describe, expect, it } from "vitest";
import { prettyType, shortHash, stateBadgeVariant } from "./evidenceShared";

describe("evidence shared helpers", () => {
  it("maps evidence states to badge variants", () => {
    expect(stateBadgeVariant("available")).toBe("low");
    expect(stateBadgeVariant("uploading")).toBe("primary");
    expect(stateBadgeVariant("failed")).toBe("critical");
    expect(stateBadgeVariant("archived")).toBe("outline");
    expect(stateBadgeVariant("draft")).toBe("neutral");
  });

  it("prettifies snake_case types", () => {
    expect(prettyType("court_document")).toBe("Court Document");
    expect(prettyType(null)).toBe("—");
  });

  it("shortens a long sha256 and passes through short values", () => {
    const sha = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    expect(shortHash(sha)).toBe("ba7816bf8f…15ad");
    expect(shortHash(null)).toBe("—");
    expect(shortHash("abc")).toBe("abc");
  });
});
