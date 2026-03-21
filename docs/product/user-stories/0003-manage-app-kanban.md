---
title: "0003: Manage an app's backlog on a Kanban board"
status: ready
last_updated: 2026-03-21
prd: docs/product/prd/0001-sovereign-agentic-foundry.md
---

## Story

As an operator,
I want to create and organise backlog items for my app on a Kanban board,
so that I can track feature requests and bug reports without switching to an external tool.

## Context

Each deployed app has a per-app Kanban board with five columns: Backlog, In Progress, Review, Done, Failed. The build pipeline creates and moves cards automatically as stages complete. The operator can add their own Backlog cards and move them as work progresses, providing a unified view of automated pipeline activity alongside manually managed work.

## Acceptance criteria

- [ ] Given I am on the Kanban view for an app, when the build pipeline is active, I see pipeline-stage cards in their current column (e.g. "Builder — generating files" in In Progress).
- [ ] Given I am on the Kanban view, when I click "Add card", I can create a card in the Backlog column with a title and optional description.
- [ ] Given I have a Backlog card, when I drag it to In Progress or any other column, the card position is persisted and visible on next reload.
- [ ] Given a card was created by the pipeline (locked), when I attempt to drag it, the drag is rejected and the card does not move.
- [ ] Given a pipeline stage completes successfully, when I reload the Kanban board, the pipeline card has moved to Done (or Failed if the stage failed).
- [ ] Given the Kanban board has more than 10 cards in a column, when I scroll within the column, I can access all cards.
- [ ] Error state: given the gateway is unreachable, when I drag a card, the card snaps back to its original position and an error message is shown.

## Out of scope

- Assigning cards to specific users.
- Card due dates or priority fields (beyond the basic title and description).
- Comments on cards (pipeline events are appended to the description, not a separate comment thread).
- Archiving or deleting individual cards.

## Notes

- Pipeline-created cards have `locked: true` in `board_cards`; the portal renders a lock icon and disables drag.
- Card positions use the `position` INTEGER column; lower is higher in the column.
- The portal uses dnd-kit from the MUI Minimal template Kanban section.
