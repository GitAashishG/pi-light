// Isolated integration-test provider. No network request or real model is used.
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { AssistantMessageEventStream, type AssistantMessage } from "@oh-my-pi/pi-ai";
import { fileURLToPath } from "node:url";

export default function runtimeProvider(api: ExtensionAPI): void {
  let response = 0;
  let held: { stream: AssistantMessageEventStream; message: AssistantMessage } | undefined;
  const kind = process.env.PI_LIGHT_TEST_KIND || "question";
  if (kind === "async") {
    api.on("agent_end", (event) => {
      // Observe conversion metadata only; never inspect or publish messages.
      process.stdout.write(JSON.stringify({
        type: "pi_light_test_extension_end",
        willContinue: event.willContinue ?? null,
        isTerminal: "isTerminal" in event && typeof event.isTerminal === "boolean" ? event.isTerminal : null,
        awaitingAsyncWork: "awaitingAsyncWork" in event && typeof event.awaitingAsyncWork === "boolean" ? event.awaitingAsyncWork : null,
      }) + "\n");
    });
  }
  api.registerCommand("fixture-release", {
    description: "Release only this isolated local test provider",
    handler: async () => {
      if (!held) return;
      const current = held;
      held = undefined;
      current.stream.push({ type: "done", reason: "stop", message: current.message });
      current.stream.end();
    },
  });
  api.registerProvider("pi-light-fixture", {
    baseUrl: "http://127.0.0.1/unused-local-fixture",
    apiKey: "unused-local-fixture",
    api: "pi-light-local-fixture",
    models: [{ id: "fixture", name: "pi-light local fixture", reasoning: false, input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 8192, maxTokens: 1024 }],
    streamSimple(model) {
      const stream = new AssistantMessageEventStream();
      const first = response++ === 0;
      const question = first && kind === "question";
      const approval = first && kind === "approval";
      const failure = kind === "error";
      const asyncJob = first && kind === "async";
      const workerCommand = [process.env.PI_LIGHT_TEST_PYTHON || "python3", fileURLToPath(new URL("./async-worker.py", import.meta.url))]
        .map(value => "'" + value.replaceAll("'", "'\\''") + "'").join(" ");
      const content = question ? [{ type: "toolCall" as const, id: "pi-light-question", name: "ask",
        arguments: { html: '<form><p>Harmless pi-light integration test, not a permission approval.</p><fieldset><legend>Continue the LED test?</legend><label><input type="radio" name="choice" value="continue" checked>Continue test</label></fieldset></form>' } }] :
        approval ? [{ type: "toolCall" as const, id: "pi-light-approval", name: "read",
          arguments: { path: "test-read.txt" } }] :
          asyncJob ? [{ type: "toolCall" as const, id: "pi-light-async", name: "bash",
            arguments: { command: workerCommand, async: true, timeout: 45, pty: false } }] :
            [{ type: "text" as const, text: kind === "async" && response === 2 ?
              "The owned background fixture is still running; yielding until its result arrives." :
              "pi-light runtime fixture completed." }];
      const message: AssistantMessage = {
        role: "assistant", content, api: model.api, provider: model.provider, model: model.id,
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        stopReason: question || approval || asyncJob ? "toolUse" : failure ? "error" : "stop",
        ...(failure ? { errorMessage: "Intentional isolated pi-light fixture failure" } : {}),
        timestamp: Date.now(),
      };
      stream.push({ type: "start", partial: message });
      const call = message.content[0];
      if (call?.type === "toolCall") {
        stream.push({ type: "toolcall_start", contentIndex: 0, partial: message });
        stream.push({ type: "toolcall_delta", contentIndex: 0, delta: JSON.stringify(call.arguments), partial: message });
        stream.push({ type: "toolcall_end", contentIndex: 0, toolCall: call, partial: message });
      }
      if (first && kind === "hold") {
        held = { stream, message };
        return stream;
      }
      if (failure) stream.push({ type: "error", reason: "error", error: message });
      else stream.push({ type: "done", reason: message.stopReason, message });
      stream.end();
      return stream;
    },
  });
}
