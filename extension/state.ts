export type LightState = "working" | "waiting" | "done" | "error" | "idle";
export type WaitKind = "question" | "approval" | "plan";

/** No conversation text enters this reducer. */
export class IndicatorState {
  private base: LightState = "idle";
  private reasons = new Set<string>();
  private anonymous: Record<WaitKind, number> = { question: 0, approval: 0, plan: 0 };

  value(): LightState {
    return this.reasons.size || Object.values(this.anonymous).some(Boolean) ? "waiting" : this.base;
  }
  start(clearWaits = true): void {
    this.base = "working";
    if (clearWaits) this.clearWaits();
  }
  reset(working = false): void {
    this.clearWaits();
    this.base = working ? "working" : "idle";
  }
  wait(kind: WaitKind, id?: string): void {
    if (id) this.reasons.add(`${kind}:${id}`);
    else this.anonymous[kind]++;
  }
  resolve(kind: WaitKind, id?: string): void {
    if (id) this.reasons.delete(`${kind}:${id}`);
    else this.anonymous[kind] = Math.max(0, this.anonymous[kind] - 1);
  }
  finish(willContinue: boolean, stopReason?: string): void {
    if (willContinue) return;
    this.base = stopReason === "error" ? "error" : stopReason === "aborted" ? "idle" : "done";
    // A plan review can remain open after model work ends. Its reason stays.
  }
  private clearWaits(): void {
    this.reasons.clear();
    this.anonymous = { question: 0, approval: 0, plan: 0 };
  }
}

export function eventId(event: unknown, plan = false): string | undefined {
  if (!event || typeof event !== "object") return undefined;
  const value = plan ? ("reviewId" in event ? event.reviewId : undefined) :
    "toolCallId" in event ? event.toolCallId : "approvalId" in event ? event.approvalId :
      "id" in event ? event.id : undefined;
  return typeof value === "string" && value.length <= 256 ? value : undefined;
}

export function finalStopReason(messages: unknown): string | undefined {
  if (!Array.isArray(messages)) return undefined;
  for (let i = messages.length - 1; i >= 0; --i) {
    const message: unknown = messages[i];
    if (message && typeof message === "object" && "role" in message && message.role === "assistant") {
      return "stopReason" in message && typeof message.stopReason === "string" ? message.stopReason : undefined;
    }
  }
  return undefined;
}
