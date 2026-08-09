/**
 * The three voice controls (PLAN-02 P16): agent voice on/off, which voice, and push-to-talk.
 *
 * **A transcript never becomes a turn on its own.** `useVoice` hands the text back to the
 * caller, `App.tsx` drops it into the composer's `draft`, and the user presses send exactly as
 * they would after typing. That is the no-auto-send rule expressed structurally — there is no
 * code path from the microphone to `postMessage`, so it cannot regress into one by accident.
 * A mis-heard "no" that silently becomes a chat message is a far worse failure than one the
 * user gets to correct.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  BrowserFallbackNeeded,
  browserSpeechInSupported,
  fetchCapabilities,
  listenInBrowser,
  speak as speakText,
  stopSpeaking,
  transcribe,
  type VoiceCapabilities,
  type VoiceTier,
} from "./api";
import { MicRecorder, micSupported } from "./recorder";

const AGENT_VOICE_KEY = "cardinal.voice.agent";
const VOICE_ID_KEY = "cardinal.voice.id";

/**
 * Mirrors `MIN_AUDIO_BYTES` in `src/adapters/voice/cascade.py`. Duplicated on purpose: the
 * server must keep rejecting empty uploads whatever the client does, and the client should
 * not spend a round trip to be told something it can see for itself.
 */
const MIN_AUDIO_BYTES = 500;

/** Below this, the user tapped rather than held, whatever the microphone did. */
const MIN_CLIP_MS = 700;

/**
 * Why a clip has no usable audio — the two causes need different advice, and conflating them
 * is what makes this failure read as "voice is broken".
 *
 * A *short* clip is the user's timing: they tapped instead of holding. A clip that ran for a
 * second and still arrived near-empty is the machine's: the recorder was handed a device that
 * produced silence — muted, the wrong default input, or an OS privacy block. Telling someone
 * to "hold longer" when their microphone is muted sends them to fix the one thing that was
 * never wrong.
 */
function emptyClipReason(bytes: number, durationMs: number): string | null {
  if (durationMs < MIN_CLIP_MS) {
    return "That was too brief — hold the button while you speak, then press stop.";
  }
  if (bytes < MIN_AUDIO_BYTES) {
    return "No sound reached the microphone. Check it isn't muted, and that the browser is using the input device you expect.";
  }
  return null;
}

