/**
 * The `/voice/*` client and the browser half of the cascade (PLAN-02 P16).
 *
 * The server answers **204** to mean "tier 1 could not serve this — you speak/listen
 * instead". That is not an error path: `speak()` and `transcribe()` below fall through to the
 * Web Speech API on a 204 and return which tier actually served the call, so the UI can show
 * it and a trace can be checked against it.
 */

export type VoiceTier = "provider" | "browser" | "text";

export interface VoiceOption {
  id: string;
  label: string;
  tier: VoiceTier;
}

export interface VoiceCapabilities {
  speak_tier: VoiceTier;
  transcribe_tier: VoiceTier;
  voices: VoiceOption[];
}

export function browserSpeechOutSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function browserSpeechInSupported(): boolean {
  if (typeof window === "undefined") return false;
  return "SpeechRecognition" in window || "webkitSpeechRecognition" in window;
}

export async function fetchCapabilities(): Promise<VoiceCapabilities> {
  const browser = browserSpeechOutSupported() || browserSpeechInSupported();
  const response = await fetch(`/voice/capabilities?browser=${browser}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error("could not read voice capabilities");
  return response.json();
}

/**
 * The utterance currently playing, so it can be cut off when the user turns the voice off.
 * Without this, switching the toggle mid-reply silences *future* replies while the current
 * one keeps talking, which reads as the toggle being broken.
 */
let playing: HTMLAudioElement | null = null;

/** Stop whatever is being said right now, on either tier. */
export function stopSpeaking(): void {
  if (playing) {
    playing.pause();
    playing = null;
  }
  if (browserSpeechOutSupported()) window.speechSynthesis.cancel();
}

/**
 * Speak `text`, returning the tier that actually did it. Never throws for a degradation.
 *
 * **Resolves when the audio finishes, not when it starts.** `HTMLAudioElement.play()` returns
 * a promise that settles as soon as playback *begins*, so `await audio.play()` hands control
 * back almost immediately -- and a caller that speaks each agent message as it arrives ends up
 * with two voices talking over each other. Waiting for `ended` is what makes sequencing
 * possible at all; the queue in `VoiceControls` relies on it.
 */
export async function speak(text: string, voiceId: string | null): Promise<VoiceTier> {
  try {
    const response = await fetch("/voice/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ text, voice_id: voiceId }),
    });
    if (response.status === 204) return speakInBrowser(text);
    if (!response.ok) return speakInBrowser(text);

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    playing = audio;

    await new Promise<void>((resolve) => {
      // Every path resolves and revokes exactly once. A rejected `play()` (autoplay policy,
      // no output device) must not leave the queue waiting forever on an utterance that was
      // never going to be heard -- one stuck promise would silence every reply after it.
      const done = () => {
        URL.revokeObjectURL(url);
        if (playing === audio) playing = null;
        resolve();
      };
      audio.onended = done;
      audio.onerror = done;
      audio.onpause = done; // `stopSpeaking()` pauses; treat that as finished.
      void audio.play().catch(done);
    });
    return "provider";
  } catch {
    return speakInBrowser(text);
  }
}

/** Tier 2. Also resolves on `end`, so the queue sequences browser speech the same way. */
function speakInBrowser(text: string): Promise<VoiceTier> {
  if (!browserSpeechOutSupported()) return Promise.resolve("text");
  return new Promise<VoiceTier>((resolve) => {
    // Cancel anything queued: two overlapping utterances are worse than one late one.
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => resolve("browser");
    utterance.onerror = () => resolve("browser");
    window.speechSynthesis.speak(utterance);
  });
}

export interface TranscriptResult {
  text: string;
  tier: VoiceTier;
}

/**
 * Transcribe a recording. Returns the text for the user to **confirm** — this function never
 * sends anything as a chat turn, which is PLAN-02 P16's "no auto-send" rule expressed as an
 * API shape rather than a convention someone has to remember.
 */
export async function transcribe(
  blob: Blob,
  mimeType: string,
  sessionId: string,
): Promise<TranscriptResult> {
  // The filename extension is load-bearing: Whisper's multipart endpoints key off it rather
  // than the part's content-type, and an upload named `speech.bin` is rejected as an
  // unsupported format even when the mime type is right. Mirrors `_extension` server-side.
  const ext = mimeType.includes("ogg")
    ? "ogg"
    : mimeType.includes("mp4")
      ? "mp4"
      : mimeType.includes("wav")
        ? "wav"
        : "webm";
  const form = new FormData();
  form.append("file", blob, `speech.${ext}`);
  form.append("session_id", sessionId);

  const response = await fetch("/voice/transcribe", {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (response.status === 204) {
    throw new BrowserFallbackNeeded();
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "transcription failed" }));
    throw new Error(typeof detail?.detail === "string" ? detail.detail : "transcription failed");
  }
  const body = await response.json();
  return { text: body.text, tier: body.tier };
}

/** Signals that tier 1 declined and the caller should use `SpeechRecognition` instead. */
export class BrowserFallbackNeeded extends Error {
  constructor() {
    super("use the browser speech recogniser");
  }
}

/** Tier 2 speech-in. Resolves with a transcript, or rejects if the browser cannot do it. */
export function listenInBrowser(): Promise<TranscriptResult> {
  return new Promise((resolve, reject) => {
    const Ctor =
      (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike })
        .SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike })
        .webkitSpeechRecognition;
    if (!Ctor) {
      reject(new Error("this browser cannot transcribe speech"));
      return;
    }
    const recognition = new Ctor();
    recognition.lang = "en-GB";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      resolve({ text: event.results[0][0].transcript, tier: "browser" });
    };
    recognition.onerror = () => reject(new Error("could not hear that"));
    recognition.start();
  });
}

/** The slice of the un-standardised `SpeechRecognition` interface this file actually uses. */
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: (event: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void;
  onerror: () => void;
  start: () => void;
}
