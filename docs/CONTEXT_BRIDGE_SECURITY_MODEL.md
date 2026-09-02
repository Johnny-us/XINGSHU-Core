---
type: security-model-candidate
status: proposed
scope: public-candidate-documentation
implementation_status: not-implemented
governance_effect: none
authorization_effect: none
activation_effect: none
visibility: public
---

# Context Bridge Security Model

## 1. Scope and Security Claim

This document defines the minimum public security baseline for a future Context Bridge. It is a requirements document, not a production server implementation or a claim that Public Core currently enforces these requirements.

The model assumes Source Content is Untrusted Data even when it comes from an authorized Source. Authorization permits a bounded read; it does not make content, AI output, provider output, or transport input a trusted instruction.

## 2. Threat Actors and Untrusted Inputs

At minimum, an implementation must account for:

- an untrusted caller attempting to forge identity, authority, scope, or Source selection;
- AI output or a Registration Proposal attempting to become final authority;
- a local process attempting to invoke a loopback or local tool surface;
- provider output attempting to override authority, limits, provenance, or failure state;
- stale data presented as current;
- derived data presented as authoritative;
- a malformed, oversized, ambiguous, or inconsistent Source response.

Compromise of a client prompt, transport request, local process, or derived provider must not be sufficient to expand Source access.

## 3. Protected Assets

Protected assets include:

- trusted client identity and profile;
- runtime binding;
- authorized scope;
- Source identity and `source_locator`;
- exact ordered `source_entry_points`;
- Human Authorization evidence;
- Registered Context Reference and lifecycle state;
- Source body;
- credentials and tokens;
- freshness evidence;
- provenance and returned-byte linkage.

The public contract may describe the shape of these assets. Real values belong to the Personal Instance and must not be embedded in Public Core.

## 4. Trust Boundaries

The authority boundary consists of:

- an owner-controlled client profile and runtime binding;
- deterministic validation of object structure, linkage, lifecycle, and authority rules;
- the current Authoritative Source and provider-native observations.

The following are not authority:

- AI suggestions, confidence, or final-answer text;
- caller input, tool arguments, headers, or environment self-report;
- derived-provider output;
- a loopback network location by itself.

`AI Intelligence != Authority`

`Loopback != Authentication`

The canonical Registered Context Reference lifecycle states are `active`, `paused`, `source_unavailable`, `stale_locator`, `revoked`, and `archived`. Only an `active` Reference may proceed toward active use, and it remains subject to all current authorization, freshness, scope, and provenance checks. A `paused` Reference still exists but cannot be used actively; it is neither revoked nor archived, and it may return to `active` only through a legal lifecycle transition with any necessary revalidation.

Stale data, a stale observation, a moved Source, and provider unavailability are conditions or observations, not additional lifecycle states. In particular, a moved or mismatched authorized locator leads to canonical fail-closed handling such as `stale_locator`; `moved` is not a Registered Context Reference state.

## 5. Primary Threats and Required Controls

| Threat | Required control |
|---|---|
| Forged principal or client | Inject identity from an owner-controlled server-side profile and binding; reject caller-supplied principal. |
| Caller scope or Source override | Accept only narrowing selections inside the Registered Context Reference; reject caller authority fields. |
| Proposal or AI output treated as authorization | Require exact Candidate, Proposal, deterministic Validation, Human Authorization, and registration linkage. |
| Root-wide read from `source_locator` | Treat the locator as identity/root anchor only; authorize exact ordered `source_entry_points`. |
| Wildcard or implicit client access | Require explicit clients; preserve `allowed_clients=[]` as deny-all; do not infer access from model or product identity. |
| Stale data, moved Source, or unavailable provider observation | Treat these as conditions, obtain current authoritative evidence where possible, and fail closed; a moved or mismatched authorized locator is handled through a canonical state such as `stale_locator`. |
| `paused`, `source_unavailable`, `stale_locator`, `revoked`, or `archived` Reference | Deny active use before Source body access; do not invent an additional lifecycle state. |
| Provider metadata overriding Core semantics | Isolate provider metadata; Core authority, limits, freshness, and provenance remain deterministic. |
| Derived value replacing Source truth | Fix derived authority class, require authoritative support, and fail closed when the Authoritative Source is unavailable. |
| Malformed or oversized Source response | Enforce content type, encoding, structure, item/byte bounds, truncation semantics, and body-free errors. |
| Source content acting as instruction | Label Source Content as Untrusted Data and keep it outside trusted configuration and authority evaluation. |
| Credential or body leakage | Authenticate before resolver/body processing, use minimum disclosure, body-free audit, and secret-free reports. |

## 6. Fail-Closed Resolution Order

The required resolution order is:

