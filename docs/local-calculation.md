# Calculate one request and keep its result

`bj-calculate` captures one supported request, computes its decision in an
owned disposable worker and retains an ordinary decision file only with a
completed result receipt. Earlier attempts are never overwritten. The existing
`bj-advise`, record, replay and browser inspection interfaces remain available
with their existing behavior.

Use the Python environment containing the installed package. The command is
also available as `python -I -m bj.calculation`. No development checkout is
needed at runtime. Install a reviewed wheel through the existing package
installation route, or install the repository using pip:

```sh
python -m pip install "https://github.com/T92T1914/exact-blackjack-solver/archive/refs/heads/main.zip"
```

This installs the revision available at that time. A release acceptance packet
can instead identify an exact wheel or source revision. Package version labels
alone do not identify all its implementation bytes. No registry publication
or historical version acquisition is implied by this command. This source
archive route requires network access and pip's normal build backend and
dependency installation support. It does not require Git or a development
checkout. The archive also contains the small request example and this guide.

## Supply modeled inputs

Save the following as `request.json`, or save the
[small example request](../examples/calculation-request.json). Its six unseen
cards keep the example calculation small.

```json
{
  "schema": {"name": "solver-calculation-request", "version": 1},
  "rules": {},
  "input": {
    "cards": ["T", "4"],
    "dealer_up": "T",
    "unseen_counts": [0, 1, 1, 0, 0, 0, 1, 1, 1, 1],
    "is_split_hand": false,
    "hand_count": 1,
    "can_double": true,
    "can_split": true
  }
}
```

`rules` accepts supported `Rules` fields. Omitted fields receive the existing
defaults, and the captured request expands all effective values before dispatch.
For example, `{"blackjack_payout": 1.25, "max_hands": 2}` selects a finite
nonnegative natural payout and a two-hand round cap. The request supplies no
saved answer, recommendation or EV. Unknown fields are refused.

The ten counts are in `A,2,3,4,5,6,7,8,9,T` order. They already exclude visible
cards and include the hidden dealer hole. They are supplied to the existing
exporter once, without another subtraction. This first request interface
requires explicit counts. It does not infer a fresh shoe or external table
state. Card strings use the existing aliases and normalize without changing
their dealt order. The first card identifies a split hand's original rank.

`hand_count` includes completed hands in the round. An unsplit hand requires
one, and a split hand requires at least two within the selected cap. The
current action controls only exclude the present double or split alternative.
They do not change continuation rules. Supported calculations retain the
hidden-hole post-peek model, ordinary split-21 settlement, stated payout and
the existing independent-hand/shared-budget split approximations. No surrender,
no-peek settlement, insurance calculation or general split error bound is added.

Input admission is limited to 65,536 UTF-8 bytes and eight nested containers.
Duplicate keys, nonfinite data and invalid state/rules are refused before
worker startup. These are representation limits. A small JSON request can
still describe an expensive calculation.

## Select execution policy

On Windows:

```sh
bj-calculate request.json --output-dir run-001 --wall-seconds 30 --memory-mib 256
```

The default Windows cap is 256 MiB. It is aggregate committed memory in the
owned Windows Job, not a physical resident-memory measurement. Supported
values are 64 through 4096 MiB. The fixed hidden worker waits for its captured
input. Job creation, limit setup and assignment must succeed before that input
is sent and before pricing code is imported. Refusal launches no computation.
Kill-on-close ownership also covers processes contained in that Job.
The Job also suppresses foreground fault dialogs for associated owned processes
through `JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION`. The host's global error
mode is unchanged, and this flag is checked with the other required Job limits.
The committed-memory and ownership meanings follow Microsoft's
[extended Job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)
and [basic Job limit flags](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information).

On Linux:

```sh
bj-calculate request.json --output-dir run-001 --wall-seconds 30
```

Linux support is explicitly wall-only, with uncapped memory. The fixed worker
runs in a fresh session and does not create descendants. This interface owns
that direct worker, not arbitrary user programs or process trees. A requested
`--memory-mib` is refused before worker startup. Other operating systems are
currently refused. The policy is printed to stderr before work begins and
retained in the final receipt. Do not use Linux wall-only mode when a hard
memory cap is required.

