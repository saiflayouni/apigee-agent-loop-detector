var history = context.getVariable("loop.intent_history") || "";
var intents = history.split("||").filter(function(s) { return s.trim().length > 0; });

var prompt =
  "You are an AI safety guard for agentic systems.\n" +
  "Analyze these recent API requests from an AI agent and determine if the agent is stuck " +
  "in a semantic loop — repeating the same intent in different words.\n\n" +
  "Agent request history (" + intents.length + " recent calls):\n" +
  intents.map(function(s, i) { return (i + 1) + ". " + s; }).join("\n") + "\n\n" +
  "Respond with JSON only (no markdown fences):\n" +
  "{\"loop_confidence\": <0.0-1.0>, \"reason\": \"<one-sentence explanation>\"}";

var requestBody = JSON.stringify({
  contents: [{ parts: [{ text: prompt }] }],
  generationConfig: {
    responseMimeType: "application/json",
    temperature: 0.1,
    maxOutputTokens: 512,
    thinkingConfig: { thinkingBudget: 0 }
  }
});

context.setVariable("gemini.request.body", requestBody);

var apiKey = context.getVariable("propertyset.config.gemini_api_key") || "disabled";
context.setVariable("gemini.api.key", apiKey);
