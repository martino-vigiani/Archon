# Contract Template: Component

Use this template when defining a reusable UI component that needs coordination between design (T1) and functionality (T2).

---

## When to Use

- T1 creates a UI component that T2 needs to power with data
- A component needs specific bindings or callbacks
- Multiple screens share a component with different data sources

## Template

```markdown
# Contract: [ComponentName]

**ID:** `contract_[name]_[timestamp]`
**Type:** component
**Status:** Negotiating
**Proposer:** T[N]
**Created:** [ISO timestamp]
**Updated:** [ISO timestamp]
**Tags:** ui, [platform]

---

## Negotiation History

### Proposal (T[N] @ HH:MM)

[Describe the component and its requirements]

**Component:** `[ComponentName]`
**Purpose:** [What this component displays/does]

**Props/Bindings:**
```swift
struct [ComponentName]: View {
    // Required
    let title: String
    let data: [DataType]

    // Optional
    var onAction: (() -> Void)? = nil
    var isLoading: Bool = false
}
```

**Appearance:**
- [Layout description]
- [Animation requirements]
- [Accessibility requirements]

**States:**
- Loading: [Description]
- Empty: [Description]
- Error: [Description]
- Normal: [Description]

### Response (T[N] @ HH:MM)

[Data availability, suggested modifications]

### Implementation (T[N] @ HH:MM)

Implemented in `[file/path]`.

**Quality:** 80%
**File:** `[path/to/Component.swift]`
```

## Example: Activity Feed Component

```markdown
# Contract: ActivityFeed

**ID:** `contract_activityfeed_20260202120000`
**Type:** component
**Status:** Negotiating
**Proposer:** T1
**Created:** 2026-02-02T12:00:00
**Updated:** 2026-02-02T12:00:00
**Tags:** ui, swiftui, feed

---

## Negotiation History

### Proposal (T1 @ 12:00)

T1 is building the home screen and needs an ActivityFeed component that
displays recent user activity. T2 needs to provide the data source.

**Component Interface:**

```swift
struct ActivityFeed: View {
    // Data binding
    @Binding var activities: [Activity]

    // State
    var isLoading: Bool = false
    var hasMore: Bool = true

    // Callbacks
    var onRefresh: () async -> Void
    var onLoadMore: () async -> Void
    var onActivityTap: (Activity) -> Void
}

struct Activity: Identifiable {
    let id: UUID
    let type: ActivityType
    let title: String
    let timestamp: Date
    let iconName: String
}

enum ActivityType {
    case achievement
    case milestone
    case social
    case system
}
```

**Visual Requirements:**
- Infinite scroll with pull-to-refresh
- Activity icons with colored backgrounds per type
- Relative timestamps ("2 hours ago")
- Skeleton loading states
- Empty state with illustration

**Accessibility:**
- VoiceOver support for all items
- Dynamic Type scaling
- Reduce Motion support

### Response (T2 @ 12:15)

I can provide this data. Suggest adding `isRead: Bool` to Activity for
visual differentiation of new vs seen items. Also recommend pagination
via cursor rather than offset for better performance.

**Modified interface:**

```swift
struct Activity: Identifiable {
    let id: UUID
    let type: ActivityType
    let title: String
    let timestamp: Date
    let iconName: String
    let isRead: Bool  // NEW
}

// Pagination
struct ActivityPage {
    let activities: [Activity]
    let nextCursor: String?
    let hasMore: Bool
}
```
```

## Tips

1. **Define all states** - Components have loading, empty, error, and success states
2. **Include callbacks** - How does the UI communicate back to the data layer?
3. **Specify accessibility** - This should be part of the contract, not an afterthought
4. **Show visual requirements** - Layout, animations, theming
5. **Consider reusability** - Can this component be used in multiple contexts?