The default worker deadline is 30 seconds, and a positive value up to 300 can
be selected. It covers startup, calculation and complete message receipt. The
parent observes a monotonic deadline and initiates retirement when it expires.
Ordinary operating-system startup calls and subsequent cleanup are not a
promise of exact command duration. Cleanup has a separate five-second
allowance, and unresolved cleanup is visible rather than reported as success.
Each worker stream is bounded to 65,536 bytes. No production enumeration-state
or algorithmic-work cap is implemented. Caches belong to the disposable worker
and retire with it. Parent/shared caches are not cleared.

## Completion, cancellation and failure

Use a new output directory under an existing ordinary directory. The command
owns that attempt directory. Leave its files unchanged while the attempt runs.
It captures the source request bytes once, then retains its expanded normalized
request and their separate SHA256 identities. Replacing the original request
after dispatch cannot change the captured calculation. Hashes establish byte
identity, not authenticated origin.

An attempt contains `request-source.json`, `request.json` and `attempt.json`.
The initial capture is not a completed result. Received worker streams are
retained when present. Success publishes the complete `result` directory with:

- `result/decision.json`, an unchanged V1 or V2 decision format suitable for
  existing consumers.
- `result/receipt.json`, the completed attempt, request identity, applied policy,
  worker exit, retirement observations and decision byte count/digest.

The receipt distinguishes the selected `policy` from the parent's
`policy_established` observation. A refused Job setup or assignment has no
established policy and no accepted decision.

The parent checks the complete worker message and record admission, captured
inputs, rules, controls, finite values, recommendation consistency and ordinary
worker exit before publication. Those checks are distinct from independently
proving the numerical model. The completed decision remains subject to the
existing [model and replay limits](saved-record-replay.md).

Press Ctrl+C to cancel the owned attempt. Cancellation observed before the final
publication choice wins even if the worker has already returned. After completion
has been selected and the complete result directory committed, a later cancellation
does not relabel or remove that result. No interrupted calculation is retried or
resumed automatically. Retirement is checked, rather than inferred from a sent
termination request.

Staged `pending-result` files and retained worker output are diagnostic candidates,
not completed decisions. A write, flush, close or publication failure produces a
delivery outcome. Failed attempts retain `outcome.json` when storage allows. If
storage also refuses that receipt, stdout/exit retain the failure and its receipt
delivery error. A successful flush or rename is not a durable-storage, atomic
multi-filesystem or crash-recovery guarantee. If reporting to stdout fails after a
result was already committed, the command returns delivery failure while preserving
the completed files. Inspect their receipt rather than rerunning blindly.

| Outcome | Exit | Meaning |
| --- | ---: | --- |
| `completed` | 0 | Complete valid record, ordinary worker exit, verified retirement and committed result |
| `invalid_request` | 2 | Unsupported/malformed request or invalid modeled state before pricing |
| `unsupported_policy` | 3 | Requested platform policy unavailable, or Windows containment could not be established |
| `resource_limited` | 4 | Reported memory/recursion exhaustion or the explicit worker transport cap |
| `calculation_error` | 5 | Admitted state could not be calculated, including exhaustion or arithmetic overflow |
| `worker_failed` | 6 | Unexpected exit, incomplete/invalid message or transport failure |
| `cleanup_failed` | 7 | An otherwise complete record could not be accepted because cleanup remained unresolved |
| `delivery_failed` | 8 | Capture/result/receipt/report could not be completely delivered |
| `timed_out` | 124 | Worker deadline caused retirement without an accepted decision |
| `cancelled` | 130 | Explicit cancellation won before result publication |

The receipt keeps cleanup observations separate from the primary outcome. A
cancelled or failed attempt can also have a cleanup error. No decision is accepted
while retirement remains unresolved. An unexplained nonzero exit or external kill
is a worker failure, not evidence that a particular memory limit was reached.
Unknown options or invalid option text produce the normal command-line usage
error before an attempt is created.

## Reuse the completed file

For this tiny example, recompute the exact retained record through the existing
installed replay interface:

```sh
bj-advise --replay run-001/result/decision.json --json
```

Replay reports agreement or differences separately from calculation/failure
outcomes. It trusts no saved answer as a calculation input. Replay itself retains
its existing caller-owned, unbounded engine behavior. The calculation worker's
deadline and memory policy do not silently apply to this later replay command.

Open the [existing project inspector](https://t92t1914.github.io/exact-blackjack-solver/)
and select `result/decision.json` as local record A. Select another completed record
as B to compare modeled inputs before raw recorded answers. This browser journey
does not recompute EVs, upload the selected file or authenticate its origin. Keep
the request/attempt receipts separately, since they are not decision-record formats.
Publishing or sharing any of these local artifacts is a separate deliberate action.
