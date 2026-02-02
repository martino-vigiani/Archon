# User Persona System - Serenity

> How Serenity builds and maintains understanding of each user for personalized support.

---

## Overview

Serenity's effectiveness depends on knowing the user. Unlike generic chatbots, Serenity builds a **living persona** of each user that evolves over time. This document defines how we capture, store, and utilize user data to provide meaningful psychological support.

---

## The Persona Model

### User Persona Structure

```swift
@Model
final class UserPersona {
    // Identity
    var id: UUID
    var displayName: String
    var preferredPronouns: String?
    var ageRange: AgeRange?

    // Context
    var occupation: String?
    var lifeCircumstances: [LifeCircumstance]
    var supportNetwork: String? // "lives alone", "has partner", etc.

    // Wellness Profile
    var primaryGoals: [WellnessGoal]
    var challenges: [Challenge]
    var copingStrategies: [String]
    var triggers: [String]

    // Preferences
    var communicationStyle: CommunicationStyle
    var conversationTopics: TopicPreferences
    var responseLength: ResponseLengthPreference

    // Temporal
    var createdAt: Date
    var lastUpdatedAt: Date
    var lastActiveAt: Date

    // Relationship
    var relationshipStage: RelationshipStage
    var totalConversations: Int
    var totalMessages: Int
}
```

### Supporting Types

```swift
enum AgeRange: String, Codable {
    case under18 = "under_18"
    case young_adult = "18-24"
    case adult = "25-34"
    case mid_adult = "35-44"
    case mature_adult = "45-54"
    case senior = "55+"
}

enum LifeCircumstance: String, Codable {
    case student
    case employed
    case selfEmployed
    case unemployed
    case caregiver
    case retired
    case parentingYoungChildren
    case parentingTeens
    case emptyNester
    case recentlyDivorced
    case recentlyWidowed
    case newRelationship
    case chronicIllness
    case inRecovery
}

enum WellnessGoal: String, Codable {
    case reduceAnxiety
    case improveSleep
    case buildConfidence
    case manageStress
    case processGrief
    case improveRelationships
    case breakBadHabits
    case buildGoodHabits
    case findPurpose
    case improveWorkLifeBalance
    case developMindfulness
    case increaseActivity
}

enum Challenge: String, Codable {
    case anxiety
    case depression
    case stress
    case insomnia
    case loneliness
    case anger
    case lowSelfEsteem
    case procrastination
    case burnout
    case relationshipIssues
    case workPressure
    case healthConcerns
}

enum CommunicationStyle: String, Codable {
    case direct         // "Tell it like it is"
    case gentle         // "Be kind and soft"
    case analytical     // "Give me data and logic"
    case motivational   // "Pump me up"
    case reflective     // "Help me think it through"
}

struct TopicPreferences: Codable {
    var comfortable: [String]    // Topics user is happy to discuss
    var sensitive: [String]      // Topics to approach carefully
    var avoid: [String]          // Topics user doesn't want to discuss
}

enum ResponseLengthPreference: String, Codable {
    case brief      // Quick check-ins, short responses
    case moderate   // Balanced, 2-3 paragraphs
    case detailed   // Deep dives, comprehensive responses
}

enum RelationshipStage: String, Codable {
    case newUser            // First 1-3 sessions
    case gettingToKnow      // Sessions 4-10
    case comfortable        // Sessions 11-30
    case trusted            // 30+ sessions
}
```

---

## Persona Collection

### Onboarding Flow

Initial persona data is collected during onboarding:

```
Welcome Screen
    ↓
"What should I call you?"
    → displayName
    ↓
"What brings you to Serenity?"
    → primaryGoals (multi-select)
    → challenges (inferred)
    ↓
"How do you prefer support?"
    → communicationStyle (visual choice)
    ↓
"Anything I should know?"
    → Optional free-text for context
    ↓
Health Permissions
    → Apple Health access
    ↓
Ready to Chat
```

### Progressive Disclosure

We don't ask everything upfront. Persona builds over time:

| Session | What We Learn |
|---------|---------------|
| 1-3 | Basic identity, primary goal, communication style |
| 4-10 | Life circumstances, triggers, coping strategies |
| 11-30 | Deeper patterns, relationships, recurring themes |
| 30+ | Comprehensive understanding, subtle preferences |

### Implicit Learning

The AI extracts information from conversations:

