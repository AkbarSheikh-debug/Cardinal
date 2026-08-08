/**
 * Chat rail (plain React) + A2UI canvas (agent-composed, catalog-validated) + MCP App host
 * (PHASE-7) -- PLAN-00 SS3's three-pane shape. The canvas never constructs markup itself: every
 * surface it shows arrived as a `createSurface`/`updateComponents` message over SSE from
 * `src/api/main.py`'s `GET /sessions/{id}/events` (PHASE-6 SS6). The same SSE stream carries one
 * more tagged message kind P6 didn't have: `{kind: "mcp_app_open", ...}`, pushed by
 * `open_booking_form`'s handler (`src/mcp/booking/tools.py`) through the identical
 * `UISink`/`QueueUISink` transport rather than a second channel -- discriminated from a real
 * A2UI message by the absence of A2UI's own `version` field.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  A2uiSurface,
  MarkdownContext,
  createProcessor,
  plainTextMarkdownRenderer,
  type A2uiClientAction,
  type ReactComponentImplementation,
  type SurfaceModel,
} from "./a2ui/adapter";
import { customComponents } from "./a2ui/catalog";
import { McpAppHost } from "./mcp-host/McpAppHost";

interface McpAppOpenMessage {
  kind: "mcp_app_open";
  resourceUri: string;
  toolName: string;
  toolInput: Record<string, unknown>;
}

function isMcpAppOpenMessage(value: unknown): value is McpAppOpenMessage {
  return (
    typeof value === "object" && value !== null && (value as { kind?: unknown }).kind === "mcp_app_open"
  );
}

/** Live turn progress pushed by `CardinalOrchestrator.send` down the same SSE channel. */
interface AgentTextMessage {
  kind: "agent_text";
  text: string;
}
interface AgentStatusMessage {
  kind: "agent_status";
  status: string;
}
/** D-063: `DEMO_MODE`'s scripted persona narrated as an actual chat turn, not just a canvas
 * update -- pushed by `src/agent/demo_stream.py` alongside its `render_*` calls, same SSE
 * channel, so the chat rail shows the walkthrough as a conversation instead of staying silent
 * while charts and cards appear on their own. */
interface UserTextMessage {
  kind: "user_text";
  text: string;
}

function messageKind(value: unknown): string | null {
  if (typeof value !== "object" || value === null) return null;
  const kind = (value as { kind?: unknown }).kind;
  return typeof kind === "string" ? kind : null;
}

const SESSION_STORAGE_KEY = "cardinal.session";

/**
 * A per-browser-session id, persisted so a reload continues the same conversation but two tabs
 * (or two people on one demo machine) never land on the same one. A hardcoded shared id is what
 * made the whole app look broken once a session had been used: the backend holds one live agent
 * connection per id, so a second visitor inherited the first's in-flight state.
 */
function sessionId(): string {
  const fromUrl = new URLSearchParams(window.location.search).get("session");
  if (fromUrl) return fromUrl;
  const stored = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (stored) return stored;
  const fresh = crypto.randomUUID();
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, fresh);
  return fresh;
}

async function postAction(
  session: string,
  action: { surfaceId: string; sourceComponentId: string; name: string; context: unknown },
): Promise<void> {
  await fetch(`/sessions/${session}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      surface: action.surfaceId,
      component: action.sourceComponentId,
      action: action.name,
      payload: action.context,
    }),
  });
}

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
}

/** `src/agent/model_catalog.py`'s `MODELS`, fetched from `GET /models`. */
interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  free: boolean;
  reasoning: boolean;
  description: string;
}

const CLAUDE_MODEL_ID = "claude";

async function fetchModels(): Promise<ModelInfo[]> {
  try {
    const response = await fetch("/models");
    if (!response.ok) return [];
    const body: unknown = await response.json();
    return Array.isArray(body) ? (body as ModelInfo[]) : [];
  } catch {
    return [];
  }
}

async function setSessionModel(session: string, modelId: string): Promise<void> {
  const response = await fetch(`/sessions/${session}/model`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
  }
}

async function postMessage(session: string, text: string): Promise<ChatMessage[]> {
  const response = await fetch(`/sessions/${session}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
  }
  const replies: unknown = body?.messages;
  if (!Array.isArray(replies)) return [];
  return replies
    .filter((m): m is { role: string; text: string } => typeof m?.text === "string")
    .map((m) => ({ role: "assistant" as const, text: m.text }));
}

