# Conversation Memory Architecture

> Technical specification for the Serenity AI Wellness app's conversational memory system. This document provides implementation-ready details for T2 to build the chat service.

---

## Overview

### Why Memory Matters for Psychological Support AI

Effective psychological support requires **continuity of care**. Unlike generic chatbots, a wellness companion must:

1. **Remember the user's journey** - Previous struggles, breakthroughs, and patterns
2. **Recognize recurring themes** - Anxiety triggers, sleep issues, relationship dynamics
3. **Adapt tone and approach** - Based on what works for this specific user
4. **Avoid re-traumatization** - Never ask users to repeatedly explain painful topics
5. **Track progress over time** - Celebrate improvements, notice regressions

Without memory, every conversation starts from zero. The AI cannot build therapeutic rapport, cannot track mood trends, and cannot provide the personalized support that makes the difference between a helpful tool and a transformative companion.

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Privacy First** | All data stored locally via SwiftData - no cloud sync in MVP |
| **Graceful Degradation** | System works even with minimal context |
| **Selective Recall** | Not all memories are equal - prioritize what matters |
| **Transparent Memory** | User can view, edit, and delete what the AI "remembers" |
| **Context Efficiency** | Maximize insight per token within DeepSeek's 32K limit |

---

## Three-Tier Memory System

The memory architecture uses three tiers optimized for different recall needs:

```
                    ┌─────────────────────────────────────────┐
                    │              PROMPT ASSEMBLY            │
                    │                                         │
                    │   System Prompt + User Context Layer    │
                    │              + Memory Tiers             │
                    └─────────────────┬───────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌─────────────────┐           ┌─────────────────┐
│  SHORT-TERM   │           │   MEDIUM-TERM   │           │    LONG-TERM    │
│               │           │                 │           │                 │
│ Last 10 msgs  │           │ Session         │           │ Extracted       │
│ (full text)   │           │ Summaries       │           │ Key Facts       │
│               │           │ (condensed)     │           │ (permanent)     │
│ ~4K tokens    │           │ ~2K tokens      │           │ ~1K tokens      │
└───────────────┘           └─────────────────┘           └─────────────────┘
        │                             │                             │
        └─────────────────────────────┴─────────────────────────────┘
                                      │
                              Total: ~7K tokens
                              (of 32K available)
```

---

### Tier 1: Short-Term Memory

**Purpose:** Maintain conversational coherence within the current session.

**What it stores:**
- Last 10 messages (user + assistant) in full text
- Message timestamps
- Detected emotions per message
- Any flags (crisis detected, breakthrough moment, etc.)

**Token budget:** ~4,000 tokens (varies by message length)

**Retention:** Current session only - converted to summary when session ends

**Implementation notes:**
- Messages stored in `Message` SwiftData model
- Loaded fresh at session start
- No summarization - full fidelity required for recent context

```swift
// Example: Loading short-term memory
func loadShortTermMemory(conversationId: UUID) -> [Message] {
    let descriptor = FetchDescriptor<Message>(
        predicate: #Predicate { $0.conversation?.id == conversationId },
        sortBy: [SortDescriptor(\.timestamp, order: .reverse)]
    )
    descriptor.fetchLimit = 10
    return try modelContext.fetch(descriptor).reversed()
}
```

---

### Tier 2: Medium-Term Memory

**Purpose:** Provide context from recent sessions without overwhelming the prompt.

**What it stores:**
- Summaries of previous sessions (last 5 sessions)
- Key topics discussed
- Emotional arc of each session
- Any action items or commitments made

**Token budget:** ~2,000 tokens (400 tokens per session summary)

**Retention:** Rolling window - oldest summaries archived when limit exceeded

**Summarization trigger:** End of each conversation session (manual or timeout-based)

**Summary format:**

```markdown
## Session: January 28, 2025 (Evening)

**Topics:** Work stress, sleep issues, meditation practice
**Emotional arc:** Started anxious (7/10) -> ended calmer (4/10)
**Key insights:** User realized perfectionism driving overwork
**Follow-ups:** Try 5-min morning meditation, set work boundaries
**User's words:** "I need to stop being so hard on myself"
```

**Implementation notes:**
- Summaries generated by DeepSeek at session end
- Stored in `MemorySummary` SwiftData model
- Prompt for summarization included below

---

