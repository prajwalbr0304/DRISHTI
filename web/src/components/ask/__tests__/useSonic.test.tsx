import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSonic } from "../useSonic";

const { session, append } = vi.hoisted(() => ({ session: vi.fn(), append: vi.fn() }));
vi.mock("@/api/endpoints/chat", () => ({ chatApi: { voiceSession: session } }));
vi.mock("@/stores/useAskStore", () => ({ useAskStore: { getState: () => ({ sourceSessionId: 42, appendVoiceAnswer: append }) } }));
const trackStop = vi.fn();
class Context {
  sampleRate = 16000; state = "running";
  resume = vi.fn(async () => undefined);
  close = vi.fn(async () => { this.state = "closed"; });
  audioWorklet = { addModule: vi.fn(async () => undefined) };
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
}
class Worklet {
  port = { onmessage: null };
  connect = vi.fn(); disconnect = vi.fn();
}
class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  readyState = 1; bufferedAmount = 0;
  send = vi.fn(); close = vi.fn();
  constructor(public url: string) { Socket.instances.push(this); }
}

describe("Nova audio lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Socket.instances = [];
    session.mockResolvedValue({ url: "wss://api.example/stream/voice", ticket: "short-lived-ticket" });
    vi.stubGlobal("AudioContext", Context);
    vi.stubGlobal("AudioWorkletNode", Worklet);
    vi.stubGlobal("WebSocket", Socket);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: trackStop }] })) } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("authenticates in the first frame, uses the existing chat, and stops the microphone", async () => {
    const { result, unmount } = renderHook(useSonic);
    expect(session).not.toHaveBeenCalled();
    await act(async () => { await result.current.start("kiara"); });
    expect(session).toHaveBeenCalledWith({ voice: "kiara", language: "en", audio_consent: true, session_id: 42 });
    const socket = Socket.instances[0];
    act(() => socket.onopen?.());
    expect(socket.url).not.toContain("ticket");
    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ ticket: "short-lived-ticket" }));
    act(() => socket.onmessage?.({ data: JSON.stringify({ type: "ready" }) }));
    expect(result.current.phase).toBe("listening");
    act(() => socket.onmessage?.({ data: JSON.stringify({ type: "answer", question: "case count", answer: { reply: "5", session_id: 42 } }) }));
    expect(append).toHaveBeenCalledOnce();
    const stale = socket.onmessage;
    act(() => result.current.stop());
    expect(trackStop).toHaveBeenCalled();
    expect(socket.close).toHaveBeenCalled();
    act(() => stale?.({ data: JSON.stringify({ type: "answer", question: "late", answer: { reply: "old" } }) }));
    expect(append).toHaveBeenCalledOnce();
    unmount();
  });

  it("fails honestly and releases audio when the server rejects the connection", async () => {
    const { result, unmount } = renderHook(useSonic);
    await act(async () => { await result.current.start("arjun"); });
    act(() => Socket.instances[0].onerror?.());
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toContain("browser voice");
    expect(trackStop).toHaveBeenCalled();
    unmount();
  });

  it("reassembles large answer cards and renews a continuous conversation", async () => {
    const { result, unmount } = renderHook(useSonic);
    await act(async () => { await result.current.start("kiara"); });
    const socket = Socket.instances[0];
    const payload = JSON.stringify({ type: "answer", question: "case details", answer: { reply: "x".repeat(40000), session_id: 42 } });
    act(() => socket.onmessage?.({ data: JSON.stringify({ type: "chunk", data: payload.slice(0, 20000), last: false }) }));
    expect(append).not.toHaveBeenCalled();
    act(() => socket.onmessage?.({ data: JSON.stringify({ type: "chunk", data: payload.slice(20000), last: true }) }));
    expect(append).toHaveBeenCalledOnce();
    act(() => socket.onmessage?.({ data: JSON.stringify({ type: "session_end" }) }));
    await act(async () => socket.onclose?.());
    expect(session).toHaveBeenCalledTimes(2);
    expect(session).toHaveBeenLastCalledWith(expect.objectContaining({ session_id: 42, voice: "kiara" }));
    unmount();
  });
});
