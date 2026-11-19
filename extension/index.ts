import type { ExtensionAPI, ExtensionContext } from "@oh-my-pi/pi-coding-agent";
import { IndicatorState, eventId, finalStopReason } from "./state";
import { Publisher } from "./publisher";

export default function piLight(api: ExtensionAPI): void {
  const state = new IndicatorState();
  let publisher: Publisher | undefined;
  let clearHeartbeat: (() => void) | undefined;

  const isMain = (ctx: ExtensionContext) => ctx.agent.kind === "main";
  const emit = () => publisher?.update(state.value());
  const stop = () => {
    try { clearHeartbeat?.(); } catch { /* Session already disposed. */ }
    clearHeartbeat = undefined;
    publisher?.remove();
    publisher = undefined;
  };
  const start = (ctx: ExtensionContext) => {
    if (!isMain(ctx)) return;
    stop();
    state.reset(typeof ctx.isIdle === "function" && !ctx.isIdle());
    publisher = new Publisher();
    const timer = ctx.setInterval(() => { try { emit(); } catch { /* Never fail a session. */ } }, 3000);
    clearHeartbeat = () => ctx.clearTimer(timer);
    emit();
  };
  const active = (ctx: ExtensionContext) => {
    if (!isMain(ctx)) return false;
    if (!publisher) start(ctx);
    return true;
  };

  api.on("session_start", (_event, ctx) => start(ctx));
  api.on("session_switch", (_event, ctx) => start(ctx));
  api.on("session_clear", (_event, ctx) => { if (active(ctx)) { state.reset(); emit(); } });
  api.on("session_shutdown", (_event, ctx) => { if (isMain(ctx)) stop(); });
  api.on("agent_start", (_event, ctx) => { if (active(ctx)) { state.start(); emit(); } });
  api.on("before_agent_start", (_event, ctx) => { if (active(ctx)) { state.start(false); emit(); } });
  api.on("agent_end", (event, ctx) => {
    if (!active(ctx)) return;
    state.finish(event.willContinue === true, finalStopReason(event.messages));
    emit();
  });
  api.on("tool_execution_start", (event, ctx) => {
    if (event.toolName !== "ask" || !active(ctx)) return;
    state.wait("question", eventId(event));
    emit();
  });
  api.on("tool_execution_end", (event, ctx) => {
    if (event.toolName !== "ask" || !active(ctx)) return;
    state.resolve("question", eventId(event));
    emit();
  });
  api.on("tool_approval_requested", (event, ctx) => {
    if (!active(ctx)) return;
    state.wait("approval", eventId(event));
    emit();
  });
  api.on("tool_approval_resolved", (event, ctx) => {
    if (!active(ctx)) return;
    state.resolve("approval", eventId(event));
    emit();
  });
  api.on("plan_review_requested", (event, ctx) => {
    if (!active(ctx)) return;
    state.wait("plan", eventId(event, true));
    emit();
  });
  api.on("plan_review_resolved", (event, ctx) => {
    if (!active(ctx)) return;
    state.resolve("plan", eventId(event, true));
    emit();
  });
}
