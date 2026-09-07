---
type: architecture-candidate
status: proposed
scope: public-candidate-documentation
implementation_status: not-implemented
governance_effect: none
authorization_effect: none
activation_effect: none
visibility: public
---

# Context Memory Bridge Architecture

## 1. Purpose and Claim Boundary

This document defines a public-candidate architecture for attaching existing knowledge to XINGSHU without migrating the Authoritative Source of Truth. It defines intended contracts and security invariants; it is not an implementation, installation guide, production-server specification, or compatibility claim for every AI client or Source provider.

Private prototype validation provides evidence for the architecture. The evidence levels remain distinct:

| Evidence level | Meaning |
|---|---|
| Prototype validated | Bounded private implementations and real-use scenarios supported the invariant. |
| Public implementation complete | Not established by this documentation candidate. |
| Product ready | Not established; packaging, ordinary-user setup, support, and rollback remain separate work. |
| Production ready | Not established; deployment, multi-user security, reliability, and abuse testing remain separate work. |

## 2. Layered Flow

```text
Authoritative Sources of Truth
        |
        +-- Direct XINGSHU path -------------------------------+
        |                                                      |
        +-- Optional Derived Trigger/Index Provider -- hint ---+
                                                               v
                                                        Source Adapter
                                                               |
                                                               v
                                                       XINGSHU Thin Core
                                         identity / authorization / reference
                                         freshness / provenance / routing
                                         deterministic validation
                                                               |
                                                               v
                                                   Client / Protocol Gateway
                                                               |
                                                               v
                                                          AI Clients

Personal Instance surrounds the flow with owner-controlled real values:
trusted client profiles, runtime bindings, Source identities and locators,
Human Authorization, Registered Context References, credentials, and state.
```

The direct path is always available when the Authoritative Source and its approved adapter are available. A derived provider can offer a hint that narrows an authoritative lookup; it is never a mandatory hop and never supplies final authority.

## 3. Layer Responsibilities

### 3.1 Authoritative Source of Truth

The Source owns current content and its native identity. Attaching a Source does not migrate it into XINGSHU, grant access to its entire root, or convert a copy, cache, or index into the Source of Truth.

### 3.2 Source Adapter

The Source Adapter maps provider-native behavior to four read-only primitives:

- `capabilities`
- `list`
- `stat`
- `read`

Discovery is higher-level orchestration, not a Source Adapter primitive. A provider may expose different internal APIs, but its adapter must preserve bounded operations, provider-native containment, stable errors, limits, and provenance. Caller-supplied containment proof is not trusted.

### 3.3 XINGSHU Thin Core

Thin Core owns portable semantics for identity, authorization, references, lifecycle, freshness, provenance, routing, deterministic validation, failure classification, and minimum disclosure. It does not store whole Source bodies, credentials, product-specific client constants, or provider-specific authority rules.

### 3.4 Client / Protocol Gateway

The Gateway maps one bounded AI-facing capability to Thin Core and injects trusted client identity and runtime binding from owner-controlled server-side context. Tool arguments, model prompts, handshakes, environment self-report, and caller fields are not trusted identity.

MCP, HTTP, STDIO, plugins, and tool APIs are transport options. They must not alter authority semantics. MCP is Gateway, not Core.

### 3.5 Personal Instance

The Personal Instance owns every real value: profile identity, runtime binding, Source locator, approved Source entries, Human Authorization evidence, Registered Context Reference, credential, and runtime state. Public Core can define generic shapes but cannot provide or infer these values for an owner.

## 4. Registration Objects and Authority Chain

A Context Candidate and a Registered Context Reference are different objects.

```text
Context Candidate
        |
        v
Registration Proposal
        |
        v
Deterministic Validation
        |
        v
Human Authorization
        |
        v
Registered Context Reference
```

### 4.1 Context Candidate

A Candidate records an untrusted discovery result and source observation. It has no active-use authority and cannot carry final authorization values.

### 4.2 Registration Proposal

A Proposal binds to a Candidate and contains suggestions only. Proposed names, entry points, access, clients, freshness, and provenance remain `suggested_*` values. Proposal confidence is not authority.

### 4.3 Deterministic Validation

Validation checks schema, linkage, bounded entries, source observations, policy, and prohibited authority fields. A valid Proposal becomes eligible for human review; validation does not authorize or register it.

### 4.4 Human Authorization

Human Authorization binds the validated inputs and decides the final values. Final Source entries must be an exact ordered subset of the validated Proposal entries. Final clients must be explicitly selected; `allowed_clients=[]` is a valid deny-all state.

