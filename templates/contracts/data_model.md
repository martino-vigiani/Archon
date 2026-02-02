# Contract Template: Data Model

Use this template when defining a persistent data model that needs to be shared across terminals for database, caching, or state management.

---

## When to Use

- T2 designs a database schema that T1 will display
- SwiftData/CoreData models need UI integration
- State management shapes need agreement

## Template

```markdown
# Contract: [ModelName]

**ID:** `contract_[name]_[timestamp]`
**Type:** data_model
**Status:** Negotiating
**Proposer:** T[N]
**Created:** [ISO timestamp]
**Updated:** [ISO timestamp]
**Tags:** data, [storage-type]

---

## Negotiation History

### Proposal (T[N] @ HH:MM)

[Describe the data model and its purpose]

**Model:** `[ModelName]`
**Storage:** [SwiftData/CoreData/UserDefaults/etc.]
**Purpose:** [What this model represents]

```swift
@Model
class [ModelName] {
    // Identity
    @Attribute(.unique) var id: UUID

    // Fields
    var field1: Type1
    var field2: Type2

    // Relationships
    @Relationship var related: [RelatedModel]

    // Timestamps
    var createdAt: Date
    var updatedAt: Date
}
```

**Constraints:**
- [Uniqueness constraints]
- [Required vs optional fields]
- [Validation rules]

**Relationships:**
- [Model] has-many [OtherModel]
- [Model] belongs-to [ParentModel]

**Indexes:**
- [Fields to index for query performance]

### Response (T[N] @ HH:MM)

[Feedback on schema design, UI considerations]

### Implementation (T[N] @ HH:MM)

Implemented in `[file/path]`.

**Quality:** 80%
**File:** `[path/to/Model.swift]`
```

## Example: Habit Model

```markdown
# Contract: Habit

**ID:** `contract_habit_20260202130000`
**Type:** data_model
**Status:** Negotiating
**Proposer:** T2
**Created:** 2026-02-02T13:00:00
**Updated:** 2026-02-02T13:00:00
**Tags:** data, swiftdata, core

---

## Negotiation History

### Proposal (T2 @ 13:00)

T2 proposes the core Habit model for the habit tracking app. This is the
central entity that T1's UI will display and allow users to manage.

**SwiftData Model:**

```swift
@Model
class Habit {
    // Identity
    @Attribute(.unique) var id: UUID

    // Core fields
    var name: String
    var description: String?
    var emoji: String
    var color: String  // Hex color code

    // Schedule
    var frequency: HabitFrequency
    var targetDays: [Int]  // 0=Sunday, 6=Saturday
    var reminderTime: Date?

    // Tracking
    var currentStreak: Int
    var longestStreak: Int
    var totalCompletions: Int

    // Relationships
    @Relationship(deleteRule: .cascade)
    var completions: [HabitCompletion]

    // Timestamps
    var createdAt: Date
    var updatedAt: Date
    var archivedAt: Date?

    // Computed
    var isArchived: Bool { archivedAt != nil }
    var completionRate: Double { /* calculation */ }
}

enum HabitFrequency: String, Codable {
    case daily
    case weekly
    case custom
}

@Model
class HabitCompletion {
    @Attribute(.unique) var id: UUID
    var habit: Habit?
    var completedAt: Date
    var note: String?
}
```

**Constraints:**
- `id` must be unique
- `name` cannot be empty, max 100 chars
- `emoji` must be a single emoji character
- `color` must be valid hex (#RRGGBB)
- `targetDays` only valid when frequency is `.custom`

**Indexes:**
- `createdAt` for sorting by creation
- `archivedAt` for filtering active habits
- `HabitCompletion.completedAt` for date queries

**Migration Notes:**
- v1: Initial schema
- v2 (planned): Add `category: HabitCategory` relationship

### Response (T1 @ 13:20)

This looks good for UI purposes. I'll need a few computed properties for display:

1. `displayName: String` - name with emoji prefix
2. `streakText: String` - "5 day streak!" or "Start your streak"
3. `nextReminderText: String?` - formatted reminder time

Can T2 add these as computed properties on the model, or should T1
create a separate view model wrapper?

### Resolution (T4 mediated @ 13:30)

**AGREED:** T2 will add computed display properties to the model since
they're pure transformations. T1 will use a thin view model for any
UI-specific state (loading, selection, etc.).

```swift
// Added to Habit model
var displayName: String {
    "\(emoji) \(name)"
}

var streakText: String {
    currentStreak > 0
        ? "\(currentStreak) day streak!"
        : "Start your streak"
}

var nextReminderText: String? {
    guard let time = reminderTime else { return nil }
    return time.formatted(date: .omitted, time: .shortened)
}
```
```

## Tips

1. **Define relationships clearly** - One-to-many, many-to-many, ownership
2. **Specify deletion behavior** - Cascade, nullify, deny?
3. **Include migrations** - How will this schema evolve?
4. **Consider query patterns** - What indexes are needed?
5. **Add computed properties** - Pure transformations belong on the model
6. **Document constraints** - Validation rules, uniqueness, required fields
