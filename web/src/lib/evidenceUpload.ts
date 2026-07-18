/* Presigned S3 upload helpers for the evidence page.

   - sha256Hex: compute a file's SHA-256 in the browser (WebCrypto). The server
     RE-computes and verifies this on completion; sending it lets the server
     reject a corrupt/partial upload with a clear "hash mismatch".
   - putToPresignedUrl: PUT the file straight to S3 via a pre-signed URL using
     XMLHttpRequest (fetch gives no upload progress). Supports progress + cancel.

   No AWS credentials are involved: the URL is short-lived and signed server-side.
*/

/** Hex SHA-256 of a File/Blob using the Web Crypto API. */
export async function sha256Hex(file: Blob): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface PutOptions {
  method?: string;
  headers?: Record<string, string>;
  onProgress?: (pct: number, loaded: number, total: number) => void;
  signal?: AbortSignal;
}

/** Upload a file to a pre-signed URL. Resolves on 2xx, rejects otherwise. */
export function putToPresignedUrl(url: string, file: Blob, opts: PutOptions = {}): Promise<void> {
  const { method = "PUT", headers = {}, onProgress, signal } = opts;
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);

    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100), e.loaded, e.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed (HTTP ${xhr.status}).`));
    };
    xhr.onerror = () => reject(new Error("Upload failed: network error or blocked by CORS."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(file);
  });
}

/** A human byte size, e.g. 1.2 MB. */
export function formatBytes(n?: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}
