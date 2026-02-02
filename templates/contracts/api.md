# Contract Template: API

Use this template when defining an API endpoint or service method that one terminal provides and another consumes.

---

## When to Use

- T2 exposes an API that T1's UI will call
- T1 needs specific functionality from the backend
- Multiple terminals need to coordinate on service interfaces

## Template

```markdown
# Contract: [APIName]

**ID:** `contract_[name]_[timestamp]`
**Type:** api
**Status:** Negotiating
**Proposer:** T[N]
**Created:** [ISO timestamp]
**Updated:** [ISO timestamp]

---

## Negotiation History

### Proposal (T[N] @ HH:MM)

[Describe the API endpoint/method needed]

**Endpoint:** `[METHOD] /path/to/endpoint`
**Purpose:** [What this API does]

**Request:**
```json
{
    "field1": "type",
    "field2": "type"
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "field1": "type"
    }
}
```

**Error Cases:**
- 400: [Invalid input description]
- 404: [Not found description]
- 500: [Server error description]

### Response (T[N] @ HH:MM)

[Feedback on feasibility, modifications, or agreement]

### Resolution (T4 mediated @ HH:MM)

**AGREED:** [Final API specification]

### Implementation (T[N] @ HH:MM)

Implemented in `[file/path]`.

**Quality:** 80%
**File:** `[path/to/implementation.swift]`
```

## Example: User Settings API

```markdown
# Contract: UserSettingsAPI

**ID:** `contract_usersettingsapi_20260202110000`
**Type:** api
**Status:** Negotiating
**Proposer:** T1
**Created:** 2026-02-02T11:00:00
**Updated:** 2026-02-02T11:00:00

---

## Negotiation History

### Proposal (T1 @ 11:00)

T1 needs an API to fetch and update user settings for the Settings screen.

**Service Interface:**

```swift
protocol UserSettingsService {
    func getSettings() async throws -> UserSettings
    func updateSettings(_ settings: UserSettings) async throws -> UserSettings
}

struct UserSettings: Codable {
    var notificationsEnabled: Bool
    var theme: Theme
    var language: String
}

enum Theme: String, Codable {
    case light, dark, system
}
```

**Error Cases:**
- Network unavailable: Show cached settings (read-only mode)
- Invalid settings: Reject update, return validation errors
- Server error: Retry with exponential backoff

**Requirements:**
- Settings should be cached locally
- Updates should be optimistic (show immediately, sync later)
- Support offline mode for reads
```

## Tips

1. **Define both success and error paths** - APIs fail, plan for it
2. **Include data types** - Use concrete types, not just "object"
3. **Specify async behavior** - Is this synchronous? Does it cache?
4. **Document side effects** - Does this API modify state elsewhere?
5. **Consider versioning** - Will this API evolve? How?
