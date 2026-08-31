/* AudioWorklet: 16 kHz, mono, little-endian PCM. Never record audio to disk. */
class SonicCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = new Int16Array(512);
    this.offset = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input) for (const sample of input) {
      const bounded = Math.max(-1, Math.min(1, sample));
      this.samples[this.offset++] = bounded < 0 ? bounded * 32768 : bounded * 32767;
      if (this.offset === this.samples.length) {
        this.port.postMessage(this.samples.buffer, [this.samples.buffer]);
        this.samples = new Int16Array(512);
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("sonic-capture", SonicCapture);
