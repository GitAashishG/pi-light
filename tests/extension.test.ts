import { describe, expect, test } from "bun:test";
import { IndicatorState, finalStopReason } from "../extension/state";
import { Publisher, type Update } from "../extension/publisher";

describe("agent indicator semantics", () => {
  test("one resolved question cannot hide a concurrent approval", () => {
    const state = new IndicatorState();
    state.start(); state.wait("question", "q1"); state.wait("approval", "a1");
    state.wait("question", "q1");
    state.resolve("question", "q1"); expect(state.value()).toBe("waiting");
    state.resolve("approval", "a1"); expect(state.value()).toBe("working");
  });
  test("nonterminal background/retry pause never announces completion", () => {
    const state = new IndicatorState(); state.start();
    state.finish(true, "stop"); expect(state.value()).toBe("working");
    state.finish(true, "error"); expect(state.value()).toBe("working");
    state.finish(false, "stop"); expect(state.value()).toBe("done");
    state.start(); expect(state.value()).toBe("working");
  });
  test("a plan review stays waiting after model work finishes", () => {
    const state = new IndicatorState(); state.start(); state.wait("plan", "p1");
    state.finish(false, "stop"); expect(state.value()).toBe("waiting");
    state.resolve("plan", "p1"); expect(state.value()).toBe("done");
  });
  test("unrecovered run failure differs from user abort and ordinary continuation", () => {
    const state = new IndicatorState(); state.start(); state.finish(false, "error");
    expect(state.value()).toBe("error");
    state.start(); state.finish(false, "aborted"); expect(state.value()).toBe("idle");
  });
  test("only final assistant metadata is examined, never tool errors or text", () => {
    expect(finalStopReason([{role:"assistant",stopReason:"error",content:"sensitive"}, {role:"toolResult",isError:true}, {role:"assistant",stopReason:"stop",content:"private"}])).toBe("stop");
  });
  test("publisher coalesces intermediate states and never revives a removed session", async () => {
    const sent: Update[] = [];
    const first = Promise.withResolvers<void>();
    const publisher = new Publisher(async message => { sent.push(message); if (sent.length === 1) await first.promise; });
    publisher.update("working"); publisher.update("waiting"); publisher.update("done"); publisher.remove(); publisher.update("working");
    first.resolve(); await publisher.flush();
    expect(sent.length).toBe(2); expect(sent[1].op).toBe("remove");
    expect(sent[1].seq).toBeGreaterThan(sent[0].seq);
    expect(Object.keys(sent[0]).sort()).toEqual(["op","seq","session","state"]);
  });
});