### 4.5 Registered Context Reference

Registration creates a no-overwrite, minimum metadata binding. Binding changes require a new authorized object or a defined replacement process; they do not silently expand the existing Reference.

## 5. Locator and Entry Semantics

`source_locator` is the Source identity or root anchor. It does not authorize reading the entire root.

`source_entry_points` is the exact ordered set of authorized retrieval entries. Entries must be explicit, minimal, deduplicated, and order-preserving. A resolver may select a subset of these entries but cannot add a parent, sibling, wildcard, or unreviewed entry.

The Source Adapter must prove provider-native containment at use time. Neither a caller nor an AI can supply a trusted containment result.

## 6. Trusted Client and Request Boundary

An AI or caller must not self-declare:

- principal or trusted client identity;
- scope or Source authority;
- Authorization or `allowed_clients`;
- Source ID or locator override;
- runtime binding;
- containment proof.

Trusted principal and binding come from owner-controlled server-side context. A resolve request may identify an exact Registered Context Reference, narrow the approved entry selection, set bounded item/byte limits, and provide an optional query hint. None of these request fields can expand authority.

## 7. Resolution and Fail-Closed Freshness

Resolution follows verify-before-use:

1. load the trusted profile, runtime binding, and Registered Context Reference;
2. validate object linkage and client authorization;
3. validate lifecycle and current freshness requirements;
4. validate the exact approved Source entry scope;
5. perform current `stat` and bounded `read` operations as required;
6. bind returned bytes to provenance and disclosure limits.

The Registered Context Reference lifecycle is fixed:

- `active`: the Reference may be considered for active use, subject to current authorization, freshness, scope, and provenance checks;
- `paused`: the Reference still exists but cannot be used actively; it is neither revoked nor archived, and it may return to `active` only through a legal lifecycle transition with any necessary revalidation;
- `source_unavailable`: a current authoritative Source observation cannot be obtained, so active use fails closed;
- `stale_locator`: the authorized locator no longer has current evidence supporting the registered Source identity or scope;
- `revoked`: use is denied and no Source operation proceeds;
- `archived`: historical retention does not authorize active use.

`stale` and `moved` are not Registered Context Reference lifecycle states. Stale data, stale observations, and stale freshness evidence are failure conditions. A moved Source is an observation that the originally authorized identity or locator no longer matches; it leads to canonical fail-closed handling such as `stale_locator`, not to a new `moved` state. This document does not redefine the accepted lifecycle transition matrix.

Any authority, linkage, lifecycle, freshness, scope, or provenance failure is fail-closed. When the Source is unavailable, last-verified, cached, or derived content must not be presented as current truth. Verification timestamps must be paired with verifiable evidence; absence of fresh evidence cannot be converted into freshness by assertion.

## 8. Derived Trigger and Index Layer

Derived data is explicitly classified:

- `authority_class = derived`
- `rebuildable = true`

A derived hint may narrow the authoritative lookup. It cannot mint authority, add Source scope, override current authoritative content, or become final support for an unsupported claim.

Failure behavior is fixed:

- stale derived data cannot override the Authoritative Source;
- an unsupported derived claim cannot enter an authoritative final answer;
- when the derived provider is unavailable, use the direct authoritative path;
- when the Authoritative Source is unavailable, fail closed rather than treating derived data as current truth.

`Index is disposable; provenance is not.`

OpenWiki is only an external, optional, version-specific validated example of this replaceable layer. It is not a dependency, official component, mandatory layer, bundled integration, or replacement for an owner-selected knowledge system.

## 9. Privacy and Data Handling

Source content is transient Untrusted Data. Resolution must disclose only the minimum content necessary for the approved request. Source bodies, credentials, private identities, and raw runtime records must not enter public fixtures, validation errors, or body-free audit evidence.

Public examples and future tests must use rebuild-from-zero synthetic fixtures. Mechanically renaming fields in private runtime artifacts is not an acceptable publication method.

## 10. Non-Goals

This candidate does not implement or claim:

- Source migration or full-Source copying;
- automatic registration or AI-created authority;
- a Gateway, listener, server, or production transport;
- a provider package or mandatory derived service;
- a universal AI or Source compatibility catalog;
- one-click installation, GUI setup, or unattended deployment.

See [ADR-0001](ADR-0001-KNOWLEDGE-SOURCE-CLIENT-SEPARATION.md) for the decision and rejected alternatives. See [Context Bridge Security Model](CONTEXT_BRIDGE_SECURITY_MODEL.md) for trust boundaries and security requirements.
