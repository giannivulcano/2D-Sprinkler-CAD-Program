# Align Tool Design Specification

**Status:** Draft
**Date:** 2026-04-30
**Scope:** New tool + new constraint type — builds on existing constraint system
**Depends on:** [Snapping Engine](../../specs/snapping-engine.md), [Grid System](../../specs/grid-system.md), [Constraint System](../../../firepro3d/constraints.py)

---

## Table of Contents

1. [Goal](#1-goal)
2. [Motivation](#2-motivation)
3. [Interaction Model](#3-interaction-model)
4. [Reference & Edge Detection](#4-reference--edge-detection)
5. [AlignmentConstraint & Lock Behavior](#5-alignmentconstraint--lock-behavior)
6. [Tool Mode Implementation](#6-tool-mode-implementation)
7. [Gridline Spec Update](#7-gridline-spec-update)
8. [Performance](#8-performance)
9. [Testing Strategy](#9-testing-strategy)
10. [Acceptance Criteria](#10-acceptance-criteria)
11. [Verification Checklist](#11-verification-checklist)

---

## 1. Goal

Define an Align tool for FirePro3D that allows users to align any movable item to a reference edge in the scene, with optional persistent lock constraints. Modeled after Revit's Align tool (AL shortcut), adapted to FirePro3D's existing constraint system and snap engine.

## 2. Motivation

Aligning gridlines to underlay reference geometry (imported DXF/PDF drawings) currently requires manual measurement and perpendicular repositioning. This is tedious and error-prone — especially when setting up a project from architectural backgrounds where gridlines must match the structural grid shown on the underlay.

More generally, any movable item (walls, pipes, nodes, construction geometry) should be alignable to any visible reference edge in the scene. This is a fundamental CAD operation.

## 3. Interaction Model

### 3.1 Tool Activation

- **Ribbon:** Button in the Modify group (alongside Move/Rotate/Mirror/Copy)
- **Mode string:** `"align"`
- **Keyboard shortcut:** `AL`

### 3.2 Single-Item Workflow (2 Picks)

1. **Pick reference** — click any visible linear element in the scene. The snap engine identifies the nearest linear segment. A dashed highlight line confirms the pick.
2. **Pick target** — click any movable item. The target translates perpendicular to the reference until its nearest parallel edge aligns with the reference.
3. **Padlock prompt** — a padlock icon appears at the alignment point. Click to lock (creates `AlignmentConstraint`), or press Escape / start next alignment to dismiss without locking.

### 3.3 Multi-Select Workflow (3 Picks)

1. **Pre-select** a group of items using normal selection tools.
2. **Activate Align**, click the **reference** (stays put).
3. **Click the anchor** — must be an item within the selection. This item's nearest parallel edge aligns to the reference. All other selected items translate by the same delta (rigid group movement, preserving relative positions).
4. Same padlock behavior — each item in the group gets its own lock constraint with appropriate perpendicular offset from the reference.

### 3.4 Parallel Edge Resolution

The tool computes the perpendicular distance from the reference line to each edge of the target that is parallel (within 5° angular tolerance). The closest parallel edge is selected for alignment.

If no edge on the target is parallel to the reference, the tool shows a status bar warning ("No parallel edge found") and does nothing.

### 3.5 Point-Like Items

Nodes and sprinklers have no edges. The tool projects the item's position onto the reference line and translates the item perpendicular to the reference. Effectively treats the item's position as a zero-length edge parallel to anything.

## 4. Reference & Edge Detection

### 4.1 Linear Segment Extraction

The Align tool extracts linear segments from scene items to identify both reference edges and target edges.

| Item Type | Extractable Edges |
|---|---|
| GridlineItem | The gridline itself (p1→p2) |
| WallSegment | Two face edges (left/right offset from centerline) + centerline |
| Pipe | Centerline between node1 and node2 |
| ConstructionLine | The line itself |
| LineItem / PolylineItem | Each segment |
| DXF underlay paths | Each segment within `QGraphicsPathItem` children |
| PDF vector paths | Same as DXF — segment extraction from path items |
| CircleItem / ArcItem | Not supported (no parallel edge concept) — skipped silently |

### 4.2 Reference Pick Mechanism

On click, the tool uses the snap engine's spatial query (`scene.items(search_rect)`) to find nearby items, then extracts linear segments from each. The segment nearest to the click point (within snap tolerance) becomes the reference line.

A dashed highlight line is drawn along the full extent of the reference segment to confirm the pick.

### 4.3 Target Edge Selection

When the target is picked, the tool extracts all linear segments from the target item using the same table above. For items with multiple edges (e.g. walls with two face edges + centerline), all parallel candidates are evaluated and the nearest one to the reference wins.

### 4.4 Underlay Geometry Access

DXF underlay children are `QGraphicsPathItem` instances within a `QGraphicsItemGroup`. The tool walks the group's children, extracts path segments from each child item's `QPainterPath`, and maps them to scene coordinates. This is the same traversal pattern used by the snap engine's phase-1 scan.

PDF vector underlays use the same approach — geometry is stored as `QGraphicsPathItem` children.

PDF raster underlays have no extractable geometry and are silently skipped.

## 5. AlignmentConstraint & Lock Behavior

### 5.1 New Constraint Class

`AlignmentConstraint(Constraint)` added to `constraints.py` as a third concrete implementation alongside `ConcentricConstraint` and `DimensionalConstraint`.

### 5.2 Stored State

| Field | Type | Purpose |
|---|---|---|
| `reference_item` | object \| None | The item that stays put. `None` when reference is underlay geometry (fixed line mode). |
| `reference_line` | tuple[QPointF, QPointF] \| None | Fixed reference line in scene coordinates. Used when `reference_item` is `None` (underlay reference). `None` when reference is a scene item. |
| `target_item` | object | The item that moves |
| `reference_edge_index` | int | Which edge on the reference (e.g. wall left face = 0, right face = 1, centerline = 2). Ignored in fixed-line mode. |
| `target_edge_index` | int | Which edge on the target |
| `perpendicular_offset` | float | Signed perpendicular distance to maintain (normally 0.0 after align) |

### 5.3 solve() Behavior

When the reference moves:
1. Recompute the reference edge's current position using `_extract_edges(reference_item)[reference_edge_index]`.
2. Compute where the target edge should be: reference edge position + `perpendicular_offset` in the perpendicular direction.
3. Translate the target item so its edge is at the computed position.

Follows the same anchor/mobile pattern as `DimensionalConstraint` — if the target was the `moved_item`, the reference stays and the target snaps back to its constrained position.

### 5.4 Padlock Visual

- Small padlock icon (SVG, `QGraphicsPixmapItem` or painted directly) positioned at the midpoint of the aligned edge overlap.
- Uses `ItemIgnoresTransformations` for constant screen size (same pattern as `GridBubble`).
- **Click to unlock:** removes the `AlignmentConstraint` from `self._constraints` and deletes the padlock icon.
- Padlock color: matches the constraint system's visual language (distinct from snap markers and grid bubbles).

### 5.5 Multi-Select Lock Behavior

Each item in a multi-select alignment gets its own `AlignmentConstraint` with:
- Same `reference_item` and `reference_edge_index`
- Individual `target_edge_index` for that item
- `perpendicular_offset` calculated as (that item's edge distance from reference) at lock time

This means each locked item independently maintains its offset when the reference moves. The group relationship is preserved through individual constraints — no group object needed.

### 5.6 Edge Cases

- **Reference deleted:** `_solve_constraints` skips failing constraints. The cleanup in `set_mode()` (model_space.py line 616) removes constraints involving deleted items. Padlock icon is also removed.
- **Target deleted:** Same cleanup path — constraint and padlock removed.
- **Reference is underlay geometry:** Underlays are static reference geometry (not user-movable in the scene). Underlay children (`QGraphicsPathItem` instances) lack stable identity across save/load and refresh-from-disk — they are not in the scene's geometry list and have no persistent ID. When the reference is an underlay sub-item, the `AlignmentConstraint` stores the reference edge as a **fixed line** (two scene-coordinate points) rather than an item reference + edge index. The `solve()` method uses these stored coordinates directly. This means the constraint pins the target to an absolute position — if the underlay is moved or refreshed, the constraint does not follow. This is acceptable because underlays are typically locked/static reference geometry. The lock still prevents the target from being accidentally bumped out of alignment.
- **Circular constraints:** The existing solver's stall detection (3 consecutive iterations with no progress) handles circular constraint chains gracefully.

### 5.7 Serialization

Same `to_dict()` / `from_dict()` pattern as existing constraints:

```json
{
    "constraint_type": "alignment",
    "reference_item": <item_id>,
    "target_item": <item_id>,
    "reference_edge_index": 0,
    "target_edge_index": 0,
    "perpendicular_offset": 0.0,
    "enabled": true
}
```

The `Constraint.from_dict()` factory in `constraints.py` gains a new branch for `"alignment"` type.

## 6. Tool Mode Implementation

### 6.1 State Machine

```
IDLE
  → pick_reference (click 1: store reference line, draw highlight)
    → pick_target (click 2, no selection: move item, show padlock prompt)
    → pick_anchor (click 2, selection active: must be in selection, move group, show padlock prompt)
      → IDLE (padlock clicked or dismissed)
```

### 6.2 Handler Methods

Added to `SceneToolsMixin` in `scene_tools.py`:

**`_press_align(event, pos, ...)`** — main dispatch:
- No reference stored yet: extract nearest linear segment from click position. Store as `_align_reference` (line segment + source item + edge index). Draw dashed highlight. Update status: "Click item to align (or click anchor in selection)".
- Reference stored, no selection active: clicked item is the target. Call `_execute_align()`.
- Reference stored, selection active: clicked item must be in the selection — it's the anchor. Call `_execute_align()` with group.

**`_move_align(event)`** — live preview:
- Before reference pick: highlight nearest linear segment under cursor (preview of what would be picked as reference).
- After reference pick: if cursor is over a movable item, show a ghost preview of where it would move, with a dimension label showing the perpendicular distance.

**`_execute_align(reference_line, target_item, target_edge, group=None)`**:
1. Compute perpendicular translation vector.
2. If group: compute anchor's translation delta, apply same delta to all group members.
3. Call `self.push_undo_state()`.
4. Apply translation to target (or group).
5. Call `_solve_constraints()` to resolve any existing constraints affected by the move.
6. Show padlock icon at alignment point.

### 6.3 Mode Dispatch Wiring

```python
_PRESS_DISPATCH = {
    # ...
    "align": "_press_align",
}
```

Mouse move handler in `mouseMoveEvent` gains an `"align"` branch calling `_move_align()`.

### 6.4 Escape Behavior

- First Escape: clears `_align_reference`, removes highlight line, returns to reference-pick state.
- Second Escape (no reference stored): exits tool, calls `set_mode("select")`.

### 6.5 Undo

Single undo state pushed before the move. Undo reverts all items to pre-align positions. If a lock constraint was created, the undo snapshot does not include it (constraint was added after the snapshot), so undo also effectively removes the constraint.

## 7. Gridline Spec Update

The grid system spec (`docs/specs/grid-system.md`) requires a small addition:

### 7.1 Alignment Constraint Participation

Gridlines can be both **reference** and **target** for the Align tool:

- **As reference:** The gridline's single line segment (p1→p2) serves as the reference edge. Other items align to it.
- **As target:** The Align tool calls `set_perpendicular_position()` to move the gridline. This respects the existing `_locked` flag — locked gridlines cannot be aligned (status bar warning).
- **Edge extraction:** Trivial — a gridline exposes exactly one linear segment (p1→p2).
- **Lock constraint:** When locked via Align, an `AlignmentConstraint` is stored referencing the gridline. The padlock icon appears at the gridline's midpoint. Moving the reference triggers `set_perpendicular_position()` via the constraint solver.

No structural changes to `GridlineItem` are needed. The existing `move_perpendicular()` and `set_perpendicular_position()` APIs are sufficient.

## 8. Performance

### 8.1 Edge Extraction Budget

Edge extraction runs twice per alignment (once for reference pick, once for target pick). Each extraction walks the item's geometry — trivial for gridlines/walls/pipes (1-3 segments), potentially heavier for DXF underlay groups with many children.

**Mitigation:** The snap engine's spatial query already filters to items near the click point. Edge extraction only runs on items within the search rect, not all scene items.

### 8.2 Constraint Solver Impact

Each `AlignmentConstraint.solve()` is O(1) — extract one edge, compute perpendicular translation, apply. The iterative solver (max 20 iterations) handles interaction with other constraints. No performance concern unless hundreds of alignment constraints accumulate (unlikely in practice).

### 8.3 Underlay Segment Extraction

DXF underlays may contain thousands of path segments. The tool must not extract all segments from the entire underlay group — only from the specific `QGraphicsPathItem` child nearest to the click point.

**Approach:** Use `scene.items(search_rect)` which returns individual child items (not just the top-level group), then extract segments only from the matched child item.

## 9. Testing Strategy

### 9.1 AlignmentConstraint Unit Tests

| Test | Assertion |
|---|---|
| Solve with reference moved | Target translates to maintain perpendicular offset |
| Solve with target moved | Target snaps back to constrained position |
| Solve with zero offset | Target edge aligns exactly with reference edge |
| Solve with non-zero offset | Target edge maintains specified perpendicular distance |
| Serialization round-trip | `to_dict()` → `from_dict()` produces equivalent constraint |
| Involves check | `involves(reference)` and `involves(target)` both return True |
| Disabled constraint | `solve()` returns True without moving anything |

### 9.2 Edge Extraction Tests

| Test | Assertion |
|---|---|
| GridlineItem | Returns 1 segment (p1→p2) |
| WallSegment | Returns 3 segments (left face, right face, centerline) |
| Pipe | Returns 1 segment (node1→node2 centerline) |
| LineItem | Returns 1 segment |
| PolylineItem (3 vertices) | Returns 2 segments |
| CircleItem | Returns empty list |
| Point-like item (Node) | Falls through to point projection path |

### 9.3 Parallel Detection Tests

| Test | Assertion |
|---|---|
| Exactly parallel (0°) | Detected as parallel |
| Within tolerance (4°) | Detected as parallel |
| Outside tolerance (6°) | Not detected |
| Perpendicular (90°) | Not detected |
| Antiparallel (180°) | Detected as parallel |

### 9.4 Align Tool Integration Tests

| Test | Assertion |
|---|---|
| Align gridline to underlay edge | Gridline moves perpendicular to match underlay edge position |
| Align wall to gridline | Wall translates so nearest face aligns with gridline |
| Align node to gridline | Node projects perpendicular onto gridline |
| Multi-select rigid align | Group translates together, relative offsets preserved |
| Lock and move reference | Target follows reference via constraint solver |
| Unlock via padlock click | Constraint removed, target stays in place |
| Align locked gridline | Status bar warning, no movement |
| No parallel edge | Status bar warning, no movement |
| Undo after align | All items return to pre-align positions |
| Reference deleted after lock | Constraint cleaned up, padlock removed |

## 10. Acceptance Criteria

1. User can activate Align tool via ribbon button or `AL` shortcut.
2. First click selects reference edge with dashed highlight confirmation.
3. Second click on a movable item translates it perpendicular until its nearest parallel edge aligns with the reference.
4. Point-like items (nodes, sprinklers) project perpendicular onto the reference line.
5. Multi-select alignment: user picks anchor in selection, group moves rigidly.
6. Padlock icon appears after alignment; clicking it creates a persistent `AlignmentConstraint`.
7. Moving the reference item triggers the constraint solver, maintaining the aligned relationship.
8. Clicking the padlock icon removes the constraint (unlock).
9. Locked gridlines cannot be aligned (status bar warning).
10. Items with no parallel edge to the reference produce a status bar warning with no movement.
11. Live preview shows ghost position and perpendicular distance during target hover.
12. Escape clears reference pick; double-escape exits tool.
13. Undo reverts alignment and any created constraint in a single step.
14. `AlignmentConstraint` serializes to/from project files via the existing constraint system.

## 11. Verification Checklist

- [ ] Ribbon button in Modify group activates `"align"` mode
- [ ] `AL` keyboard shortcut activates align mode
- [ ] Reference pick highlights nearest linear segment with dashed line
- [ ] Status bar shows appropriate prompts at each stage
- [ ] Single-item alignment: target moves perpendicular to reference
- [ ] Nearest parallel edge correctly selected (within 5° tolerance)
- [ ] Non-parallel edge produces warning, no movement
- [ ] Point-like items (nodes/sprinklers) project perpendicular onto reference
- [ ] Multi-select: anchor pick restricted to selection members
- [ ] Multi-select: group translates rigidly, relative offsets preserved
- [ ] Padlock icon appears at alignment midpoint after alignment
- [ ] Padlock click creates `AlignmentConstraint` in `self._constraints`
- [ ] Padlock click again (unlock) removes constraint and icon
- [ ] Padlock uses `ItemIgnoresTransformations` (constant screen size)
- [ ] Moving locked reference triggers solver, target follows
- [ ] Locked gridlines rejected with status bar warning
- [ ] Ghost preview on hover shows target destination and distance label
- [ ] Escape clears reference, second Escape exits tool
- [ ] Undo reverts all moved items and removes created constraint
- [ ] `AlignmentConstraint.to_dict()` / `from_dict()` round-trips correctly
- [ ] Deleted reference/target cleans up constraint and padlock
- [ ] DXF underlay edges work as references (spatial-filtered, not full group scan)
- [ ] PDF vector underlay edges work as references
- [ ] PDF raster underlays silently skipped (no geometry)
- [ ] Grid system spec updated with alignment constraint participation section
- [ ] Constraint spec backlog item updated to P2 with AlignmentConstraint mention
