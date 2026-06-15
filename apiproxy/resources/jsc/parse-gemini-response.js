var SEMANTIC_BLOCK_THRESHOLD = 0.7;
var COST_PER_CALL = 0.002;
var ASSUMED_RUNAWAY = 1000;

try {
  var statusCode = parseInt(context.getVariable("geminiResponse.status.code") || "0", 10);

  if (statusCode === 200) {
    var responseBody = context.getVariable("geminiResponse.content");
    var response = JSON.parse(responseBody);
    var text = response.candidates[0].content.parts[0].text;
    var result = JSON.parse(text);

    var confidence = parseFloat(result.loop_confidence) || 0;
    var reason = result.reason || "unknown";

    context.setVariable("semantic.loop.confidence", confidence.toFixed(2));
    context.setVariable("semantic.loop.reason", reason);

    if (confidence >= SEMANTIC_BLOCK_THRESHOLD) {
      var hopCount = parseInt(context.getVariable("loop.hop_count") || "0", 10);
      var callsPrevented = ASSUMED_RUNAWAY - hopCount;
      var costSaved = parseFloat((callsPrevented * COST_PER_CALL).toFixed(2));

      context.setVariable("loop.detected", "true");
      context.setVariable("loop.response_json", JSON.stringify({
        error: "loop_detected",
        detection_type: "semantic",
        message: "Semantic loop detected: agent is repeating the same intent",
        hop_count: hopCount,
        semantic_confidence: confidence,
        reason: reason,
        calls_prevented: callsPrevented,
        cost_saved_usd: costSaved
      }));
    }
  } else {
    // Fail open: Gemini unavailable never blocks traffic
    context.setVariable("semantic.loop.confidence", "0");
    context.setVariable("semantic.parse.error", "Gemini returned HTTP " + statusCode);
  }
} catch (e) {
  context.setVariable("semantic.loop.confidence", "0");
  context.setVariable("semantic.parse.error", e.toString());
}
