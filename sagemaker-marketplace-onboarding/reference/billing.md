# Billing — Hourly vs Per-Inference Reference

The container-side implications of the two Marketplace billing models. This skill covers only the container hooks — the actual Marketplace listing configuration (pricing values, EULA) happens in the Marketplace Management Portal and is outside this skill's scope.

## The customer pays two things

Regardless of which billing model you choose:

1. **Instance usage price** — set by AWS, always per hour per instance.
2. **Model usage price** — set by you, either hourly or per-inference.

## Hourly pricing

- Customer pays $/hour for every instance running your model.
- No container-side code required. `/invocations` returns its result as usual.
- Different prices per instance type are supported.
- Example: $2/hr × 3 instances × 2 hours = $12.

## Per-inference (usage-based) pricing

- Customer pays for units consumed per invocation. **The container must report metering on every invocation.** Fail to report = fail to be paid for that invocation.
- Metering emission depends on the endpoint:

### Standard `/invocations` (Real-Time, Streaming response, Batch Transform)

Emit metering as an HTTP response header. The value is a JSON string.

```
X-Amzn-Inference-Metering: {"Dimension": "inference.count", "ConsumedUnits": 3}
```

**Mini-batch semantics.** If a single `/invocations` call processes multiple inferences (e.g. batching several inputs), set `ConsumedUnits` to the number of inferences processed. For a single-inference call, use `1`.

**Only 2XX responses are billed.** AWS Marketplace charges the buyer only for responses with HTTP status codes in the 2XX range. Metering on 4XX/5XX responses is ignored. Conversely, do not return 200 with a silent error body — you would be paid for a failed inference. Make error paths return proper non-2XX codes.

Reference: https://docs.aws.amazon.com/marketplace/latest/userguide/machine-learning-pricing.html

### Bidirectional WebSocket (`/invocations-bidirectional-stream`)

A bidi session's total usage isn't known until the stream ends, so the response header above can't
carry it. Instead, the container reports usage **mid-stream** on a **companion metadata WebSocket**
(never on the main data stream): it sends small JSON metering frames as usage accrues, and SageMaker
validates each frame, drops malformed ones, de-duplicates by `ClientToken`, and reports the units to
AWS Marketplace. It is the same `inference.count` dimension and the same per-unit listing price as the
header path — the only difference is that units can be reported while the session is still running.
A frame with `ConsumedUnits: 0` is accepted (e.g. an interval with no billable usage).

See `reference/websocket.md` for the full protocol: opt-in headers, message schema, size/rate limits
(512 bytes, 1 msg/sec), and failure-mode behavior (`X-Amzn-SageMaker-Metadata-Stream-Required`).

References: the bidirectional streaming feature itself is introduced in the AWS ML blog post
["Introducing bidirectional streaming for real-time inference on Amazon SageMaker
AI"](https://aws.amazon.com/blogs/machine-learning/introducing-bidirectional-streaming-for-real-time-inference-on-amazon-sagemaker-ai/);
the `inference.count` metering header is documented in the [Marketplace ML pricing
guide](https://docs.aws.amazon.com/marketplace/latest/userguide/machine-learning-pricing.html); the
metadata-channel protocol is summarized in `reference/websocket.md`.

## The dimension is always `inference.count`

ML product listings bill per-inference usage on a single, fixed dimension: **`inference.count`**. You
cannot register a custom dimension name such as `audio_seconds`, `tokens`, or `characters` on an ML
listing — do not try to configure one, and do not emit one from the container. Every metering record,
header or metadata frame, uses `"Dimension": "inference.count"`.

To price by something other than requests, **scale `ConsumedUnits`**: decide what one unit of
`inference.count` represents, report that many units, and set the listing's per-inference price as
the price of one unit.

| Modality | What one unit typically represents | `ConsumedUnits` to report |
|---|---|---|
| Any (simplest) | One request / inference | `1` (or the mini-batch size) |
| STT / TTS / audio | One second of audio processed or produced | Seconds of audio |
| TTS | A block of characters synthesized | Characters ÷ block size |
| LLM / vision-language | A block of tokens | Tokens ÷ block size |
| Text embedding | A block of input characters or tokens | Input length ÷ block size |
| Image models | One image, or a block of pixels | Images, or pixels ÷ block size |

Recommended: when the underlying quantity is fractional (e.g. part of a second of audio), accumulate
it and report whole units, carrying the remainder forward — `metering.py`'s `UnitAccumulator` shows
this pattern. It keeps each record's units exact without rounding every request up.

Whatever unit you pick becomes part of the customer contract — document it on the listing (e.g.
"price per inference = price per second of audio") so buyers can predict their bill.

## Price granularity: choose the unit size up front

Listing prices support three decimal places, so the minimum price is **$0.001 per unit**. If your
per-second price is lower than that, define a larger unit (e.g. 1 unit = 10 seconds of audio) and
price that unit instead. The unit size lives in the model server's metering code, not on the listing,
so changing it later means a new model package version and re-validation. Decide it before you submit
and keep it in one named constant (`QUANTITY_PER_UNIT` in `metering.py`).

## Critical pricing rules

- **You cannot switch models.** Hourly ↔ per-inference is a new listing.
- **Once a price is set** and the product reaches limited state, you cannot change it on your own. Changes go through AWS support.
- **90-day freeze** after any price update. During the freeze:
  - You cannot add or remove supported instance types.
  - Existing subscribers stay on the old price for 90 days.
  - New subscribers get the new price immediately.
- **Workaround for the freeze:** create a new product and unpublish the old one.
- **Do not choose "Free"** if you plan to charge later. Use "$0/hour" instead — a Free listing cannot be converted to paid.

## Currency

- Public pricing: **USD only**.
- Private offers: USD or INR (useful for India-based listings).

## Private offers

Enterprise-specific pricing with a custom EULA and duration. Contract-based (fixed payment, unlimited access for the duration). Cannot mix pricing types — a hourly public listing cannot have a per-inference private offer.

Required inputs for a private offer:
- ProductId
- Targeted Buyer AWS Account(s)
- Offer acceptance deadline
- Offer duration (in days)
- Custom EULA file (optional)
- Prices per instance type

Configuration happens in the Marketplace Management Portal — outside this skill's scope.

## Container-side implication summary

| Setup | What the container must do |
|---|---|
| Hourly pricing, no WebSocket | Nothing special. Return inference results. |
| Hourly pricing, WebSocket | Nothing special beyond the WebSocket contract. |
| Per-inference, `/invocations` only | Emit `X-Amzn-Inference-Metering: {"Dimension": "inference.count", "ConsumedUnits": N}` on every 2XX response, with N scaled to your unit. |
| Per-inference, WebSocket | Advertise metadata support in upgrade response, emit `inference.count` metering frames on the companion channel as usage accrues. |