function stored(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export interface UseVoice {
  capabilities: VoiceCapabilities | null;
  agentVoiceOn: boolean;
  setAgentVoiceOn: (on: boolean) => void;
  voiceId: string | null;
  setVoiceId: (id: string) => void;
  recording: boolean;
  busy: boolean;
  error: string | null;
  lastTier: VoiceTier | null;
  toggleRecording: () => Promise<void>;
  speakReply: (text: string) => Promise<void>;
  micAvailable: boolean;
}

export function useVoice(sessionId: string, onTranscript: (text: string) => void): UseVoice {
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [agentVoiceOn, setAgentVoiceOnState] = useState(stored(AGENT_VOICE_KEY) === "on");
  const [voiceId, setVoiceIdState] = useState<string | null>(stored(VOICE_ID_KEY));
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastTier, setLastTier] = useState<VoiceTier | null>(null);
  const recorder = useRef(new MicRecorder());

  useEffect(() => {
    void fetchCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null));
  }, []);

  const setAgentVoiceOn = useCallback((on: boolean) => {
    setAgentVoiceOnState(on);
    try {
      window.sessionStorage.setItem(AGENT_VOICE_KEY, on ? "on" : "off");
    } catch {
      /* a browser with storage disabled still gets a working toggle, just not a sticky one */
    }
    // Cut off whatever is mid-sentence on either tier, not just what is queued behind it.
    if (!on) stopSpeaking();
  }, []);

  const setVoiceId = useCallback((id: string) => {
    setVoiceIdState(id);
    try {
      window.sessionStorage.setItem(VOICE_ID_KEY, id);
    } catch {
      /* as above */
    }
  }, []);

  /**
   * The tail of the speech queue.
   *
   * The agent emits each `agent_text` as it lands, and `App` speaks every one. Spoken
   * immediately, a two-message turn produces two voices at once. Chaining onto the previous
   * promise makes message 2 wait for message 1 to *finish* -- which only works because
   * `speak()` resolves on `ended` rather than on `play()`.
   *
   * A ref, not state: this must be the single live tail across renders, and a re-render
   * midway through a reply must not fork the chain into two queues.
   */
  const speechQueue = useRef<Promise<void>>(Promise.resolve());

  // Read by queued items at the moment they come up, so switching the voice off silences
  // everything still waiting rather than only what had not been queued yet.
  const agentVoiceOnRef = useRef(agentVoiceOn);
  agentVoiceOnRef.current = agentVoiceOn;

  const speakReply = useCallback(
    async (text: string) => {
      if (!agentVoiceOnRef.current || !text.trim()) return;
      const next = speechQueue.current
        .then(async () => {
          // Re-checked here, not just at enqueue time: a reply queued while the voice was on
          // must stay silent if it was switched off during the wait.
          if (!agentVoiceOnRef.current) return;
          setLastTier(await speakText(text, voiceId));
        })
        // A failed utterance must not break the chain -- one rejection would leave every
        // later reply permanently unspoken.
        .catch(() => undefined);
      speechQueue.current = next;
      await next;
    },
    [voiceId],
  );

  const toggleRecording = useCallback(async () => {
    setError(null);
    if (recording) {
      setRecording(false);
      setBusy(true);
      try {
        const clip = await recorder.current.stop();

        // Caught here rather than at the server, so the message can name the actual cause.
        // The server's own 422 says only "too short to contain speech", which is true and
        // useless: it cannot tell a tap from a muted microphone, because both arrive as the
        // same empty upload.
        const emptyReason = emptyClipReason(clip.blob.size, clip.durationMs);
        if (emptyReason !== null) {
          // Left in deliberately: when someone reports "it did not hear me", these two
          // numbers are the whole diagnosis, and asking them to reproduce it with devtools
          // open is a slower path to the same two numbers.
          console.warn(
            `[voice] discarded clip: ${clip.blob.size} bytes over ${clip.durationMs}ms (${clip.mimeType})`,
          );
          setLastTier("text");
          setError(emptyReason);
          return;
        }

        try {
          const result = await transcribe(clip.blob, clip.mimeType, sessionId);
          setLastTier(result.tier);
          // A 200 carrying an empty transcript is the worst of the failure modes: nothing
          // appears in the composer and nothing says why, which is indistinguishable from a
          // dead button. It happens when the clip is long enough to send but holds only room
          // noise. Say so instead of writing "" into the draft.
          if (!result.text.trim()) {
            setError("Nothing recognisable in that recording — try again, a little closer.");
            return;
          }
          onTranscript(result.text);
        } catch (exc) {
          if (exc instanceof BrowserFallbackNeeded) {
            // Tier 1 declined. The recording is already spent, so tier 2 has to listen
            // afresh -- surfaced as a prompt rather than silently re-opening the mic, which
            // would look like the button did nothing.
            setError("Using this browser's recogniser — press and speak again.");
            const result = await listenInBrowser();
            setLastTier(result.tier);
            onTranscript(result.text);
          } else {
            throw exc;
          }
        }
      } catch (exc) {
        setLastTier("text");
        setError(exc instanceof Error ? exc.message : "could not transcribe that");
      } finally {
        setBusy(false);
      }
      return;
    }

    try {
      await recorder.current.start();
      setRecording(true);
    } catch {
      // Denied permission, or no device. Tier 3: typing still works, and saying so is better
      // than a button that silently fails (PLAN-02 P16, gate 16.5).
      setLastTier("text");
      setError("No microphone access — you can still type.");
    }
  }, [recording, sessionId, onTranscript]);

  return {
    capabilities,
    agentVoiceOn,
    setAgentVoiceOn,
    voiceId,
    setVoiceId,
    recording,
    busy,
    error,
    lastTier,
    toggleRecording,
    speakReply,
    micAvailable: micSupported() || browserSpeechInSupported(),
  };
}

export function VoiceControls({ voice }: { voice: UseVoice }): React.ReactElement {
  const voices = voice.capabilities?.voices ?? [];
  return (
    <div className="voice-controls" data-testid="voice-controls">
      <button
        type="button"
        className="voice-toggle"
        data-testid="voice-agent-toggle"
        aria-pressed={voice.agentVoiceOn}
        onClick={() => voice.setAgentVoiceOn(!voice.agentVoiceOn)}
        title={voice.agentVoiceOn ? "Agent voice on" : "Agent voice off"}
      >
        {voice.agentVoiceOn ? "🔊" : "🔇"}
        <span className="voice-label">Voice</span>
      </button>

      {voices.length > 1 && (
        <select
          className="voice-picker"
          data-testid="voice-picker"
          aria-label="Agent voice"
          value={voice.voiceId ?? voices[0].id}
          onChange={(e) => voice.setVoiceId(e.target.value)}
        >
          {voices.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      )}

      {voice.micAvailable && (
        <button
          type="button"
          className="voice-mic"
          data-testid="voice-mic"
          aria-pressed={voice.recording}
          data-recording={voice.recording ? "yes" : "no"}
          disabled={voice.busy}
          onClick={() => void voice.toggleRecording()}
        >
          {voice.busy ? "…" : voice.recording ? "◼ Stop" : "🎤 Speak"}
        </button>
      )}

      {/* Which tier served the last utterance. Visible, not just traced -- "the voice sounded
          worse today" should be answerable by looking at the screen. */}
      {voice.lastTier && (
        <span className="voice-tier" data-testid="voice-tier" data-tier={voice.lastTier}>
          {voice.lastTier === "provider" ? "hi-fi" : voice.lastTier === "browser" ? "system" : "text"}
        </span>
      )}

      {voice.error && (
        <span className="voice-error" role="status" data-testid="voice-error">
          {voice.error}
        </span>
      )}
    </div>
  );
}
