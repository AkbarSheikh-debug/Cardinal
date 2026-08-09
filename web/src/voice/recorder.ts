/**
 * Microphone capture for push-to-talk (PLAN-02 P16).
 *
 * Two details here are not obvious and both came from watching a real recorder misbehave:
 *
 * 1. **The MIME type must be probed, not assumed.** Safari supports neither `audio/webm` nor
 *    Opus; hardcoding either yields a `MediaRecorder` that constructs and then produces
 *    nothing. `isTypeSupported` in preference order is the only reliable way to pick one.
 * 2. **`start(250)` matters.** With no timeslice, `MediaRecorder` may emit a single
 *    `dataavailable` only at stop — and for a short press that can arrive empty, producing a
 *    0-byte blob and a baffling "too short" error. Asking for a chunk every 250ms guarantees
 *    data exists however briefly the user held the button.
 */

const PREFERRED_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
  "audio/mp4",
];

export function supportedMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const type of PREFERRED_TYPES) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

export function micSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined"
  );
}

export interface Recording {
  blob: Blob;
  mimeType: string;
  durationMs: number;
}

export class MicRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;
  private mimeType = "";

  async start(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.mimeType = supportedMimeType();
    this.chunks = [];
    this.recorder = new MediaRecorder(stream, this.mimeType ? { mimeType: this.mimeType } : {});
    this.recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    this.recorder.start(250); // see this module's docstring
    this.startedAt = Date.now();
  }

  stop(): Promise<Recording> {
    return new Promise((resolve, reject) => {
      const recorder = this.recorder;
      if (!recorder) {
        reject(new Error("not recording"));
        return;
      }
      recorder.onstop = () => {
        const mimeType = this.mimeType || "audio/webm";
        const blob = new Blob(this.chunks, { type: mimeType });
        // Release the mic immediately. Leaving tracks live keeps the browser's recording
        // indicator on, which reads to the user as "it is still listening".
        recorder.stream.getTracks().forEach((track) => track.stop());
        this.recorder = null;
        resolve({ blob, mimeType, durationMs: Date.now() - this.startedAt });
      };
      recorder.stop();
    });
  }

  get isRecording(): boolean {
    return this.recorder !== null;
  }
}
