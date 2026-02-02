# Contract Template: Interface

Use this template when defining a data structure or protocol that multiple terminals need to agree upon.

---

## When to Use

- T1 needs to define what data shape the UI expects
- T2 needs to expose a service interface
- Both terminals need to agree on a shared data model

## Template

```markdown
# Contract: [InterfaceName]

**ID:** `contract_[name]_[timestamp]`
**Type:** interface
**Status:** Negotiating
**Proposer:** T[N]
**Created:** [ISO timestamp]
**Updated:** [ISO timestamp]

---

## Negotiation History

### Proposal (T[N] @ HH:MM)

[Describe what you need and why]

I need this interface for [specific use case]:

```swift
struct [InterfaceName] {
    let id: UUID
    let [field1]: [Type1]
    let [field2]: [Type2]
}
```

**Requirements:**
- [Requirement 1]
- [Requirement 2]

### Response (T[N] @ HH:MM)

[Agreement, counter-proposal, or questions]

### Resolution (T4 mediated @ HH:MM)

**AGREED:** [Final decision summary]

### Implementation (T[N] @ HH:MM)

Implemented in `[file/path]`.

**Quality:** 80%
**File:** `[path/to/implementation.swift]`
```

## Example: UserProfile Interface

```markdown
# Contract: UserProfile

**ID:** `contract_userprofile_20260202103000`
**Type:** interface
**Status:** Negotiating
**Proposer:** T1
**Created:** 2026-02-02T10:30:00
**Updated:** 2026-02-02T10:30:00

---

## Negotiation History

### Proposal (T1 @ 10:30)

T1 needs this interface for the profile screen. The UI will display user info
and allow editing of the display name.

```swift
struct UserProfile {
    let id: UUID
    let displayName: String
    let avatarURL: URL?
}
```

**Requirements:**
- id must be stable and unique
- displayName is user-editable
- avatarURL can be nil for users without avatars
```

## Tips

1. **Be specific about requirements** - Don't assume the other terminal knows why you need something
2. **Include code examples** - Visual contracts are easier to understand
3. **List edge cases** - What happens with nil, empty strings, etc.?
4. **Reference dependencies** - If this contract depends on others, mention them
