/// Extract action text from OpenAI-compatible requests and responses.

interface ChatMessage {
  role: string;
  content: string | null;
}

interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  stream?: boolean;
}

interface ChatCompletionResponse {
  choices: Array<{
    message: {
      content: string | null;
    };
  }>;
}

/// Extract the last user message from a chat completion request.
export function extractRequestText(body: ChatCompletionRequest): string {
  const messages = body.messages ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role === "user" && typeof msg.content === "string") {
      return msg.content;
    }
  }
  return "";
}

/// Extract the model from a chat completion request.
export function extractModel(body: ChatCompletionRequest): string {
  return body.model ?? "unknown";
}

/// Check if the request is a streaming request.
export function isStreaming(body: ChatCompletionRequest): boolean {
  return body.stream === true;
}

/// Extract the system prompt from a chat completion request.
export function extractSystemPrompt(body: ChatCompletionRequest): string {
  const messages = body.messages ?? [];
  for (const msg of messages) {
    if (msg.role === "system" && typeof msg.content === "string") {
      return msg.content;
    }
  }
  return "";
}

/// Extract assistant response text from a chat completion response.
export function extractResponseText(body: ChatCompletionResponse): string {
  const choices = body.choices ?? [];
  if (choices.length > 0) {
    const content = choices[0]?.message?.content;
    if (typeof content === "string") {
      return content;
    }
  }
  return "";
}