```swift
struct ImplicitLearning {
    // Extracted from conversation
    var mentionedPeople: [Person]      // "my sister Sarah..."
    var mentionedPlaces: [String]      // "at work...", "when I'm home..."
    var timePatterns: [TimePattern]    // "in the morning I feel...", "Mondays are hard..."
    var emotionalPatterns: [EmotionalPattern]
}

struct Person: Codable {
    var name: String
    var relationship: String  // "sister", "boss", "therapist"
    var sentiment: Sentiment  // positive, negative, neutral, mixed
}

struct EmotionalPattern: Codable {
    var trigger: String       // "work deadlines"
    var emotion: String       // "anxiety"
    var frequency: Int        // times mentioned
    var lastMentioned: Date
}
```

---

## Persona-Aware Responses

### Context Injection

When generating responses, inject persona context:

```swift
func buildPersonaContext(persona: UserPersona) -> String {
    var context = """
    ## About \(persona.displayName)

    """

    // Core identity
    if let age = persona.ageRange {
        context += "Age range: \(age.rawValue)\n"
    }
    if let occupation = persona.occupation {
        context += "Occupation: \(occupation)\n"
    }

    // Goals
    if !persona.primaryGoals.isEmpty {
        let goals = persona.primaryGoals.map { $0.rawValue }.joined(separator: ", ")
        context += "Working on: \(goals)\n"
    }

    // Communication preference
    context += """

    ## How to communicate
    Style: \(persona.communicationStyle.rawValue)
    Response length: \(persona.responseLength.rawValue)

    """

    // Topic guidance
    if !persona.conversationTopics.avoid.isEmpty {
        let avoid = persona.conversationTopics.avoid.joined(separator: ", ")
        context += "Avoid discussing: \(avoid)\n"
    }

    // Relationship context
    context += """

    ## Our relationship
    Stage: \(persona.relationshipStage.rawValue)
    Sessions together: \(persona.totalConversations)

    """

    return context
}
```

### Tone Calibration

Communication style affects AI responses:

| Style | AI Behavior |
|-------|-------------|
| Direct | Short sentences, clear advice, no hedging |
| Gentle | Soft language, lots of validation, careful phrasing |
| Analytical | Include reasoning, data references, logical structure |
| Motivational | Encouraging language, focus on progress, celebrate wins |
| Reflective | Ask questions, help user discover answers, Socratic method |

### Relationship Stage Behavior

| Stage | AI Behavior |
|-------|-------------|
| newUser | More questions, building trust, explaining approach |
| gettingToKnow | Reference past conversations, show memory |
| comfortable | More direct, can challenge gently, deeper topics |
| trusted | Full candor, can push harder, deep emotional work |

---

## Persona Updates

### Automatic Updates

```swift
class PersonaUpdateService {
    func updateFromConversation(_ conversation: Conversation, persona: UserPersona) {
        // Update last active
        persona.lastActiveAt = Date()
        persona.totalConversations += 1
        persona.totalMessages += conversation.messages.count

        // Update relationship stage
        updateRelationshipStage(persona)

        // Extract implicit learning
        let learning = extractImplicitLearning(from: conversation)
        mergeImplicitLearning(learning, into: persona)

        persona.lastUpdatedAt = Date()
    }

    private func updateRelationshipStage(_ persona: UserPersona) {
        switch persona.totalConversations {
        case 0...3: persona.relationshipStage = .newUser
        case 4...10: persona.relationshipStage = .gettingToKnow
        case 11...30: persona.relationshipStage = .comfortable
        default: persona.relationshipStage = .trusted
        }
    }
}
```

### User-Initiated Updates

Users can update their persona directly:

```
Profile Screen
├── Edit Name
├── Edit Goals (re-select)
├── Communication Style (re-select)
├── Topics to Avoid (add/remove)
├── View What Serenity Knows
│   ├── People mentioned
│   ├── Topics discussed
│   └── Patterns noticed
└── Reset Persona (start fresh)
```

---

## Privacy & Control

### User Rights

1. **View**: See everything Serenity knows about them
2. **Edit**: Correct or update any information
3. **Delete**: Remove specific facts or entire persona
4. **Export**: Download their persona data
5. **Reset**: Start completely fresh

### Data Handling

- All persona data stored locally (SwiftData)
- Never transmitted to servers
- Encrypted at rest (iOS data protection)
- Can be deleted with app deletion

---

## Implementation Checklist for T2

- [ ] Create `UserPersona` SwiftData model
- [ ] Create onboarding flow data collection
- [ ] Implement `PersonaUpdateService`
- [ ] Create persona context builder for prompts
- [ ] Implement implicit learning extraction
- [ ] Build "What Serenity Knows" view data
- [ ] Implement persona reset functionality

---

*Document for T2 (Features/Architecture) and T1 (Onboarding UI)*
