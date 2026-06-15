var MAX_HOPS = 10;
var SEMANTIC_HOP_THRESHOLD = 3; // start semantic checks after this many hops
var ASSUMED_RUNAWAY = 1000;
var COST_PER_CALL = 0.002;

var hopHeader = context.getVariable("request.header.X-Agent-Loop-Count");
var hopCount = hopHeader ? parseInt(hopHeader, 10) : 0;
if (isNaN(hopCount)) hopCount = 0;

context.setVariable("loop.hop_count", String(hopCount));

// Extract intent from JSON body (field: intent / query / message)
var body = context.getVariable("request.content") || "";
var intent = "";
try {
  var parsed = JSON.parse(body);
  intent = parsed.intent || parsed.query || parsed.message || body.substring(0, 120);
} catch (e) {
  intent = body.substring(0, 120) || "request";
}
context.setVariable("loop.current_intent", intent);

// Accumulate intent history (client mirrors it back in X-Agent-History)
var historyHeader = context.getVariable("request.header.X-Agent-History") || "";
var history = historyHeader ? historyHeader.split("||") : [];
history.push(intent);
if (history.length > 5) history = history.slice(-5);
var intentHistory = history.join("||");
context.setVariable("loop.intent_history", intentHistory);

var apiKey = context.getVariable("propertyset.config.gemini_api_key") || "disabled";
context.setVariable("gemini.api.key", apiKey);

var doSemantic = (hopCount >= SEMANTIC_HOP_THRESHOLD && hopCount < MAX_HOPS && apiKey !== "disabled");
context.setVariable("loop.do_semantic_check", doSemantic ? "true" : "false");

if (hopCount >= MAX_HOPS) {
  var callsPrevented = ASSUMED_RUNAWAY - hopCount;
  var costSaved = parseFloat((callsPrevented * COST_PER_CALL).toFixed(2));

  context.setVariable("loop.detected", "true");
  context.setVariable("loop.response_json", JSON.stringify({
    error: "loop_detected",
    detection_type: "structural",
    message: "Agentic loop detected: request hop count exceeded limit",
    hop_count: hopCount,
    calls_prevented: callsPrevented,
    cost_saved_usd: costSaved
  }));
} else {
  context.setVariable("loop.detected", "false");
  context.setVariable("request.header.X-Agent-Loop-Count", String(hopCount + 1));
  context.setVariable("request.header.X-Agent-History", intentHistory);
}