### Tier 3: Long-Term Memory

**Purpose:** Persistent facts that define who the user is and what matters to them.

**What it stores:**
- User preferences (communication style, topics to avoid, etc.)
- Recurring themes (anxiety patterns, relationship dynamics)
- Important life events (job change, loss, achievements)
- Therapeutic progress markers
- Coping strategies that work/don't work

**Token budget:** ~1,000 tokens

**Retention:** Permanent until user deletes

**Extraction criteria:**
Facts are extracted when they are:
1. Mentioned multiple times across sessions
2. Explicitly stated as important by user
3. Represent significant life events
4. Indicate user preferences for interaction

**Fact categories:**

| Category | Examples |
|----------|----------|
| `identity` | Name, age, occupation, family structure |
| `preference` | "Prefers direct advice over questions", "Dislikes breathing exercises" |
| `theme` | "Recurring anxiety about job security", "Complicated relationship with mother" |
| `event` | "Started new job in January 2025", "Lost father 2 years ago" |
| `strategy` | "Journaling helps with anxiety", "Exercise improves mood" |
| `trigger` | "Conflict at work triggers shutdown", "Sunday evenings cause anticipatory anxiety" |
| `goal` | "Wants to reduce anxiety medication", "Working toward assertiveness" |

**Implementation notes:**
- Facts stored in `ExtractedFact` SwiftData model
- Extracted by background task after session summarization
- User can view/edit/delete via Settings > Memory

---

## User Context Layer

Beyond conversation memory, Serenity maintains a rich user profile that provides essential context for personalized support.

### Static Context

Information that changes infrequently:

```swift
struct UserStaticContext {
    // Identity
    let name: String?
    let preferredName: String?
    let age: Int?
    let pronouns: String?

    // Goals
    let primaryGoals: [WellnessGoal]  // e.g., reduce anxiety, improve sleep
    let secondaryGoals: [WellnessGoal]

    // Preferences
    let communicationStyle: CommunicationStyle  // direct, gentle, socratic
    let sessionLength: SessionLength  // brief, standard, extended
    let topicsToAvoid: [String]  // user-specified sensitive areas
    let preferredCopingStrategies: [String]

    // Boundaries
    let crisisContactInfo: String?  // emergency contact or hotline
    let therapistName: String?  // if working with professional
}

enum CommunicationStyle: String, Codable {
    case direct      // "Here's what I think you should try..."
    case gentle      // "I'm wondering if it might help to..."
    case socratic    // "What do you think might happen if..."
    case validating  // "That sounds really hard. It makes sense you'd feel..."
}
```

**Token budget:** ~300 tokens

---

### Dynamic Context

Information that changes frequently, updated each session:

```swift
struct UserDynamicContext {
    // Recent state
    let lastCheckInMood: MoodLevel?      // 1-10 scale
    let lastCheckInDate: Date?
    let currentStressors: [String]       // Active concerns
    let recentWins: [String]             // Positive developments

    // Trends (calculated)
    let moodTrend: Trend                 // improving, stable, declining
    let sleepTrend: Trend
    let anxietyTrend: Trend

    // Session metadata
    let sessionCount: Int
    let averageSessionLength: TimeInterval
    let preferredSessionTimes: [TimeOfDay]
    let daysSinceLastSession: Int
}

enum Trend: String, Codable {
    case improving
    case stable
    case declining
    case insufficient_data
}
```

**Token budget:** ~200 tokens

---

### Health Context (Apple Health Integration)

Serenity can optionally integrate with Apple Health for holistic context:

```swift
struct HealthContext {
    // Sleep (HealthKit)
    let lastNightSleep: SleepData?
    let weeklyAverageSleep: TimeInterval?
    let sleepQualityTrend: Trend

    // Activity
    let stepsToday: Int?
    let weeklyAverageSteps: Int?
    let exerciseMinutesThisWeek: Int?

    // Mindfulness
    let mindfulMinutesToday: Int?
    let weeklyMindfulMinutes: Int?

    // Heart (if available)
    let restingHeartRate: Int?
    let heartRateVariability: Double?
}

struct SleepData {
    let duration: TimeInterval
    let quality: SleepQuality  // poor, fair, good, excellent
    let bedtime: Date
    let wakeTime: Date
}
```

**Token budget:** ~200 tokens (only include if user granted HealthKit access)