```text
trusted object / owner-controlled runtime binding
        -> object and authorization linkage validation
        -> client authorization
        -> lifecycle and freshness validation
        -> exact Source scope and entry validation
        -> bounded stat / read
        -> provenance binding and minimum disclosure
```

Every step narrows the operation. A failure at an earlier authority or freshness step stops processing before a broader or deeper read. An implementation must not continue reading in order to produce a more detailed error.

Source unavailability is not permission to use a last-verified value, cache, or derived index as current truth. A paused Reference remains registered but cannot be used actively; only a legal lifecycle transition with any necessary revalidation can return it to `active`. Revoked and archived References cannot be reactivated by a caller or AI response. A moved or mismatched Source identity is an observation requiring revalidation and canonical fail-closed handling such as `stale_locator`, not silent auto-follow or a new `moved` lifecycle state.

## 7. Minimum Disclosure and Privacy

The baseline requires:

- minimum necessary Source disclosure;
- Source Content labeled and handled as Untrusted Data;
- body-free audit records;
- secret-free validation and execution reports;
- no credential or token echo;
- no Source body in validation errors;
- stable error codes and field locations without private values;
- bounded item, byte, frame, and response sizes;
- synthetic privacy sentinels for body, secret, and private-identity leakage;
- rebuild-from-zero fixtures rather than mechanically sanitized private JSON.

Audit evidence should retain operation type, decision, bounded counts, timestamps, and non-secret provenance linkage where permitted. It must not retain Source bodies, reusable credentials, raw authorization objects, or unnecessary private locators.

Credentials must remain in an appropriate protected credential store, be scoped to the minimum operation, and support revocation and cleanup. Technical access to a credential does not authorize logging, copying, or publishing it.

## 8. Source Adapter Security Requirements

A Source Adapter exposes only the declared read-only primitives `capabilities`, `list`, `stat`, and `read`. Discovery and registration orchestration remain outside the adapter contract.

The adapter must:

- use provider-native containment and identity checks;
- reject caller-supplied containment proof;
- preserve opaque locator semantics rather than letting Core guess provider paths;
- return stable success/error envelopes with limits and provenance;
- reject unsupported content or encoding explicitly;
- prevent provider metadata from changing authority, freshness, or disclosure limits;
- return body-free errors.

## 9. Derived-Layer Security Requirements

Derived metadata must declare `authority_class = derived` and `rebuildable = true`. Derived content cannot mint authority, widen Source scope, or support an authoritative final claim without current Source evidence.

If derived data is stale, inconsistent, or unsupported, it is ignored or rejected. If the derived provider is unavailable, resolution uses the direct authoritative path. If the Authoritative Source is unavailable, resolution fails closed.

Deleting and rebuilding an index must not destroy provenance requirements or silently change authority. Index availability is operational; provenance and Source authorization are security properties.

## 10. Gateway Security Requirements and Deferred Status

Gateway implementation is deferred. This document does not add a listener, server, MCP endpoint, HTTP endpoint, STDIO executable, plugin, client configuration, credential, or tool surface.

Any future localhost Gateway still requires:

- trusted local authentication; loopback alone is insufficient;
- authentication before body parsing and before resolver invocation;
- owner-controlled profile and runtime binding injection;
- a narrowly bounded tool surface;
- bounded request body, frame, item, byte, and response sizes;
- replay, expiry, revocation, and credential-cleanup controls appropriate to the transport;
- body-free audit and minimum-disclosure errors;
- tests against forged identity, wrong or missing credentials, scope injection, oversized requests, and cleanup failure.

MCP, HTTP, STDIO, plugin, and tool transports remain replaceable Gateway choices. None can define Core authority or justify a production-security claim without separate implementation and acceptance evidence.

## 11. Public Evidence and Fixture Boundary

Private prototype evidence may support these requirements, but it must not be copied into Public Core. Public fixtures and examples must be synthetic, from-zero, provider-neutral, and free of real paths, identifiers, hashes, credentials, runtime bindings, Source content, or client configuration.

Prototype validation does not establish public implementation completeness, universal AI compatibility, a second production authoritative Source, one-click setup, a production server, or product readiness.

## 12. Security Non-Goals for This Candidate

This documentation candidate does not:

- grant Source access or create an authorization;
- create or register a Registered Context Reference or trusted client identity;
- implement a Source Adapter, Gateway, provider, validator, or runtime;
- modify existing security policy or governance;
- define a production deployment or credential lifecycle implementation.

See [ADR-0001](ADR-0001-KNOWLEDGE-SOURCE-CLIENT-SEPARATION.md) and [Context Memory Bridge Architecture](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md) for the corresponding decision and layered flow.
