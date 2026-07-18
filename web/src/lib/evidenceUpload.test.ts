import { describe, expect, it } from "vitest";
import { formatBytes, sha256Hex } from "@/lib/evidenceUpload";

describe("evidence upload helpers", () => {
  it("formats byte sizes", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("computes a stable SHA-256 hex matching the well-known 'abc' vector", async () => {
    if (!globalThis.crypto?.subtle) return; // environment without WebCrypto
    // jsdom's Blob lacks arrayBuffer(); supply a Blob-like exposing it so the
    // crypto path (identical in the browser) is exercised against a known vector.
    const blobLike = {
      arrayBuffer: async () => new TextEncoder().encode("abc").buffer,
    } as unknown as Blob;
    const hash = await sha256Hex(blobLike);
    expect(hash).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
