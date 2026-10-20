# Replay a saved record with explicit process limits

`bj-replay` captures one saved decision file, recomputes its original recorded
model in an owned disposable worker, and keeps a complete comparison only after
the worker and transport have retired. It uses the existing replay dispatcher.
Saved answers remain comparison data. The numerical model, recorded state cap
and exact comparison policy remain unchanged.

This is a separate installed command. `bj-advise --replay`, `replay_json` and
`replay_file` retain their direct, caller-owned behavior. No development checkout
is needed at runtime. Use the environment containing the installed package:

```sh
python -m pip install "https://github.com/T92T1914/exact-blackjack-solver/archive/refs/heads/main.zip"
bj-replay saved-decision.json --output-dir replay-001 --wall-seconds 30
```

The archive installation selects the current public revision. A release packet
can identify an exact archive or reviewed wheel instead. This does not install
a historical engine because of a package label in the saved file. The command
is also available as `python -I -m bj.supervised_replay`.

To obtain a small genuine record through the existing installed calculation,
use the request from the [local calculation guide](https://github.com/T92T1914/exact-blackjack-solver/blob/main/docs/local-calculation.md):

```sh
bj-calculate request.json --output-dir calculation-001 --wall-seconds 30
bj-replay calculation-001/result/decision.json --output-dir replay-001 --wall-seconds 30
```

Use a new output directory for every attempt. Earlier results are never
overwritten, retried or resumed automatically.

## Capture and model selection

The input must be one ordinary local regular file. The parent sends only a
bounded local path to the fixed worker after the owner establishes its policy.
Original-file lookup, open, descriptor checks and a read of at most 65,536 bytes
plus one oversize witness happen inside that same contained process. Devices,
pipes, links, reparse points and Windows network/device namespaces are refused.
Windows opens use `OPEN_REPARSE_POINT` for the final component. POSIX opens use
nonblocking, no-follow flags. The descriptor must remain an ordinary file with
the inspected identity. Ancestor checks are not an atomic no-follow traversal:
a raced or stalled lookup is contained by the worker policy.

The worker captures the bytes once. A later replacement of the original cannot
change its replay. Capture does not modify the original. Concurrent editing
during a read is not an atomic filesystem snapshot guarantee. The parent never
rereads the original and parses no saved JSON before the worker has retired.

The exact captured bytes, including whitespace and number representation, are
exclusively retained as `record-source.json`. After observed retirement, the
parent reads this owned artifact with the same byte bound and joins the worker's
byte count and SHA256 before accepting any report. `capture_verified: true`
means that joined identity was observed. It does not make an oversized prefix a
complete source: its `source_record.complete` is false, and its digest is not the
digest of the entire larger file. A partial file left by interruption before a
complete worker message remains diagnostic and has no verified capture identity.
Hashes identify bytes, not authenticated origin.

The fixed contained worker parses and admits those captured bytes through the
existing replay function. UTF-8, duplicate-key, finite-number, eight-container
depth and supported schema/model checks remain in effect. Schemas 1 through 6
retain their original ordinary, controlled, two-hand common-shoe, late-surrender,
bounded non-ace resplit and bounded one-card ace resplit meanings. Their counts
already exclude visible cards and include the hidden hole. They are used once.
The separately selected [deferred second-card family](deferred-second-card-calculation.md)
uses schema 7. It retains its no-peek timing, no dealt hole and loss of every
committed wager to a later dealer natural. Replay preserves that family's
recorded state and cooperative time limits rather than substituting a post-peek model.

The saved action, values and margin are never calculation inputs. A supported
changed answer or missing action produces differences when recomputation
finishes. Unknown models, unsupported caps and unavailable required
continuations remain refusals. The command does not lower or raise a recorded
algorithmic cap, substitute an approximation or install another package version.

## Policy and platform limits

On Windows the default policy is a 256 MiB aggregate Job committed-memory cap:

```sh
bj-replay saved-decision.json --output-dir replay-001 --wall-seconds 30 --memory-mib 256
```

Supported memory values are 64 through 4096 MiB. This is committed memory in the
owned Job, not physical resident memory. The hidden fixed worker waits for its
path envelope. Verified Job creation, limits and assignment precede release of
the input, replay imports and original-file lookup. If containment cannot be
established, capture and replay do not begin. The existing owner retains
kill-on-close ownership and fault-dialog
suppression for associated processes without changing the host's global mode.

On Linux omit `--memory-mib`. The existing policy remains wall-only and
memory-uncapped, owning one fixed direct worker in a fresh session. That worker
creates no descendants. A requested hard-memory mode refuses before capture or
startup. Other operating systems are unsupported for this command.

The default worker deadline is 30 seconds. Select a positive value at most 300.
It covers worker startup, original-file lookup/capture, replay and complete
transport, with a separate five-second cleanup allowance. Expiry initiates
retirement. It is not an exact whole-command duration promise. Parent output
directory setup, reading the retired worker's owned artifact, result publication,
ordinary operating-system startup calls and subsequent cleanup have separate
boundaries. Parent artifact I/O is bounded and descriptor checked, but a byte
limit is not a hard deadline for ordinary filesystem calls.

The local path is bounded to 4,096 UTF-8 bytes and its input envelope to 32,768
bytes. Each worker stream keeps
the existing 65,536-byte bound. A valid source can yield a larger replay message,
for example through expanded Unicode labels or comparison data. Such a result
is refused completely rather than truncated. Old calculation transport and
input limits remain unchanged.

Recorded model caps and cooperative limits still apply. Legacy models have no
algorithmic-state cap. The receipt reports only model work actually supplied on
an applicable refusal. Elapsed time and byte limits are not mathematical state
counts. Worker caches retire with that process. Parent caches are not cleared.

## Results, differences and incomplete outcomes

An accepted comparison publishes:

- `result/replay.json`: the existing complete replay report.
- `result/receipt.json`: capture identity, selected and established policy,
  worker exit, retirement observations and report byte count/digest.

`agreement` exits 0. `differences` exits 1 and is also a completed calculation.
The report preserves `exact_binary_float`: zero absolute/relative tolerance,
numeric binary-float equality and exact action identity. It does not compare
signed zero or authenticate record origin. A one-step float difference remains
visible. Agreement demonstrates reproduction by the selected engine, not an
independent mathematical validation.

Invalid/unsupported records and incomplete calculations publish no `result`
directory. Their received worker output is diagnostic. `attempt.json` is a
prepared attempt, not acceptance. `pending-result` contains staged candidates.
`outcome.json` retains failure and cleanup observations when storage permits.
An unverified `record-source.json` after timeout, cancellation or unexpected
failure is also diagnostic. A successful capture does not itself accept a replay.

| Status | Exit | Meaning |
| --- | ---: | --- |
| `agreement` | 0 | Complete recomputation, all compared fields agree, retirement verified and result committed |
| `differences` | 1 | Complete recomputation with visible differences, retirement verified and result committed |
| `invalid_input` | 2 | Malformed or oversized saved data |
| `unsupported_record` | 3 | Schema, rules, cap or model outside supported replay |
| `unsupported_policy` | 3 | Requested platform policy unavailable or containment not established |
| `resource_limited` | 4 | Model/resource refusal or bounded complete replay transport could not fit |
| `calculation_error` | 5 | Admitted required calculation could not complete |
| `io_error` | 6 | Source could not be captured as an ordinary local file |
| `worker_failed` | 6 | Unexpected exit, malformed message or identity/comparison inconsistency |
| `cleanup_failed` | 7 | Returned data withheld because retirement remained unresolved |
| `delivery_failed` | 8 | Capture/result/receipt/report could not be completely delivered |
| `timed_out` | 124 | Worker deadline caused retirement without an accepted comparison |
| `cancelled` | 130 | Explicit cancellation won before publication |
| `interrupted` | 130 | The original replay dispatcher returned interruption |

Timeout is not disagreement. An unexplained exit is worker failure, rather than
proof of a particular memory limit. The receipt keeps cleanup observations
separate from the primary outcome. No returned comparison is accepted while
owned retirement remains unresolved.

Press Ctrl+C to cancel this attempt. Cancellation observed before the final
publication choice wins even when the worker has returned. After the complete
result directory commits, a later cancellation does not erase or relabel it.
Writes, flushes, closes and the final directory rename must succeed. A staged
partial report is never a completed verification result. Flush/rename is not a
durable-storage or crash-recovery guarantee. If stdout delivery fails after
commit, the command exits with delivery failure while preserving completed
files. Inspect their receipt before deciding to run again.

## Reuse the existing inspector

Open the [project inspector](https://t92t1914.github.io/exact-blackjack-solver/)
and select the unchanged admitted `record-source.json`, or your original saved
decision. It displays the modeled inputs and saved values and can compare a
second decision file. It does not recompute, upload the record or interpret
`replay.json`/attempt receipts. The replay report's bare recomputed decision is
not a newly exported full decision record.

Keep the captured source, complete report and receipt together when recording
evidence. Their identity and operational observations answer different questions.
Sharing any local files remains a separate deliberate action.
