---
type: architecture-decision-record
status: proposed
scope: public-candidate-documentation
implementation_status: not-implemented
governance_effect: none
authorization_effect: none
activation_effect: none
visibility: public
---

# ADR-0001: Knowledge Source and AI Client Separation

## Status

Proposed documentation candidate. This record defines architecture boundaries only. It does not claim that the described contracts, validators, adapters, gateways, installers, or production services are implemented in XINGSHU Public Core.

## Context

Long-lived user knowledge normally already has an Authoritative Source of Truth: a repository, document system, knowledge base, or another owner-selected source. Copying the whole source into XINGSHU would create duplicate state, weaken provenance, increase privacy exposure, and make replacement or rollback harder.

AI clients and protocols also change more quickly than the authority rules that protect user context. If Core semantics depend on a particular provider, client, or transport, replacing that component can change authorization behavior or strand user assets.

XINGSHU therefore needs a Thin Core that preserves stable identity, authorization, freshness, provenance, routing, and deterministic validation semantics while leaving source content in its Authoritative Source of Truth.

## Decision

### 1. Attach, do not migrate

An existing Source is attached by reference; it is not copied into XINGSHU by default. The Source remains authoritative, and XINGSHU stores only the minimum metadata required to resolve approved context safely.

A lightweight Registered Context Reference identifies an approved relationship among a Source, exact retrieval entries, permitted clients, freshness requirements, and provenance evidence. A Candidate, Proposal, or Validation result is not approved Reference authority. A Registered Context Reference is not a content mirror, cache authorization, or permission to read an entire Source root.

### 2. Keep four layers separate

XINGSHU separates four responsibilities:

1. **Core** defines source-neutral identity, authorization, reference, lifecycle, freshness, provenance, routing, and deterministic validation semantics.
2. **Gateway** maps a protocol or tool surface to Core operations and injects trusted, owner-controlled client context. A Gateway does not redefine authority.
3. **Provider** implements Source Adapter operations or optional derived trigger/index behavior. Provider output is data, not authority.
4. **Personal Instance** owns all real identities, bindings, Source locators, approved entry points, Human Authorization evidence, Registered Context References, credentials, and runtime state.

Public Core may define portable shapes and invariants for these objects, but it must not store Personal Instance values.

### 3. Separate Source Adapter from Client/Gateway

A Source Adapter exposes bounded, read-only Source operations. A Client/Protocol Gateway exposes a bounded AI-facing operation and supplies trusted server-side identity and binding context. These are different interfaces and different trust boundaries.

The Source Adapter does not trust caller-supplied authority. The Gateway does not become a Source of Truth. Protocol, provider, and AI client names do not define Core authority semantics.

MCP is Gateway, not Core. The same rule applies to HTTP, STDIO, plugin, tool, or future transports: transport choice must not create, widen, or bypass authority.

### 4. Keep AI intelligence separate from authority

AI may discover context, interpret semantics, and prepare a Proposal. AI output remains an untrusted suggestion until deterministic validation and explicit Human Authorization are complete.

`AI Intelligence != Authority`

Neither an AI response nor a caller request may self-declare principal, scope, Source authority, final entry points, allowed clients, containment proof, or authorization. The Personal Instance and owner-controlled runtime binding remain the authority boundary.

### 5. Treat derived data as replaceable assistance

An optional derived trigger or index may help identify where authoritative verification should begin. It is rebuildable and non-authoritative. It cannot mint authority, override a fresher authoritative observation, or become current truth when the Authoritative Source is unavailable.

`Index is disposable; provenance is not.`

A named product such as OpenWiki may be discussed only as an external, optional, version-specific validated example. It is not a dependency, official component, mandatory layer, bundled integration, or replacement for the owner-selected Source.

## Rejected Alternatives

### Copy the whole Source into XINGSHU

Rejected because it creates a competing Source of Truth, increases privacy exposure, and makes freshness and provenance ambiguous.

### Make MCP the only Core interface

Rejected because a transport-specific Core couples authority semantics to one protocol. MCP belongs in a replaceable Gateway.

### Accept caller-defined authority

Rejected because a caller, model, prompt, or tool argument cannot be trusted to choose its own principal, scope, Source authority, allowed clients, or containment result.

### Encode product-specific Core constants

Rejected because product names must not become schema enums, Core constants, lifecycle states, or authority semantics. Products belong behind replaceable Gateway or Provider boundaries.

### Require OpenWiki or another derived provider

Rejected because derived capability is optional and non-authoritative. Direct authoritative resolution must remain available when the derived provider is absent, and resolution must fail closed when the Authoritative Source itself is unavailable.

## Consequences

- Source content remains under its existing owner-selected authority and lifecycle.
- AI clients, transports, and providers can be replaced without changing Core authorization semantics.
- Registration requires a distinct Candidate, Proposal, deterministic Validation, Human Authorization, and Registered Context Reference chain.
- Freshness and provenance must be checked before use; cached or derived content cannot silently replace current authoritative evidence.
- Public examples and future fixtures must be rebuilt from zero with synthetic values, not mechanically sanitized from private runtime artifacts.

## Claim Boundary

Private prototype validation can justify these public architecture requirements. It does not mean the Public Core implementation is complete, a product is ready, all AI clients are compatible, a second production authoritative Source has been validated, or a production server and installer exist.

The detailed flow is defined in [Context Memory Bridge Architecture](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md). Security requirements are defined in [Context Bridge Security Model](CONTEXT_BRIDGE_SECURITY_MODEL.md).