/**
 * The agent writes markdown; the chat rail is plain React. Rather than pull a markdown library
 * in for one feature, this handles the only construct that actually shows up in its replies --
 * `**bold**` -- and leaves everything else as literal text. Splitting on the delimiter and
 * alternating means no HTML is ever constructed from model output.
 *
 * Each word additionally becomes its own span carrying a `--i` index (styles.css's `.kinetic`
 * reads it for a staggered fade-in) -- harmless when the surrounding message isn't marked
 * `.kinetic` (user/error bubbles), since nothing then matches `.kinetic span` and the spans
 * render as plain, instantly-visible text.
 */
function formatted(text: string): React.ReactNode[] {
  let wordIndex = 0;
  return text.split(/\*\*(.+?)\*\*/gs).map((part, i) => {
    const isBold = i % 2 === 1;
    const words = part.split(/(\s+)/).map((word, j) => {
      const idx = wordIndex;
      if (word.trim()) wordIndex += 1;
      return (
        <span key={j} style={{ "--i": idx } as React.CSSProperties}>
          {word}
        </span>
      );
    });
    return isBold ? <strong key={i}>{words}</strong> : <span key={i}>{words}</span>;
  });
}

/** `InterviewProgress`'s `phase` prop, hue-rotating the ambient background per phase so the
 * app reads as reacting to what the agent is actually doing (D-061's UX pass). Degrees are a
 * rotation of the CSS-authored baseline (green/blue), not absolute hues -- see `.ambient`. */
const PHASE_MOOD: Record<string, number> = {
  interview: 0,
  research: 40,
  recommend: 280,
  transact: 325,
};

/** Pulls `phase` off a raw A2UI `updateComponents` message's `InterviewProgress` entry, if
 * present -- reading the wire message directly rather than the A2UI processor's own surface
 * model, since that model's shape is the library's internal representation (re-exported, not
 * owned by this codebase) and phase is the one field this app needs before the processor has
 * even run. `createSurface`/`updateDataModel`/`deleteSurface` messages don't carry it and are
 * left alone.
 */
function phaseFromMessage(message: unknown): string | null {
  if (typeof message !== "object" || message === null) return null;
  const update = (message as { updateComponents?: { components?: unknown } }).updateComponents;
  const components = update?.components;
  if (!Array.isArray(components)) return null;
  for (const c of components) {
    if (c && typeof c === "object" && (c as { component?: unknown }).component === "InterviewProgress") {
      const phase = (c as { phase?: unknown }).phase;
      return typeof phase === "string" ? phase : null;
    }
  }
  return null;
}

const OPENERS = [
  "I need a family SUV under €30,000",
  "Something cheap to run for a long commute",
  "Is it cheaper to rent or buy for 6 months?",
  "A fun weekend car, budget €20,000",
];

/** Rotating status line, so a 30-second turn reads as work rather than a hang. */
const THINKING_STAGES = [
  "Reading your requirements",
  "Searching the marketplaces",
  "Comparing the shortlist",
  "Checking the numbers",
  "Writing up the reasoning",
];

function ThinkingIndicator({ status }: { status: string | null }): React.ReactElement {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  // A real status streamed from the agent always beats the guessed-from-elapsed-time stage.
  const stage =
    status ?? THINKING_STAGES[Math.min(Math.floor(seconds / 6), THINKING_STAGES.length - 1)];
  return (
    <div className="msg msg-assistant msg-thinking" data-testid="thinking">
      <div className="thinking-row">
        <span className="dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="thinking-stage">{stage}</span>
      </div>
      <span className="thinking-elapsed">{seconds}s</span>
    </div>
  );
}

