"""
Per-inference billing metering for SageMaker Marketplace.

This module is opt-in. Only include it if your Marketplace listing uses
per-inference (usage-based) pricing rather than hourly pricing.

Two emission modes, depending on which endpoint is being billed:

1) Standard /invocations (Real-Time, Streaming response, Batch Transform):
   Emit metering as an HTTP RESPONSE header. The value is a JSON string.

       X-Amzn-Inference-Metering: {"Dimension": "inference.count", "ConsumedUnits": 3}

   Mini-batch semantics: if a single /invocations call processes multiple
   inferences (e.g. batching several inputs per request), set ConsumedUnits
   to the number of inferences processed. For a single-inference call, use 1.

   IMPORTANT: AWS Marketplace only charges the buyer for responses with
   HTTP status codes in the 2XX range. Do not emit metering on 4XX/5XX
   responses — it will be ignored. Conversely, if you return 200 with a
   silent error body, you WILL be paid, so make error paths return proper
   non-2XX status codes.

2) Bidirectional WebSocket (/invocations-bidirectional-stream):
   Metering goes on a COMPANION metadata WebSocket at
   /invocations-bidirectional-stream-metadata, NOT on the main data stream.
   Container signals support via X-Amzn-SageMaker-Metadata-Stream-Supported: true
   in the WebSocket upgrade response, then emits frames mid-stream like:
       {"Metering": {"Dimension": "inference.count", "ConsumedUnits": 720,
                     "ClientToken": "<uuid>"}}
   (here: a product priced per second of audio reports 12 minutes of
   metered audio = 720 seconds). Each record reports the units consumed
   since the previous record, not a running total; billing sums all records
   in the session.

The dimension is ALWAYS "inference.count". ML product listings do not support
custom dimension names (no "audio_seconds", "tokens", etc.). To price by
seconds, tokens, characters, or pixels, scale ConsumedUnits instead: decide
what one unit represents (QUANTITY_PER_UNIT below), report that many units,
and set the listing's per-inference price as the price of one unit.

Listing prices support three decimal places ($0.001 minimum per unit). If
your per-second price is lower, define a larger unit (e.g. 1 unit = 10
seconds). Changing QUANTITY_PER_UNIT later means a new model package version
and re-validation, so pick it before submitting. See reference/billing.md,
"Price granularity".

CRITICAL: If per-inference billing is enabled on your listing but the
container fails to emit metering, you will not be paid for those invocations.
Emit metering on EVERY successful /invocations response.

Documentation: https://docs.aws.amazon.com/marketplace/latest/userguide/machine-learning-pricing.html
"""

import json
import uuid
from typing import Any, Dict


# Fixed by the Marketplace ML metering contract -- do not change.
DIMENSION = "inference.count"

# How much billable usage one unit of inference.count represents, in whatever
# quantity your model bills by. Examples:
#   - 1   — one request, or one second of audio (STT/TTS)
#   - 10  — ten seconds of audio, if quantities are seconds
# The listing's per-inference price is the price of ONE such unit. Pick this
# once, before validation: changing it means a new model package version and
# re-validation.
QUANTITY_PER_UNIT = 1


class UnitAccumulator:
    """
    Recommended pattern (not a platform requirement): convert a fractional
    billable quantity (e.g. part of a second of audio) into whole
    inference.count units, carrying the remainder forward so nothing is lost
    or rounded up across records.

    Example (bidirectional stream, 1 unit = 1 second of audio):
        acc = UnitAccumulator()
        acc.add(audio_chunk_seconds)      # on every chunk processed
        units = acc.take_units()          # once per second, on the metadata channel
        await websocket.send_text(json.dumps(make_metering_frame(units)))
    """

    def __init__(self, quantity_per_unit: float = QUANTITY_PER_UNIT) -> None:
        if quantity_per_unit <= 0:
            raise ValueError("quantity_per_unit must be > 0")
        self.quantity_per_unit = quantity_per_unit
        self._pending = 0.0

    def add(self, quantity: float) -> None:
        if quantity < 0:
            raise ValueError("quantity must be >= 0")
        self._pending += quantity

    def take_units(self) -> int:
        """Return the whole units accrued since the last call; keep the remainder."""
        units = int(self._pending // self.quantity_per_unit)
        self._pending -= units * self.quantity_per_unit
        return units


def inference_metering_header(consumed_units: int) -> str:
    """
    Format the value for the X-Amzn-Inference-Metering response header on a
    standard /invocations response.

    Example:
        response.headers["X-Amzn-Inference-Metering"] = \\
            inference_metering_header(3)
        # → '{"Dimension": "inference.count", "ConsumedUnits": 3}'

    For mini-batch requests where the invocation processes multiple inferences,
    pass the batch size:
        inference_metering_header(len(batch_inputs))

    Only emit this on 2XX responses — Marketplace ignores metering on error
    responses (and does not charge the buyer).
    """
    return json.dumps({
        "Dimension": DIMENSION,
        "ConsumedUnits": int(consumed_units),
    })


def make_metering_frame(
    consumed_units: float,
    client_token: str = "",
) -> Dict[str, Any]:
    """
    Build the JSON metering frame sent on the companion metadata WebSocket
    (/invocations-bidirectional-stream-metadata) for bidirectional streaming
    per-inference billing. SageMaker validates each frame, de-duplicates by
    ClientToken, and reports the units to AWS Marketplace under the same
    inference.count dimension as the header path -- just mid-stream.

    ClientToken is a per-frame idempotency key (max 64 chars). Auto-generated
    if empty. A duplicate ClientToken sent again on the same connection is
    recorded only once by SageMaker.

    Constraints enforced by the metadata channel (validate before sending,
    not after -- SageMaker silently drops malformed frames rather than
    erroring back):
      - Dimension: always "inference.count".
      - ConsumedUnits: number >= 0 (0 is allowed, e.g. an interval with no
        billable usage).
      - Exactly ONE metering record per WebSocket text frame -- never batch
        multiple records into one frame.
      - Max frame size: 512 bytes total (the serialized JSON, not just the
        payload). A long ClientToken can blow this budget on otherwise-small
        payloads -- keep it short (max 64 characters).
      - Max send rate: 1 message per second per connection. Sending faster
        risks dropped messages; batch your own accounting and flush at most
        once per second rather than one frame per inference event.
      - Text frames only -- binary frames are not accepted for metering.

    Recommended calling pattern: call this at most once per second with the
    INCREMENTAL units consumed since the previous record, not a running
    total (billing sums all records in the session) --
    UnitAccumulator.take_units() returns exactly that.
    Sending incrementally means a mid-stream disconnect still gets the
    provider paid for usage reported up to that point.
    """
    if isinstance(consumed_units, bool) or not isinstance(consumed_units, (int, float)):
        raise TypeError("ConsumedUnits must be a number")
    if consumed_units < 0:
        raise ValueError("ConsumedUnits must be >= 0")
    frame = {
        "Metering": {
            "Dimension": DIMENSION,
            "ConsumedUnits": consumed_units,
            "ClientToken": client_token or str(uuid.uuid4()),
        }
    }
    encoded_len = len(json.dumps(frame).encode("utf-8"))
    if encoded_len > 512:
        raise ValueError(
            f"metering frame is {encoded_len} bytes; SageMaker's metadata "
            "channel caps frames at 512 bytes -- shorten ClientToken"
        )
    return frame