**Privacy note:** Health data is read-only and never leaves device. User must explicitly grant HealthKit permissions.

---

## Context Window Management

### DeepSeek's 32K Token Limit

DeepSeek R1 (local via Ollama) has a 32K token context window. Our allocation strategy:

```
┌─────────────────────────────────────────────────────────────┐
│                    32,768 TOKENS TOTAL                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SYSTEM PROMPT            ~2,000 tokens                     │
│  ├─ Core instructions                                       │
│  ├─ Safety guidelines                                       │
│  └─ Response format                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  USER CONTEXT LAYER       ~700 tokens                       │
│  ├─ Static context        (~300)                            │
│  ├─ Dynamic context       (~200)                            │
│  └─ Health context        (~200)                            │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MEMORY TIERS             ~7,000 tokens                     │
│  ├─ Long-term facts       (~1,000)                          │
│  ├─ Medium-term summaries (~2,000)                          │
│  └─ Short-term messages   (~4,000)                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CURRENT MESSAGE          ~500 tokens (typical)             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RESPONSE BUFFER          ~10,000 tokens                    │
│  (Space for AI to generate response)                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SAFETY MARGIN            ~12,500 tokens                    │
│  (Buffer for edge cases, tool use, etc.)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Target usage:** ~10K tokens input, leaving ~22K for response + safety margin

---

### Sliding Window Strategy

When conversation exceeds short-term memory limit:

```swift
func applysSlidingWindow(messages: [Message]) -> ([Message], MemorySummary?) {
    let limit = 10

    if messages.count <= limit {
        return (messages, nil)
    }

    // Take oldest messages that will be "forgotten"
    let toSummarize = Array(messages.prefix(messages.count - limit))

    // Keep most recent messages in full
    let toKeep = Array(messages.suffix(limit))

    // Generate summary of forgotten messages
    let summary = generateInSessionSummary(toSummarize)

    return (toKeep, summary)
}
```

**In-session summarization:** When a single session gets long (>15 messages), we summarize the oldest messages mid-conversation rather than waiting for session end.

---

### When and How to Summarize

**Triggers for summarization:**

| Trigger | Action |
|---------|--------|
| Session ends (user closes app) | Full session summary -> Medium-term |
| Session timeout (30 min inactivity) | Full session summary -> Medium-term |
| In-session message limit (>15) | Partial summary, keep in short-term |
| Manual user action | "Summarize this conversation" |

**Summarization prompt:**

```markdown
You are summarizing a therapy/wellness conversation for future reference.