export default function App(): React.ReactElement {
  const session = useMemo(sessionId, []);
  const [surfaces, setSurfaces] = useState<SurfaceModel<ReactComponentImplementation>[]>([]);
  const [mcpApp, setMcpApp] = useState<McpAppOpenMessage | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState(CLAUDE_MODEL_ID);
  const [modelConfirmed, setModelConfirmed] = useState(true);
  const [modelError, setModelError] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [wipeKey, setWipeKey] = useState(0);
  const phaseRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const processorRef = useRef(
    createProcessor(customComponents, (action: A2uiClientAction) => postAction(session, action)),
  );

  useEffect(() => {
    fetch("/health")
      .then((r) => setOnline(r.ok))
      .catch(() => setOnline(false));
    fetchModels().then(setModels);
  }, []);

  const chooseModel = useCallback(
    async (modelId: string): Promise<void> => {
      setSelectedModel(modelId);
      setModelError(null);
      // The default needs no round-trip: it's what a session is already on until told
      // otherwise (D-056). Anything else has to be confirmed server-side before the first
      // message goes out, or that message would run on whatever the backend still thinks
      // this session's model is.
      if (modelId === CLAUDE_MODEL_ID) {
        setModelConfirmed(true);
        return;
      }
      setModelConfirmed(false);
      try {
        await setSessionModel(session, modelId);
        setModelConfirmed(true);
      } catch (err) {
        setModelError(err instanceof Error ? err.message : "Could not set model");
      }
    },
    [session],
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chatMessages, sending]);

  const send = useCallback(
    async (text: string): Promise<void> => {
      const trimmed = text.trim();
      if (!trimmed || sending || !modelConfirmed) return;
      setDraft("");
      setChatMessages((prev) => [...prev, { role: "user", text: trimmed }]);
      setSending(true);
      setStatus(null);
      try {
        // The reply text already arrived over SSE as the turn ran (`agent_text`); this call is
        // awaited for completion and errors only, so its body is deliberately discarded.
        await postMessage(session, trimmed);
      } catch (err) {
        setChatMessages((prev) => [
          ...prev,
          { role: "error", text: err instanceof Error ? err.message : "Message failed" },
        ]);
      } finally {
        setSending(false);
        setStatus(null);
      }
    },
    [session, sending, modelConfirmed],
  );

  useEffect(() => {
    const processor = processorRef.current;
    const subscription = processor.model.onSurfaceCreated.subscribe(() => {
      setSurfaces([...processor.model.surfacesMap.values()]);
    });
    const source = new EventSource(`/sessions/${session}/events`);
    source.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (isMcpAppOpenMessage(message)) {
        setMcpApp(message);
        return;
      }
      switch (messageKind(message)) {
        case "agent_text":
          // Streamed as it lands; `postMessage`'s eventual return is then dropped as a dup.
          setChatMessages((prev) => [
            ...prev,
            { role: "assistant", text: (message as AgentTextMessage).text },
          ]);
          return;
        case "agent_status":
          setStatus((message as AgentStatusMessage).status);
          return;
        case "user_text":
          setChatMessages((prev) => [
            ...prev,
            { role: "user", text: (message as UserTextMessage).text },
          ]);
          return;
      }
      const nextPhase = phaseFromMessage(message);
      // A wipe marks a *transition* -- the ref (not state, which lags a render behind) is
      // what tells the very first phase report apart from an actual change, so INTERVIEW's
      // own opening progress surface doesn't wipe against nothing.
      if (nextPhase && nextPhase !== phaseRef.current) {
        if (phaseRef.current !== null) setWipeKey((k) => k + 1);
        phaseRef.current = nextPhase;
        setPhase(nextPhase);
      }
      processor.processMessages([message]);
      setSurfaces([...processor.model.surfacesMap.values()]);
    };
    return () => {
      subscription.unsubscribe();
      source.close();
    };
  }, [session]);

  const started = chatMessages.length > 0;

  return (
    <div className="app">
      <div
        className="ambient"
        aria-hidden="true"
        style={{ "--mood": `${PHASE_MOOD[phase ?? "interview"] ?? 0}deg` } as React.CSSProperties}
      />
      {wipeKey > 0 && <div key={wipeKey} className="phase-wipe" aria-hidden="true" />}
      <aside className="rail">
        <header className="brand">
          <div className="brand-mark" aria-hidden="true">
            C
          </div>
          <div className="brand-text">
            <h1>Cardinal</h1>
            <p>
              <span className={`dot ${online ? "dot-ok" : online === false ? "dot-bad" : ""}`} />
              {online === null ? "Connecting" : online ? "Agent online" : "Agent offline"}
            </p>
          </div>
        </header>

        <div className="messages" ref={scrollRef} data-testid="chat-messages">
          {!started && (
            <div className="intro">
              <h2>What are you looking for?</h2>
              <p>
                Tell Cardinal what you need. It interviews you, searches real marketplaces, and
                comes back with a ranked shortlist it can defend.
              </p>

              {models.length > 1 && (
                <div className="model-picker" data-testid="model-picker">
                  <p className="model-picker-label">Model for the interview</p>
                  <div className="model-picker-list">
                    {models.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        className={`model-picker-item ${m.id === selectedModel ? "selected" : ""}`}
                        onClick={() => void chooseModel(m.id)}
                        data-testid={`model-option-${m.id}`}
                      >
                        <span className="model-picker-item-top">
                          <span className="model-picker-item-label">{m.label}</span>
                          {m.free && <span className="badge badge-free">free</span>}
                          {m.reasoning && <span className="badge badge-reasoning">reasoning</span>}
                        </span>
                        <span className="model-picker-item-desc">{m.description}</span>
                      </button>
                    ))}
                  </div>
                  {selectedModel !== CLAUDE_MODEL_ID && (
                    <p className="model-picker-note">
                      Search, ranking and booking still run on Cardinal's own model either way —
                      this only changes what asks the interview questions.
                    </p>
                  )}
                  {modelError && <p className="model-picker-error">{modelError}</p>}
                </div>
              )}

              <div className="openers">
                {OPENERS.map((opener) => (
                  <button
                    key={opener}
                    type="button"
                    disabled={!modelConfirmed}
                    onClick={() => void send(opener)}
                  >
                    {opener}
                  </button>
                ))}
              </div>
            </div>
          )}

          {chatMessages.map((message, i) => (
            <div
              key={i}
              className={`msg msg-${message.role} ${message.role === "assistant" ? "kinetic" : ""}`}
            >
              {formatted(message.text)}
            </div>
          ))}
          {sending && <ThinkingIndicator status={status} />}
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft);
          }}
        >
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={modelConfirmed ? "Tell Cardinal what you need…" : "Setting model…"}
            data-testid="chat-input"
            disabled={sending || !modelConfirmed}
            autoFocus
          />
          <button
            type="submit"
            disabled={sending || !modelConfirmed || !draft.trim()}
            aria-label="Send"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M3.4 20.4l17.5-8.4a.5.5 0 000-.9L3.4 2.6a.5.5 0 00-.7.6L5 11l10 1-10 1-2.3 7.8a.5.5 0 00.7.6z"
                fill="currentColor"
              />
            </svg>
          </button>
        </form>
      </aside>

      <main className="canvas">
        {surfaces.length === 0 ? (
          <div className="canvas-empty">
            <div className="canvas-empty-art" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <h2>Your shortlist appears here</h2>
            <p>
              As Cardinal researches, it composes live result cards, score breakdowns and
              rent-vs-buy comparisons onto this canvas.
            </p>
          </div>
        ) : (
          <MarkdownContext.Provider value={plainTextMarkdownRenderer}>
            {surfaces.map((surface) => (
              <section key={surface.id} className="surface">
                <A2uiSurface surface={surface} />
              </section>
            ))}
          </MarkdownContext.Provider>
        )}
      </main>

      {mcpApp && (
        <McpAppHost
          key={mcpApp.resourceUri + JSON.stringify(mcpApp.toolInput)}
          sessionId={session}
          resourceUri={mcpApp.resourceUri}
          toolName={mcpApp.toolName}
          toolInput={mcpApp.toolInput}
          onClose={() => setMcpApp(null)}
          onChatMessage={(text) =>
            postAction(session, {
              surfaceId: `mcp-app:${mcpApp.resourceUri}`,
              sourceComponentId: "app",
              name: "message",
              context: { text },
            })
          }
        />
      )}
    </div>
  );
}
