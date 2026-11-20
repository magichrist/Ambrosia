# ADR 0002 — Context determines applicability; phases organize views

- Status: Accepted
- Date: 2026-11-20

## Context

A pentest-style fixed phase list would hard-code a lifecycle the product
explicitly rejects. Operator journeys are dynamic and non-linear.

## Decision

The context engine and availability matcher determine which actions are
applicable. `PhaseDefinition` is user-owned metadata: it groups actions and
presets for navigation, may carry visibility predicates, and cannot grant
permission, mutate context, or force an order.

## Consequences

- Removing all phases does not change what can execute.
- A phase-referenced action remains discoverable from global search.
- UI navigation cannot be used as an authorization mechanism.
