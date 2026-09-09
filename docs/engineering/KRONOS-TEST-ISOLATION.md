# KRONOS automated-test production isolation

Status: Engineering candidate — Sponsor review required before publication.
Authority: Sponsor TEST ISOLATION HARDENING bounded correction before WO-07B
requalification. This changes qualification infrastructure, not product authority.

## Root cause and scope

`tests/unit/browser/test_browser_server.py::_running_server` omits native store
roots. `create_browser_server` constructs `NativeReviewEvidenceStore()` and derives
UX10, notification-centre and monitoring stores from that root. Constructor
restoration can retain monitoring-unavailable evidence. Many Intraday Review,
WO-10+, live-shadow and runtime-control default paths are also evaluated from
`Path.home()` when their modules are imported. Setting a late fixture environment
variable cannot relocate already-bound defaults. `KRONOS_HOME` was not a universal
store override. Configuration uses the real home too; dotenv and inherited
Provider/OpenAI/Telegram settings are additional inputs.

This establishes a reachable production-store exposure. It does not establish
which actor created or modified previously observed Swing evidence. Preserve that
evidence and the earlier failed preservation report without assigning a writer.

One default bypassed home configuration entirely: `intraday/review_pdf.py` had two
literal `/Users/imranali` Question/Answer directories. They now derive the same
relative directories from `Path.home()`, matching existing configuration practice.
For the Sponsor's production account their resolved paths are unchanged. The
existing clipboard test now asserts these home-relative defaults. An OpenAI
Settings test scopes its absence assertion to its own section: a clean temporary
Telegram configuration legitimately displays NOT CONFIGURED elsewhere.

No frozen WO-07B path changes are required. No product store is reimplemented.

## Required entry point

From the repository run:

```sh
.venv/bin/python tools/kronos_test.py -q tests -p no:cacheprovider
```

Arguments after the launcher are pytest arguments. Explicit JUnit/report paths
remain caller-owned; they must not target protected product directories. The
launcher supports the qualified macOS kernel sandbox. Other platforms fail closed
until an equivalent backend is separately qualified. Bare pytest fails at root
conftest import before test collection. There is no unguarded fallback.

## Before-import isolation

The launcher creates a disposable root, home, manifest, controlled denied fixture
and kernel probes. It captures the operating-account home, inherited HOME and any
inherited KRONOS_HOME before clearing operational environment settings. HOME itself
is not reassigned. `sitecustomize` installs Python isolation before any Kronos
import; root conftest verifies it again. Python `Path.home()` points to the temporary
home. A too-late bootstrap fails rather than retaining old imported defaults. The
standalone `kronos_test_isolation` namespace is outside `kronos.*` and `tools.*`,
so test bootstrap does not masquerade as a preloaded application module or weaken
the production launcher's strict immutable-startup verification.

Protected roots include the real KRONOS evidence/runtime tree, Project-KRONOS
configuration tree, Review Pack directories, installed KRONOS app, inherited
KRONOS_HOME and repository/ancestor dotenv files. Explicit path resolution and
absolute store binding fail closed. Kernel file denial remains effective when a
test bypasses Python helpers, uses symlinks, descriptor-relative operations or
launches a native child. Python children receive the bootstrap even with an
explicit minimal environment; `python -I` children remain kernel constrained.

The kernel also denies external network operations, keychain commands,
LaunchServices, launchctl and AppleScript process execution. Fixture servers use
64 temporary loopback ports reserved by the launcher and released just before the
worker starts. Port-zero Python binds select from this pool. Outbound sockets are
allowed only to those exact ports, never the production listener. Exhaustion
fails closed. This is a test-only resource bound, not a production socket change.

Before application import, owned mode-0600 control-file and denied-listener probes
must both produce kernel PermissionError. A readable forged probe or absent guard
cannot pass bootstrap. The temporary default home is cleared between tests;
explicit pytest temporary fixtures retain their normal scoped lifetime. No
production default is silently remapped when explicitly supplied as a path.

## Qualification contract

Controlled fixtures prove real-HOME inheritance, production-like environment
scrubbing, omitted Browser roots, Swing/Intraday default stores, notification and
monitoring restoration, runtime-control and live-shadow roots, Question/Answer
defaults, explicit production binding, direct file operations, symlink and
file-descriptor access, subprocess inheritance, protected listener denial and
unguarded/forged bootstrap rejection. Existing SPH real-HTTP tests continue using
ephemeral fake servers. No real Provider, OpenAI, broker or runtime operation is a
test fixture.

Requalification runs focused isolation, affected Browser/restoration/launcher,
frozen WO-07B focused/affected, and the entire active suite. Record exact counts,
durations, compile/diff/secret checks, separate isolation/frozen candidate hashes,
and before/after production inventories in the external evidence pack. All
baseline bytes must match. Preserve and separately inventory concurrent additions;
path or timestamp alone does not establish actor attribution.

This candidate grants no staging, publication, runtime restart, WO-07C or further
programme authority. It does not erase the earlier failed WO-07B preservation gate.