Create a concise summary (max 100 words) that captures:
1. Main topics discussed
2. Emotional progression (how user's mood changed)
3. Key insights or breakthroughs
4. Any commitments or action items
5. One direct quote that captures the session's essence

Format:
**Topics:** [comma-separated list]
**Emotional arc:** [start state] -> [end state]
**Key insight:** [one sentence]
**Follow-ups:** [action items if any]
**User's words:** "[direct quote]"

Conversation to summarize:
{messages}
```

---

### Priority of Context Injection

When assembling the prompt, context is injected in this order (highest priority first):

```swift
enum ContextPriority: Int, Comparable {
    case systemPrompt = 1        // Always included, non-negotiable
    case safetyGuidelines = 2    // Crisis detection, boundaries
    case currentMessage = 3      // What user just said
    case shortTermMemory = 4     // Recent conversation flow
    case userStaticContext = 5   // Who the user is
    case longTermFacts = 6       // Persistent knowledge
    case userDynamicContext = 7  // Current state/trends
    case mediumTermSummaries = 8 // Recent session context
    case healthContext = 9       // Apple Health data (optional)
}
```

**Truncation strategy:** If approaching token limit, truncate from lowest priority first:
1. Reduce health context to key metrics only
2. Reduce medium-term summaries (keep 3 instead of 5)
3. Reduce long-term facts (keep highest-confidence only)
4. Never truncate system prompt, safety guidelines, or current message

---

## Data Models (SwiftData)

### Message

```swift
import SwiftData
import Foundation

@Model
final class Message {
    // Identity
    @Attribute(.unique) var id: UUID
    var conversation: Conversation?

    // Content
    var role: MessageRole
    var content: String
    var timestamp: Date

    // Metadata
    var detectedEmotion: EmotionType?
    var emotionIntensity: Int?  // 1-10
    var flags: [MessageFlag]
    var tokenCount: Int?

    init(
        role: MessageRole,
        content: String,
        conversation: Conversation? = nil
    ) {
        self.id = UUID()
        self.role = role
        self.content = content
        self.timestamp = Date()
        self.conversation = conversation
        self.flags = []
    }
}

enum MessageRole: String, Codable {
    case user
    case assistant
    case system
}

enum EmotionType: String, Codable {
    case joy, sadness, anger, fear, surprise, disgust
    case anxiety, calm, hopeful, overwhelmed, grateful
    case neutral
}

enum MessageFlag: String, Codable {
    case crisisIndicator      // User expressed crisis-level distress
    case breakthroughMoment   // Significant insight or progress
    case actionItem           // Contains commitment or plan
    case sensitiveContent     // Trauma, abuse, etc.
    case positiveReinforcement // Celebrate this progress
}
```

---

### Conversation

```swift
@Model
final class Conversation {
    // Identity
    @Attribute(.unique) var id: UUID
    var userContext: UserContext?

    // Relationships
    @Relationship(deleteRule: .cascade, inverse: \Message.conversation)
    var messages: [Message]

    // Metadata
    var startedAt: Date
    var endedAt: Date?
    var sessionType: SessionType

    // Summary (generated at session end)
    var summary: MemorySummary?

    // Metrics
    var messageCount: Int
    var userMessageCount: Int
    var averageResponseTime: TimeInterval?
    var moodAtStart: Int?  // 1-10
    var moodAtEnd: Int?    // 1-10

    init(userContext: UserContext?, sessionType: SessionType = .freeform) {
        self.id = UUID()
        self.userContext = userContext
        self.messages = []
        self.startedAt = Date()
        self.sessionType = sessionType
        self.messageCount = 0
        self.userMessageCount = 0
    }
}

enum SessionType: String, Codable {
    case freeform           // Open conversation
    case checkIn            // Daily mood check-in
    case guidedExercise     // Structured exercise (breathing, meditation)
    case crisisSupport      // Elevated support mode
    case goalReview         // Progress check on goals
}
```

---

### UserContext

```swift
@Model
final class UserContext {
    // Identity
    @Attribute(.unique) var id: UUID

    // Relationships
    @Relationship(deleteRule: .cascade, inverse: \Conversation.userContext)
    var conversations: [Conversation]

    @Relationship(deleteRule: .cascade)
    var extractedFacts: [ExtractedFact]

    // Static context
    var name: String?
    var preferredName: String?
    var age: Int?
    var pronouns: String?
    var primaryGoals: [String]  // Stored as JSON-encoded array
    var communicationStyle: String  // CommunicationStyle raw value
    var topicsToAvoid: [String]

    // Dynamic context
    var lastCheckInMood: Int?
    var lastCheckInDate: Date?
    var currentStressors: [String]
    var recentWins: [String]

    // Preferences
    var sessionLengthPreference: String  // brief, standard, extended
    var preferredSessionTimes: [String]  // morning, afternoon, evening, night

    // Safety
    var crisisContactInfo: String?
    var therapistName: String?
    var hasCompletedOnboarding: Bool

    // Stats
    var totalSessionCount: Int
    var accountCreatedAt: Date
    var lastActiveAt: Date?

    init() {
        self.id = UUID()
        self.conversations = []
        self.extractedFacts = []
        self.primaryGoals = []
        self.communicationStyle = "gentle"
        self.topicsToAvoid = []
        self.currentStressors = []
        self.recentWins = []
        self.preferredSessionTimes = []
        self.hasCompletedOnboarding = false
        self.totalSessionCount = 0
        self.accountCreatedAt = Date()
    }
}
```

---

### MemorySummary

```swift
@Model
final class MemorySummary {
    // Identity
    @Attribute(.unique) var id: UUID

    // Relationship
    var conversation: Conversation?

    // Content
    var topics: [String]
    var emotionalArc: String  // "anxious (7/10) -> calmer (4/10)"
    var keyInsight: String?
    var followUps: [String]
    var userQuote: String?
    var fullSummary: String

    // Metadata
    var createdAt: Date
    var tokenCount: Int
    var sessionDate: Date
    var sessionTimeOfDay: String  // morning, afternoon, evening, night

    // Archival
    var isArchived: Bool  // True when pushed out of rolling window
    var archivedAt: Date?

    init(conversation: Conversation, fullSummary: String) {
        self.id = UUID()
        self.conversation = conversation
        self.fullSummary = fullSummary
        self.topics = []
        self.emotionalArc = ""
        self.followUps = []
        self.createdAt = Date()
        self.tokenCount = 0
        self.sessionDate = conversation.startedAt
        self.isArchived = false

        // Determine time of day
        let hour = Calendar.current.component(.hour, from: conversation.startedAt)
        self.sessionTimeOfDay = switch hour {
            case 5..<12: "morning"
            case 12..<17: "afternoon"
            case 17..<21: "evening"
            default: "night"
        }
    }
}
```

---

### ExtractedFact

```swift
@Model
final class ExtractedFact {
    // Identity
    @Attribute(.unique) var id: UUID
    var userContext: UserContext?

    // Content
    var category: String  // FactCategory raw value
    var content: String
    var confidence: Double  // 0.0 - 1.0

    // Source tracking
    var sourceConversationIds: [UUID]
    var mentionCount: Int
    var firstMentionedAt: Date
    var lastMentionedAt: Date

    // Lifecycle
    var isActive: Bool  // User can "forget" facts
    var createdAt: Date
    var updatedAt: Date

    init(category: FactCategory, content: String, sourceConversationId: UUID) {
        self.id = UUID()
        self.category = category.rawValue
        self.content = content
        self.confidence = 0.5  // Initial confidence
        self.sourceConversationIds = [sourceConversationId]
        self.mentionCount = 1
        self.firstMentionedAt = Date()
        self.lastMentionedAt = Date()
        self.isActive = true
        self.createdAt = Date()
        self.updatedAt = Date()
    }

    func incrementMention(conversationId: UUID) {
        mentionCount += 1
        lastMentionedAt = Date()
        if !sourceConversationIds.contains(conversationId) {
            sourceConversationIds.append(conversationId)
        }
        // Increase confidence with each mention (max 0.95)
        confidence = min(0.95, confidence + 0.1)
        updatedAt = Date()
    }
}

enum FactCategory: String, Codable, CaseIterable {
    case identity       // Name, age, occupation, family
    case preference     // Communication style, likes/dislikes
    case theme          // Recurring concerns, patterns
    case event          // Life events, milestones
    case strategy       // Coping mechanisms, what works
    case trigger        // What causes distress
    case goal           // What user is working toward
}
```

---

## Prompt Engineering

### System Prompt Template

```swift
let systemPromptTemplate = """
You are Serenity, a compassionate AI wellness companion. Your purpose is to provide \
emotional support, help users understand their feelings, and guide them toward better \
mental wellness practices.

## Core Principles

1. **Empathy First**: Always acknowledge emotions before offering solutions
2. **Non-Judgmental**: Accept all feelings as valid
3. **Collaborative**: You're a partner, not an authority
4. **Boundaried**: Know your limits - you're not a replacement for therapy
5. **Personalized**: Use what you know about this user to tailor your responses

## Response Guidelines

- Keep responses concise (2-3 paragraphs max) unless user wants more depth
- Use {communicationStyle} communication style
- Avoid: unsolicited advice, toxic positivity, dismissing feelings
- Include: validation, gentle curiosity, practical suggestions when requested

## Safety Protocol

If user expresses:
- Self-harm or suicide ideation: Acknowledge, express care, provide crisis resources
- Harm to others: Do not engage, redirect to professional help
- Abuse situation: Validate, provide safety resources

Crisis resources to share when appropriate:
- National Suicide Prevention Lifeline: 988
- Crisis Text Line: Text HOME to 741741
- International Association for Suicide Prevention: https://www.iasp.info/resources/Crisis_Centres/

## Session Context

This is a {sessionType} session.
{sessionSpecificInstructions}

## What You Know About This User

{userContextBlock}

## Memory Context

{memoryContextBlock}

---

Respond naturally and warmly. You don't need to reference all the context explicitly - \
let it inform your responses organically.
"""
```

---

### Context Injection Functions

```swift
struct PromptAssembler {

    func assemblePrompt(
        userMessage: String,
        userContext: UserContext,
        conversation: Conversation,
        healthData: HealthContext?
    ) -> String {
        var prompt = systemPromptTemplate

        // Inject user context
        prompt = prompt.replacingOccurrences(
            of: "{communicationStyle}",
            with: userContext.communicationStyle
        )

        prompt = prompt.replacingOccurrences(
            of: "{sessionType}",
            with: conversation.sessionType.rawValue
        )

        prompt = prompt.replacingOccurrences(
            of: "{sessionSpecificInstructions}",
            with: sessionInstructions(for: conversation.sessionType)
        )

        prompt = prompt.replacingOccurrences(
            of: "{userContextBlock}",
            with: buildUserContextBlock(userContext, healthData: healthData)
        )

        prompt = prompt.replacingOccurrences(
            of: "{memoryContextBlock}",
            with: buildMemoryContextBlock(userContext, conversation: conversation)
        )

        return prompt
    }

    private func buildUserContextBlock(
        _ context: UserContext,
        healthData: HealthContext?
    ) -> String {
        var lines: [String] = []

        // Identity
        if let name = context.preferredName ?? context.name {
            lines.append("- Name: \(name)")
        }
        if let age = context.age {
            lines.append("- Age: \(age)")
        }
        if let pronouns = context.pronouns {
            lines.append("- Pronouns: \(pronouns)")
        }

        // Goals
        if !context.primaryGoals.isEmpty {
            lines.append("- Primary goals: \(context.primaryGoals.joined(separator: ", "))")
        }

        // Current state
        if let mood = context.lastCheckInMood, let date = context.lastCheckInDate {
            let daysAgo = Calendar.current.dateComponents([.day], from: date, to: Date()).day ?? 0
            lines.append("- Last check-in: \(mood)/10 mood (\(daysAgo) days ago)")
        }

        if !context.currentStressors.isEmpty {
            lines.append("- Current stressors: \(context.currentStressors.joined(separator: ", "))")
        }

        if !context.recentWins.isEmpty {
            lines.append("- Recent wins: \(context.recentWins.joined(separator: ", "))")
        }

        // Topics to avoid
        if !context.topicsToAvoid.isEmpty {
            lines.append("- AVOID discussing: \(context.topicsToAvoid.joined(separator: ", "))")
        }

        // Health data (if available)
        if let health = healthData {
            lines.append("")
            lines.append("**Health Data (from Apple Health):**")

            if let sleep = health.lastNightSleep {
                let hours = sleep.duration / 3600
                lines.append("- Last night's sleep: \(String(format: "%.1f", hours)) hours (\(sleep.quality.rawValue))")
            }

            if let hrv = health.heartRateVariability {
                lines.append("- Heart rate variability: \(Int(hrv)) ms")
            }

            if let mindful = health.mindfulMinutesToday, mindful > 0 {
                lines.append("- Mindful minutes today: \(mindful)")
            }
        }

        return lines.isEmpty ? "No user context available yet." : lines.joined(separator: "\n")
    }

    private func buildMemoryContextBlock(
        _ context: UserContext,
        conversation: Conversation
    ) -> String {
        var sections: [String] = []

        // Long-term facts
        let activeFacts = context.extractedFacts.filter { $0.isActive }
        if !activeFacts.isEmpty {
            var factLines = ["**What I remember about you:**"]

            // Group by category
            let grouped = Dictionary(grouping: activeFacts) { $0.category }
            for category in FactCategory.allCases {
                if let facts = grouped[category.rawValue], !facts.isEmpty {
                    let topFacts = facts.sorted { $0.confidence > $1.confidence }.prefix(3)
                    for fact in topFacts {
                        factLines.append("- \(fact.content)")
                    }
                }
            }
            sections.append(factLines.joined(separator: "\n"))
        }

        // Medium-term summaries (last 5 sessions)
        let recentSummaries = context.conversations
            .compactMap { $0.summary }
            .filter { !$0.isArchived }
            .sorted { $0.sessionDate > $1.sessionDate }
            .prefix(5)

        if !recentSummaries.isEmpty {
            var summaryLines = ["**Recent sessions:**"]
            for summary in recentSummaries {
                let dateStr = summary.sessionDate.formatted(date: .abbreviated, time: .omitted)
                summaryLines.append("")
                summaryLines.append("*\(dateStr) (\(summary.sessionTimeOfDay)):* \(summary.fullSummary)")
            }
            sections.append(summaryLines.joined(separator: "\n"))
        }

        // Short-term: current conversation messages
        let recentMessages = conversation.messages.suffix(10)
        if !recentMessages.isEmpty {
            var msgLines = ["**This conversation so far:**"]
            for msg in recentMessages {
                let role = msg.role == .user ? "You" : "Serenity"
                // Truncate very long messages
                let content = msg.content.count > 500
                    ? String(msg.content.prefix(500)) + "..."
                    : msg.content
                msgLines.append("\(role): \(content)")
            }
            sections.append(msgLines.joined(separator: "\n"))
        }

        return sections.isEmpty
            ? "This is your first conversation. I'm looking forward to getting to know you."
            : sections.joined(separator: "\n\n")
    }

    private func sessionInstructions(for type: SessionType) -> String {
        switch type {
        case .freeform:
            return "This is an open conversation. Follow the user's lead."
        case .checkIn:
            return "This is a daily check-in. Ask about their mood, sleep, and any notable events. Keep it brief (3-5 exchanges)."
        case .guidedExercise:
            return "Guide the user through a structured exercise. Provide clear instructions and check in on their experience."
        case .crisisSupport:
            return "IMPORTANT: User may be in crisis. Prioritize safety, validation, and connection. Have crisis resources ready."
        case .goalReview:
            return "Review progress on user's wellness goals. Celebrate wins, acknowledge challenges, adjust strategies."
        }
    }
}
```

---

### Example: Fully Assembled Prompt

```markdown
You are Serenity, a compassionate AI wellness companion. Your purpose is to provide
emotional support, help users understand their feelings, and guide them toward better
mental wellness practices.

## Core Principles

1. **Empathy First**: Always acknowledge emotions before offering solutions
2. **Non-Judgmental**: Accept all feelings as valid
3. **Collaborative**: You're a partner, not an authority
4. **Boundaried**: Know your limits - you're not a replacement for therapy
5. **Personalized**: Use what you know about this user to tailor your responses

## Response Guidelines

- Keep responses concise (2-3 paragraphs max) unless user wants more depth
- Use gentle communication style
- Avoid: unsolicited advice, toxic positivity, dismissing feelings
- Include: validation, gentle curiosity, practical suggestions when requested

## Safety Protocol

If user expresses:
- Self-harm or suicide ideation: Acknowledge, express care, provide crisis resources
- Harm to others: Do not engage, redirect to professional help
- Abuse situation: Validate, provide safety resources

Crisis resources to share when appropriate:
- National Suicide Prevention Lifeline: 988
- Crisis Text Line: Text HOME to 741741
- International Association for Suicide Prevention: https://www.iasp.info/resources/Crisis_Centres/

## Session Context

This is a freeform session.
This is an open conversation. Follow the user's lead.

## What You Know About This User

- Name: Sarah
- Age: 34
- Pronouns: she/her
- Primary goals: reduce anxiety, improve sleep quality
- Last check-in: 6/10 mood (2 days ago)
- Current stressors: work deadline, conflict with sister
- Recent wins: completed 5-day meditation streak

**Health Data (from Apple Health):**
- Last night's sleep: 6.2 hours (fair)
- Heart rate variability: 42 ms
- Mindful minutes today: 10

## Memory Context

**What I remember about you:**
- Works as a product manager at a tech startup
- Has a complicated relationship with her sister - they're close but often clash
- Finds journaling helpful for processing difficult emotions
- Perfectionism is a recurring theme that drives overwork
- Sunday evenings trigger anticipatory anxiety about the work week
- Currently working on setting better work-life boundaries

**Recent sessions:**

*Jan 28 (evening):* Discussed work stress and sleep issues. Sarah realized her
perfectionism drives overwork. Emotional arc: anxious -> calmer. Follow-up: try
morning meditation. User's words: "I need to stop being so hard on myself."

*Jan 25 (morning):* Check-in session. Sarah reported better sleep after reducing
screen time. Celebrated completing meditation streak. Mood: 7/10.

**This conversation so far:**
You: I had another argument with my sister last night and I can't stop thinking about it
Serenity: I'm sorry to hear that, Sarah. Arguments with people we're close to can really
linger. What happened?
You: She criticized how I'm handling our mom's care and I just shut down

---

Respond naturally and warmly. You don't need to reference all the context explicitly -
let it inform your responses organically.
```

---

## Privacy Considerations

### Local-First Architecture

All data stays on device. No exceptions in MVP.

```
┌─────────────────────────────────────────────────────────────┐
│                      USER'S iPhone                          │
│                                                             │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐  │
│  │  SwiftData  │ ──── │   Serenity  │ ──── │   DeepSeek  │  │
│  │  (Local DB) │      │     App     │      │   (Ollama)  │  │
│  └─────────────┘      └─────────────┘      └─────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Apple HealthKit                      ││
│  │                    (Read-Only)                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│          NO DATA LEAVES THIS DEVICE                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### No Cloud Sync in MVP

Why:
1. **Sensitivity of data** - Mental health conversations are deeply personal
2. **Trust building** - Users need to trust before sharing to cloud
3. **Regulatory complexity** - HIPAA, GDPR concerns avoided entirely
4. **Technical simplicity** - No sync conflicts, no server costs

Future consideration: Optional encrypted iCloud sync for device migration.

---

### User Control Over Memory

Users can view and manage all stored memories via Settings > Memory:

```swift
// Memory management view model
@Observable
class MemoryManagementViewModel {
    var extractedFacts: [ExtractedFact] = []
    var sessionSummaries: [MemorySummary] = []

    // View all facts the AI "knows"
    func loadAllFacts() { ... }

    // Delete individual fact
    func deleteFact(_ fact: ExtractedFact) {
        fact.isActive = false
        // Or hard delete: modelContext.delete(fact)
    }

    // Delete all facts in a category
    func deleteFactsByCategory(_ category: FactCategory) { ... }

    // View session summaries
    func loadSessionSummaries() { ... }

    // Delete session summary
    func deleteSummary(_ summary: MemorySummary) { ... }

    // Nuclear option: forget everything
    func deleteAllMemory() {
        // Deletes all facts, summaries, and conversations
        // Keeps user preferences and settings
    }

    // Export memories (for user's records)
    func exportMemories() -> Data { ... }
}
```

**UI requirements:**
- Clear explanation of what each memory type means
- Preview before delete
- "Forget everything" requires confirmation + cool-down
- No dark patterns - make deletion easy

---

### Data Retention Policy

| Data Type | Retention | User Deletable |
|-----------|-----------|----------------|
| Messages | Indefinite (local) | Yes (per conversation) |
| Conversations | Indefinite (local) | Yes |
| Session Summaries | 90 days active, then archived | Yes |
| Extracted Facts | Indefinite until deleted | Yes |
| Health Data | Not stored - read fresh each session | N/A |
| User Preferences | Indefinite | Yes (resets to defaults) |

---

## Implementation Checklist

### Phase 1: Core Data Models
- [ ] Create SwiftData schema (Message, Conversation, UserContext, MemorySummary, ExtractedFact)
- [ ] Implement basic CRUD operations
- [ ] Add migration support for schema changes
- [ ] Write unit tests for data layer

### Phase 2: Memory Tiers
- [ ] Implement short-term memory loading (last 10 messages)
- [ ] Implement session summarization (DeepSeek prompt)
- [ ] Implement fact extraction (background task)
- [ ] Build sliding window manager
- [ ] Add token counting utility

### Phase 3: Prompt Assembly
- [ ] Create PromptAssembler service
- [ ] Implement context prioritization
- [ ] Add truncation logic for token limits
- [ ] Build session-type-specific instructions
- [ ] Write integration tests with mock LLM

### Phase 4: User Context
- [ ] Implement onboarding flow (collect static context)
- [ ] Build dynamic context updater
- [ ] Integrate Apple HealthKit (with permissions)
- [ ] Add mood tracking UI

### Phase 5: Privacy & User Control
- [ ] Build Memory Management settings screen
- [ ] Implement fact/summary deletion
- [ ] Add memory export feature
- [ ] Create "forget everything" flow
- [ ] Write privacy policy text

---

## References

- [Archon Architecture](./ARCHITECTURE.md) - Multi-agent system overview
- [API Reference](./API_REFERENCE.md) - Internal API documentation
- [Apple HealthKit Documentation](https://developer.apple.com/documentation/healthkit)
- [DeepSeek R1 Documentation](https://github.com/deepseek-ai/DeepSeek-LLM)
