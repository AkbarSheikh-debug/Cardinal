/**
 * A bidirectional JSON-RPC 2.0 channel over one `send` function (PHASE-7 §5.2/§5.3). Both
 * "outer" and "sandbox proxy" are simultaneously a requester (forwarding calls up or down) and
 * a responder (handling the other side's requests), so one symmetric class serves both --
 * relaying itself (take a request from side A, re-issue it to side B, answer A with B's result)
 * is implemented explicitly at each call site instead, so it stays readable as "what actually
 * happens to this message" rather than hidden inside a generic forwarding abstraction.
 */
import {
  isNotification,
  isRequest,
  isResponse,
  type JsonRpcMessage,
  type JsonRpcRequest,
  type JsonRpcResponse,
} from "./protocol";

type Sender = (message: JsonRpcMessage) => void;
type RequestHandler = (params: unknown) => Promise<unknown> | unknown;
type NotificationHandler = (params: unknown) => void;

export class RpcChannel {
  private nextId = 1;
  private readonly pending = new Map<number, { resolve: (r: unknown) => void; reject: (e: Error) => void }>();
  private readonly requestHandlers = new Map<string, RequestHandler>();
  private readonly notificationHandlers = new Map<string, NotificationHandler>();

  constructor(private readonly send: Sender) {}

  onRequest(method: string, handler: RequestHandler): void {
    this.requestHandlers.set(method, handler);
  }

  onNotification(method: string, handler: NotificationHandler): void {
    this.notificationHandlers.set(method, handler);
  }

  request<R = unknown>(method: string, params: unknown): Promise<R> {
    const id = this.nextId++;
    const promise = new Promise<R>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (r: unknown) => void, reject });
    });
    this.send({ jsonrpc: "2.0", id, method, params } satisfies JsonRpcRequest);
    return promise;
  }

  notify(method: string, params: unknown): void {
    this.send({ jsonrpc: "2.0", method, params });
  }

  async handleIncoming(message: JsonRpcMessage): Promise<void> {
    if (isResponse(message)) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if ("error" in message) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
      return;
    }
    if (isRequest(message)) {
      const handler = this.requestHandlers.get(message.method);
      if (!handler) {
        const response: JsonRpcResponse = {
          jsonrpc: "2.0",
          id: message.id,
          error: { code: -32601, message: `method not found: ${message.method}` },
        };
        this.send(response);
        return;
      }
      try {
        const result = await handler(message.params);
        const response: JsonRpcResponse = { jsonrpc: "2.0", id: message.id, result };
        this.send(response);
      } catch (err) {
        const response: JsonRpcResponse = {
          jsonrpc: "2.0",
          id: message.id,
          error: { code: -32000, message: err instanceof Error ? err.message : String(err) },
        };
        this.send(response);
      }
      return;
    }
    if (isNotification(message)) {
      this.notificationHandlers.get(message.method)?.(message.params);
    }
  }

  /** Rejects every still-pending request -- called on teardown so a caller awaiting a promise
   * that will now never resolve doesn't hang forever (gate 7.7's "no leak" also means no
   * dangling promise).
   */
  cancelPending(reason: string): void {
    for (const { reject } of this.pending.values()) {
      reject(new Error(reason));
    }
    this.pending.clear();
  }
}
