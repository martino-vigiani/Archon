# Serenity - AI Wellness Companion
## Product Requirements Document (PRD)

**Version:** 1.0
**Date:** February 2026
**Platform:** iOS 17+
**Status:** Ready for Development

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Target Users](#3-target-users)
4. [MVP Features](#4-mvp-features)
5. [User Stories](#5-user-stories)
6. [Success Metrics](#6-success-metrics)
7. [Out of Scope](#7-out-of-scope-v11)
8. [Technical Requirements Summary](#8-technical-requirements-summary)

---

## 1. Executive Summary

**Serenity** is an AI-powered wellness companion iOS app that provides personalized psychological support through contextual, empathetic conversations. The app remembers user context across sessions, integrates with Apple Health to provide data-informed insights, and helps users track their mental wellness journey through goal-oriented interactions.

### Core Value Proposition

Unlike generic chatbots, Serenity:
- **Remembers you**: Multi-layered memory system maintains context across sessions
- **Knows your body**: Apple Health integration provides holistic wellness picture
- **Grows with you**: Personal goals and progress tracking create meaningful journey
- **Respects your privacy**: All data stored locally on device using SwiftData

### Design Philosophy

**Liquid Glass Aesthetic**: Warm, peaceful, translucent interface that promotes calm. Dark backgrounds with soft glows, gentle gradients, and glassmorphic elements create a sanctuary-like digital space.

---

## 2. Problem Statement

### The Gap

Mental health apps fall into two categories:
1. **Clinical tools**: Cold, form-based, transactional (mood trackers, CBT worksheets)
2. **Generic chatbots**: No memory, no personalization, feel robotic

Users seeking day-to-day emotional support lack an option that feels like talking to someone who actually knows them.

### User Pain Points

| Pain Point | Impact | Serenity's Solution |
|------------|--------|---------------------|
| "I have to re-explain myself every session" | Frustration, disengagement | Multi-layered memory system |
| "The app doesn't know what's happening in my life" | Generic, unhelpful advice | Health data + conversation context |
| "It feels like talking to a robot" | No emotional connection | Warm personality, contextual responses |
| "I forget my progress" | Lack of motivation | Goal tracking, session summaries |

### Market Opportunity

- Mental wellness app market: $5.2B (2025), growing 15% annually
- 73% of users abandon mental health apps within 2 weeks (source: industry data)
- Primary abandonment reason: "Doesn't feel personal"

---

## 3. Target Users

### Primary Persona: "Mindful Maya"

**Demographics**
- Age: 28-42
- Tech-savvy professional
- iPhone user (iOS ecosystem invested)
- Apple Watch owner (likely)

**Psychographics**
- Values self-improvement and wellness
- Practices or wants to practice mindfulness
- Prefers digital solutions over in-person therapy for daily support
- Privacy-conscious - prefers local data storage

**Goals**
- Develop better emotional regulation
- Build consistent wellness habits
- Have a safe space to process daily stress
- Track progress over time

**Frustrations**
- Therapy is expensive and scheduling is difficult
- Journaling feels tedious and one-directional
- Generic wellness advice doesn't apply to their situation
- Apps don't remember previous conversations

**Quote**: "I want something between texting a friend and seeing a therapist - something that actually knows me."

---

### Secondary Persona: "Stressed-Out Sam"

**Demographics**
- Age: 22-35
- College student or early-career professional
- High-pressure environment (tech, finance, healthcare)
- Budget-conscious

**Psychographics**
- Experiences anxiety, imposter syndrome
- Wants quick emotional relief
- Skeptical of "wellness" marketing
- Values efficiency

**Goals**
- Quick stress relief during work day
- Better sleep quality
- Managing anxiety without medication
- Understanding their emotional patterns

**Frustrations**
- Don't have time for lengthy meditation sessions
- Feel silly using affirmation apps
- Can't afford regular therapy
- Need support at 2am, not 2pm

**Quote**: "I just need to vent sometimes without burdening my friends."

---

### Anti-Persona: Who Serenity is NOT For

- Users in acute mental health crisis (need professional help)
- Users seeking clinical diagnosis or treatment
- Users who prefer human-only interaction
- Children under 18 (content not designed for minors)

---

## 4. MVP Features

### 4.1 AI Chat with Memory/Context

**Priority:** P0 (Core Feature)

#### Overview

Conversational AI interface providing psychological support through empathetic, contextual dialogue. The AI maintains memory across sessions, creating continuity and personalization.

#### Functional Requirements

| ID | Requirement | Details |
|----|-------------|---------|
| CHAT-01 | Real-time messaging | User sends messages, receives AI responses with typing indicator |
| CHAT-02 | Message persistence | All conversations stored locally via SwiftData |
| CHAT-03 | Session continuity | AI references previous conversations naturally |
| CHAT-04 | Context injection | Health data and goals automatically included in AI context |
| CHAT-05 | Response streaming | Responses appear word-by-word (streaming API) |
| CHAT-06 | Error handling | Graceful degradation when offline or API fails |

#### Memory System Architecture

```
THREE-TIER MEMORY SYSTEM

SHORT-TERM MEMORY (Working Context)
├── Last 10 messages from current session
├── Injected into every API call
└── Purpose: Conversational coherence

MEDIUM-TERM MEMORY (Session Summaries)
├── AI-generated summary after each session
├── Captures: topics discussed, emotions expressed, advice given
├── Stored per session, last 30 days retained
└── Purpose: Session-to-session continuity

LONG-TERM MEMORY (Extracted Facts)
├── Permanent user facts extracted by AI
├── Examples: "User has a dog named Max", "Works in marketing", "Struggles with sleep"
├── User can view and delete individual facts
└── Purpose: Deep personalization
```

#### T2 Implementation Spec: Memory System

```swift
// MODELS (T2 to implement)

@Model
final class Message {
    var id: UUID
    var content: String
    var role: MessageRole // .user or .assistant
    var timestamp: Date
    var session: ChatSession?
}

@Model
final class ChatSession {
    var id: UUID
    var startedAt: Date
    var endedAt: Date?
    var summary: String?
    var messages: [Message]
}

@Model
final class UserFact {
    var id: UUID
    var fact: String
    var category: FactCategory // .personal, .health, .goals, .preferences
    var extractedAt: Date
    var source: String // Which session extracted this
}

enum MessageRole: String, Codable {
    case user, assistant, system
}

enum FactCategory: String, Codable {
    case personal, health, goals, preferences, relationships
}

// SERVICES (T2 to implement)

protocol ChatServiceProtocol {
    func sendMessage(_ content: String) async throws -> AsyncStream<String>
    func getCurrentSession() -> ChatSession
    func endSession() async // Triggers summary generation
}

protocol MemoryServiceProtocol {
    func getShortTermContext() -> [Message] // Last 10 messages
    func getMediumTermContext() -> [ChatSession] // Last 5 sessions with summaries
    func getLongTermFacts() -> [UserFact]
    func extractFacts(from session: ChatSession) async // AI extraction
    func deleteFact(_ fact: UserFact)
}
```

#### T1 Implementation Spec: Chat UI

```swift
// T1 INTERFACE CONTRACT

// ChatView expects:
struct ChatViewData {
    let messages: [MessageDisplayData]
    let isTyping: Bool
    let canSend: Bool
}

struct MessageDisplayData: Identifiable {
    let id: UUID
    let content: String
    let isFromUser: Bool
    let timestamp: Date
    let isStreaming: Bool // For partial responses
}

// ChatView provides:
// - Scrollable message list with glass card bubbles
// - User message: Right-aligned, accent color tint
// - AI message: Left-aligned, glass card style
// - Typing indicator: Animated dots in glass bubble
// - Input field: Glass input with send button
// - Safe area handling for keyboard
```

#### AI Personality Guidelines

**Tone**: Warm, supportive, gently curious. Like a wise friend who happens to be a great listener.

**Do**:
- Acknowledge emotions before offering advice
- Ask clarifying questions
- Reference past conversations naturally ("Last time you mentioned...")
- Celebrate progress, no matter how small
- Offer practical, actionable suggestions

**Don't**:
- Diagnose or claim medical authority
- Use clinical/cold language
- Dismiss or minimize feelings
- Be overly cheerful when user is struggling
- Give unsolicited advice

**Example Exchange**:
```
User: I couldn't sleep again last night. Third time this week.

AI: That sounds exhausting - three nights of poor sleep really adds up.
I remember you mentioned work has been stressful lately with the project
deadline. Do you think that might be connected, or does this feel different?
```

---

### 4.2 Apple Health Integration

**Priority:** P0 (Core Feature)

#### Overview

Bi-directional integration with Apple HealthKit to provide data-informed wellness insights. The AI uses health data to contextualize conversations without requiring manual user input.

#### Functional Requirements

| ID | Requirement | Details |
|----|-------------|---------|
| HEALTH-01 | Permission request | Clear, non-scary permission flow on first launch |
| HEALTH-02 | Sleep data read | HKSleepAnalysis - duration, quality, time in bed |
| HEALTH-03 | Activity data read | HKStepCount, HKActiveEnergyBurned |
| HEALTH-04 | Mindfulness data read | HKMindfulSession from other apps |
| HEALTH-05 | Data summary | Daily/weekly aggregations for AI context |
| HEALTH-06 | Privacy-first | Data never leaves device, only summaries sent to AI |

#### HealthKit Data Model

```swift
// T2 IMPLEMENTATION SPEC

// Required HealthKit permissions
enum SerenityHealthPermissions {
    static let readTypes: Set<HKObjectType> = [
        HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
        HKObjectType.quantityType(forIdentifier: .stepCount)!,
        HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
        HKObjectType.categoryType(forIdentifier: .mindfulSession)!
    ]
}

// Aggregated data for AI context (T2 to implement)
struct HealthSummary: Codable {
    let date: Date

    // Sleep
    let sleepDuration: TimeInterval? // In seconds
    let sleepQuality: SleepQuality? // .poor, .fair, .good, .excellent
    let bedtime: Date?
    let wakeTime: Date?

    // Activity
    let stepCount: Int
    let activeCalories: Int
    let activityLevel: ActivityLevel // .sedentary, .light, .moderate, .active

    // Mindfulness
    let mindfulMinutes: Int
    let mindfulSessions: Int
}

enum SleepQuality: String, Codable {
    case poor, fair, good, excellent
}

enum ActivityLevel: String, Codable {
    case sedentary, light, moderate, active
}

// SERVICES (T2 to implement)

protocol HealthServiceProtocol {
    func requestAuthorization() async throws -> Bool
    func isAuthorized() -> Bool
    func getTodaySummary() async throws -> HealthSummary
    func getWeekSummary() async throws -> [HealthSummary]
    func getHealthContextForAI() async -> String // Natural language summary
}
```

#### T1 Implementation Spec: Health Dashboard

```swift
// T1 INTERFACE CONTRACT

// HealthDashboardView expects:
struct HealthDashboardData {
    let today: HealthDisplayData
    let weekTrend: [HealthDisplayData]
    let isAuthorized: Bool
    let lastSynced: Date?
}

struct HealthDisplayData: Identifiable {
    let id: UUID
    let date: Date
    let sleepHours: Double?
    let sleepQualityIcon: String // SF Symbol name
    let steps: Int
    let stepsGoalProgress: Double // 0.0-1.0
    let mindfulMinutes: Int
    let activityRings: ActivityRingsData
}

struct ActivityRingsData {
    let move: Double // 0.0-1.0
    let exercise: Double
    let stand: Double
}

// HealthDashboardView provides:
// - Glassmorphic cards for each metric
// - Sleep: Moon icon with hours and quality indicator
// - Steps: Walking figure with progress ring
// - Mindfulness: Lotus icon with minutes
// - Week trend: Small bar chart in glass container
// - Sync status indicator
```

#### AI Context Injection

When user sends a message, T2's `ChatService` automatically prepends health context:

```
System prompt addition:

[HEALTH CONTEXT - {date}]
Sleep: User slept 5.5 hours last night (below their average of 7 hours).
Went to bed at 1:30 AM, woke at 7:00 AM. Sleep quality: Poor.

Activity: 3,200 steps today (usually 8,000). Sedentary day.

Mindfulness: No mindfulness sessions today. Last session was 3 days ago.

[END HEALTH CONTEXT]

Use this data naturally in conversation. Don't lecture about health unless
directly relevant. Notice patterns and correlations.
```

---

### 4.3 User Profile with Personal Goals

**Priority:** P0 (Core Feature)

#### Overview

User profile storing personal information, wellness goals, and preferences. Goals provide structure and trackable progress. The AI references goals to provide relevant encouragement and check-ins.

#### Functional Requirements

| ID | Requirement | Details |
|----|-------------|---------|
| PROFILE-01 | Basic info | Name (optional), preferred name for AI |
| PROFILE-02 | Goal creation | User creates 1-5 wellness goals |
| PROFILE-03 | Goal tracking | Progress percentage, streak tracking |
| PROFILE-04 | Goal reminders | AI naturally references goals in conversation |
| PROFILE-05 | Settings | Notification preferences, theme (future), data management |
| PROFILE-06 | Data export | User can export their data |
| PROFILE-07 | Data deletion | User can delete all data |

#### Data Models

```swift
// T2 IMPLEMENTATION SPEC

@Model
final class UserProfile {
    var id: UUID
    var preferredName: String?
    var createdAt: Date
    var onboardingCompleted: Bool
    var healthIntegrationEnabled: Bool
    var notificationsEnabled: Bool
    var goals: [WellnessGoal]
    var facts: [UserFact] // From long-term memory
}

@Model
final class WellnessGoal {
    var id: UUID
    var title: String
    var description: String?
    var category: GoalCategory
    var targetValue: Double? // e.g., "7" for 7 hours sleep
    var unit: String? // e.g., "hours"
    var frequency: GoalFrequency
    var currentStreak: Int
    var longestStreak: Int
    var createdAt: Date
    var completions: [GoalCompletion]
}

@Model
final class GoalCompletion {
    var id: UUID
    var date: Date
    var value: Double?
    var note: String?
    var goal: WellnessGoal?
}

enum GoalCategory: String, Codable, CaseIterable {
    case sleep = "Sleep"
    case activity = "Activity"
    case mindfulness = "Mindfulness"
    case stress = "Stress Management"
    case social = "Social Connection"
    case custom = "Custom"

    var icon: String {
        switch self {
        case .sleep: return "moon.fill"
        case .activity: return "figure.walk"
        case .mindfulness: return "brain.head.profile"
        case .stress: return "leaf.fill"
        case .social: return "person.2.fill"
        case .custom: return "star.fill"
        }
    }

    var color: String {
        switch self {
        case .sleep: return "moodCalm"
        case .activity: return "moodExcited"
        case .mindfulness: return "moodReflective"
        case .stress: return "moodCalm"
        case .social: return "moodHappy"
        case .custom: return "primary"
        }
    }
}

enum GoalFrequency: String, Codable {
    case daily, weekly, custom
}

// SERVICES (T2 to implement)

protocol ProfileServiceProtocol {
    func getProfile() -> UserProfile
    func updateProfile(_ profile: UserProfile)
    func createGoal(_ goal: WellnessGoal)
    func updateGoal(_ goal: WellnessGoal)
    func deleteGoal(_ goal: WellnessGoal)
    func logGoalCompletion(_ goal: WellnessGoal, value: Double?, note: String?)
    func getGoalContextForAI() -> String // Natural language summary of goals
}
```

#### T1 Implementation Spec: Profile & Goals UI

```swift
// T1 INTERFACE CONTRACT

// ProfileView expects:
struct ProfileViewData {
    let preferredName: String?
    let memberSince: Date
    let totalSessions: Int
    let currentStreak: Int // Days with at least one conversation
    let goals: [GoalDisplayData]
}

struct GoalDisplayData: Identifiable {
    let id: UUID
    let title: String
    let category: String
    let categoryIcon: String
    let categoryColor: String // AppColors key
    let progress: Double // 0.0-1.0
    let currentStreak: Int
    let frequencyLabel: String // "Daily", "Weekly"
    let lastCompleted: Date?
}

// ProfileView provides:
// - Glass card header with name and stats
// - Goals list with progress rings
// - Add goal button (floating, glass style)
// - Settings navigation

// GoalDetailView expects:
struct GoalDetailViewData {
    let goal: GoalDisplayData
    let completionHistory: [CompletionDisplayData]
    let insights: String? // AI-generated insight about this goal
}

struct CompletionDisplayData: Identifiable {
    let id: UUID
    let date: Date
    let completed: Bool
    let value: Double?
    let note: String?
}

// GoalDetailView provides:
// - Large progress ring with streak
// - Calendar heatmap of completions
// - "Mark Complete" button (prominent, animated glow)
// - History list
// - Delete/Edit actions
```

#### Suggested Default Goals

During onboarding, offer these starter goals:

1. **Sleep 7+ hours** (Sleep, Daily)
2. **Walk 8,000 steps** (Activity, Daily)
3. **5 minutes mindfulness** (Mindfulness, Daily)
4. **Journal once** (Custom, Weekly) - triggers if no chat in 3 days
5. **Digital detox hour** (Stress, Daily)

---

## 5. User Stories

### 5.1 AI Chat User Stories

| ID | As a... | I want to... | So that... | Acceptance Criteria |
|----|---------|--------------|------------|---------------------|
| US-CHAT-01 | User | Send a message and receive an AI response | I can have a conversation | Message sends, typing indicator appears, response streams in <3s |
| US-CHAT-02 | User | See my conversation history | I can reference past discussions | Messages persist across app restarts, scrollable history |
| US-CHAT-03 | User | Have the AI remember previous conversations | I don't have to repeat myself | AI references facts from 2+ sessions ago naturally |
| US-CHAT-04 | User | See when the AI is typing | I know a response is coming | Animated typing indicator during response generation |
| US-CHAT-05 | User | View and delete AI's "memory" of me | I control my data | Memory management screen shows all facts, swipe to delete |
| US-CHAT-06 | User | Continue chatting even offline | I can use the app anywhere | Offline banner, messages queue, sync when online |

### 5.2 Apple Health User Stories

| ID | As a... | I want to... | So that... | Acceptance Criteria |
|----|---------|--------------|------------|---------------------|
| US-HEALTH-01 | User | Grant Health permissions easily | I can connect my data | Clear permission flow, can skip without breaking app |
| US-HEALTH-02 | User | See my health summary at a glance | I understand my current state | Dashboard shows sleep, steps, mindfulness with icons |
| US-HEALTH-03 | User | Have the AI reference my health data | The AI understands my physical state | AI mentions "I see you didn't sleep well" when relevant |
| US-HEALTH-04 | User | Know my data stays on my device | I trust the app with my health data | Privacy indicator, no raw health data sent to API |
| US-HEALTH-05 | User | Disconnect Health at any time | I maintain control | Settings toggle, data stops syncing immediately |

### 5.3 Profile & Goals User Stories

| ID | As a... | I want to... | So that... | Acceptance Criteria |
|----|---------|--------------|------------|---------------------|
| US-GOAL-01 | User | Create a wellness goal | I have something to work toward | Goal creation flow with category, title, frequency |
| US-GOAL-02 | User | Track my goal streak | I stay motivated | Streak counter increments, celebration animation |
| US-GOAL-03 | User | Log goal completion quickly | Tracking is frictionless | One-tap completion, optional note |
| US-GOAL-04 | User | See my goal history | I can reflect on progress | Calendar view with completion markers |
| US-GOAL-05 | User | Have the AI encourage my goals | I feel supported | AI says "Great job on your sleep goal this week!" |
| US-GOAL-06 | User | Delete all my data | I can leave cleanly | Single action deletes SwiftData, shows confirmation |

### 5.4 Onboarding User Stories

| ID | As a... | I want to... | So that... | Acceptance Criteria |
|----|---------|--------------|------------|---------------------|
| US-ONBOARD-01 | New user | Complete onboarding in <2 minutes | I can start chatting quickly | 4 screens max, progress indicator |
| US-ONBOARD-02 | New user | Set my preferred name | The AI addresses me correctly | Optional field, can skip |
| US-ONBOARD-03 | New user | Choose starter goals | I have structure immediately | 3 suggested goals, can skip all |
| US-ONBOARD-04 | New user | Understand data privacy | I trust the app | Clear privacy statement on onboarding |

---

## 6. Success Metrics

### 6.1 North Star Metric

**Weekly Active Conversations (WAC)**: Number of users who have at least 3 meaningful conversations (5+ messages) per week.

*Why this metric*: Indicates genuine engagement, not just downloads or one-time usage.

### 6.2 Primary Metrics

| Metric | Definition | Target (6 months) |
|--------|------------|-------------------|
| D7 Retention | % users active 7 days after install | >40% |
| Session Length | Average conversation duration | >5 minutes |
| Messages per Session | Average messages exchanged | >8 |
| Goal Completion Rate | % of active goals marked complete/week | >60% |
| Health Integration Opt-in | % users granting Health access | >70% |

### 6.3 Secondary Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| Onboarding Completion | % users completing onboarding | >85% |
| Daily Active Users | % of WAU using daily | >50% |
| Memory Engagement | % users viewing/editing memory | >20% |
| Goal Creation | Average goals per user | >2.5 |
| App Store Rating | Average rating | >4.5 |

### 6.4 Health Metrics (Technical)

| Metric | Target |
|--------|--------|
| AI Response Latency (P95) | <3 seconds |
| Message Send Success Rate | >99.5% |
| App Crash Rate | <0.5% |
| Health Sync Success Rate | >98% |

---

## 7. Out of Scope (v1.1+)

### Explicitly NOT in MVP

| Feature | Reason | Planned Version |
|---------|--------|-----------------|
| Push notifications | Requires server infrastructure | v1.1 |
| Apple Watch app | Scope creep, needs separate development | v1.2 |
| Voice input/output | Adds complexity, text-first | v1.2 |
| Social features | Privacy concerns, MVP is personal | v2.0 |
| Therapist handoff | Requires partnerships, compliance | v2.0 |
| Multiple AI personalities | Single personality first, measure engagement | v1.3 |
| Mood tracking UI | Use conversation analysis instead | v1.1 |
| Journaling mode | Chat IS journaling | - |
| Meditation guides | Many competitors, not differentiating | - |
| Gamification/badges | Can feel patronizing for wellness | - |
| Subscription/payments | Free for MVP, monetize after PMF | v1.5 |

### Technical Debt Accepted for MVP

| Item | Mitigation |
|------|------------|
| No backend sync | All data local - user accepts device loss risk |
| Single AI provider | Abstract interface for future provider swap |
| No analytics | Add after privacy-preserving solution found |
| English only | Internationalization hooks in place |

---

## 8. Technical Requirements Summary

### 8.1 Platform & Frameworks

| Component | Technology | Version |
|-----------|------------|---------|
| Platform | iOS | 17.0+ |
| Language | Swift | 5.9+ |
| UI Framework | SwiftUI | Latest |
| Persistence | SwiftData | Latest |
| Health | HealthKit | Latest |
| AI Provider | DeepSeek API | v1 |
| Architecture | MVVM + Services | - |

### 8.2 AI Integration: DeepSeek API

**Why DeepSeek**:
- Cost-effective (~10x cheaper than GPT-4)
- 32K context window (sufficient for memory system)
- Good performance on conversational tasks
- No data training on inputs (privacy)

**API Configuration**:

```swift
// T2 IMPLEMENTATION SPEC

struct DeepSeekConfig {
    static let baseURL = "https://api.deepseek.com/v1"
    static let model = "deepseek-chat"
    static let maxTokens = 1024
    static let temperature = 0.7
    static let contextWindow = 32_000
}

// System prompt structure
struct SerenitySystemPrompt {
    static func build(
        healthContext: String,
        goalContext: String,
        longTermFacts: [UserFact],
        sessionSummaries: [String]
    ) -> String {
        """
        You are Serenity, a warm and supportive AI wellness companion. You provide
        psychological support through empathetic conversation. You remember details
        about the user and reference them naturally.

        PERSONALITY:
        - Warm, supportive, gently curious
        - Acknowledge feelings before offering advice
        - Celebrate small wins
        - Never diagnose or claim medical expertise
        - Use casual, friendly language (not clinical)

        USER CONTEXT:

        [LONG-TERM MEMORY]
        \(longTermFacts.map { "- \($0.fact)" }.joined(separator: "\n"))

        [RECENT SESSIONS]
        \(sessionSummaries.joined(separator: "\n\n"))

        [TODAY'S HEALTH DATA]
        \(healthContext)

        [USER'S GOALS]
        \(goalContext)

        GUIDELINES:
        - Reference the above context naturally, don't list it back
        - If health data shows poor sleep/low activity, gently check in
        - Mention goal progress when relevant
        - Ask follow-up questions to understand better
        - Keep responses concise (2-4 paragraphs max)
        - End with a question or gentle prompt when appropriate
        """
    }
}

// API Service (T2 to implement)
protocol AIServiceProtocol {
    func chat(
        messages: [Message],
        systemPrompt: String
    ) async throws -> AsyncStream<String>

    func summarizeSession(_ session: ChatSession) async throws -> String

    func extractFacts(from text: String) async throws -> [String]
}
```

### 8.3 SwiftData Schema

```swift
// T2 IMPLEMENTATION SPEC - Complete Schema

// All models use @Model macro
// Relationships use inverse references
// Cascade delete configured appropriately

/*
 SCHEMA OVERVIEW:

 UserProfile (1)
 ├── goals: [WellnessGoal] (many)
 │   └── completions: [GoalCompletion] (many)
 ├── facts: [UserFact] (many)
 └── (implicit) sessions via separate query

 ChatSession (many)
 └── messages: [Message] (many)

 HealthSummary (many, daily)
 */

// Configuration
@MainActor
let modelContainer: ModelContainer = {
    let schema = Schema([
        UserProfile.self,
        WellnessGoal.self,
        GoalCompletion.self,
        UserFact.self,
        ChatSession.self,
        Message.self,
        HealthSummary.self
    ])

    let config = ModelConfiguration(
        isStoredInMemoryOnly: false,
        allowsSave: true
    )

    return try! ModelContainer(for: schema, configurations: [config])
}()
```

### 8.4 Design System: Liquid Glass

**Color Palette** (from existing Liquid Glass Guide):

```swift
// Serenity-specific color adjustments
extension AppColors {
    // Wellness-themed accent colors
    static let serenityCalm = Color(red: 0.4, green: 0.7, blue: 0.8)    // Soft teal
    static let serenityWarm = Color(red: 0.9, green: 0.7, blue: 0.5)    // Warm amber
    static let serenityGlow = Color(red: 0.6, green: 0.5, blue: 0.9)    // Soft purple

    // Message bubbles
    static let userBubble = Color(red: 0.3, green: 0.5, blue: 0.8).opacity(0.3)
    static let aiBubble = AppColors.glassWhite
}
```

**Typography**:
- Chat messages: `AppTypography.body`
- User name in header: `AppTypography.title2`
- Goal titles: `AppTypography.headline`
- Health metrics: `AppTypography.title` (numbers) + `AppTypography.caption` (labels)

**Animations**:
- Message appear: `AppAnimation.springStandard`
- Typing indicator: Custom 3-dot bounce (0.6s loop)
- Goal completion: `AppAnimation.springBouncy` + confetti particles
- Health sync: Subtle pulse on refresh

### 8.5 File Structure (T2 to Initialize)

```
Serenity/
├── SerenityApp.swift              # @main entry point
├── Info.plist
├── Assets.xcassets/
│   ├── AppIcon.appiconset/
│   ├── Colors/
│   └── Images/
├── Models/
│   ├── UserProfile.swift
│   ├── WellnessGoal.swift
│   ├── GoalCompletion.swift
│   ├── UserFact.swift
│   ├── ChatSession.swift
│   ├── Message.swift
│   └── HealthSummary.swift
├── Services/
│   ├── AIService.swift
│   ├── ChatService.swift
│   ├── MemoryService.swift
│   ├── HealthService.swift
│   └── ProfileService.swift
├── ViewModels/
│   ├── ChatViewModel.swift
│   ├── HealthViewModel.swift
│   ├── ProfileViewModel.swift
│   └── OnboardingViewModel.swift
├── Views/
│   ├── Chat/
│   │   ├── ChatView.swift
│   │   ├── MessageBubble.swift
│   │   └── TypingIndicator.swift
│   ├── Health/
│   │   ├── HealthDashboardView.swift
│   │   └── HealthMetricCard.swift
│   ├── Profile/
│   │   ├── ProfileView.swift
│   │   ├── GoalListView.swift
│   │   ├── GoalDetailView.swift
│   │   └── GoalCreationView.swift
│   ├── Onboarding/
│   │   └── OnboardingFlow.swift
│   ├── Components/
│   │   └── (Reusable glass components)
│   └── ContentView.swift          # Tab navigation
├── Design/
│   ├── AppColors.swift
│   ├── AppTypography.swift
│   ├── AppSpacing.swift
│   ├── AppRadius.swift
│   ├── AppAnimation.swift
│   └── GlassModifiers.swift
└── Tests/
    ├── ChatServiceTests.swift
    ├── MemoryServiceTests.swift
    ├── HealthServiceTests.swift
    └── ProfileServiceTests.swift
```

---

## Appendix A: API Key Management

For MVP, DeepSeek API key stored in Keychain (not in code or plist):

```swift
// T2 IMPLEMENTATION SPEC

struct APIKeyManager {
    private static let service = "com.serenity.apikey"
    private static let account = "deepseek"

    static func getAPIKey() throws -> String {
        // Read from Keychain
    }

    static func setAPIKey(_ key: String) throws {
        // Write to Keychain
    }
}

// User enters API key in Settings during MVP
// Future: Backend proxy to hide key
```

---

## Appendix B: Privacy & Safety

### Data Privacy

- All user data stored locally via SwiftData
- Health data aggregated before AI context (raw data never sent)
- No analytics/tracking in MVP
- User can export/delete all data

### Content Safety

- AI system prompt includes content boundaries
- No medical advice, diagnosis, or treatment recommendations
- Crisis detection prompts professional resources:

```swift
// T2 IMPLEMENTATION SPEC

struct SafetyFilter {
    static let crisisKeywords = [
        "suicide", "kill myself", "end my life", "don't want to live",
        "hurt myself", "self-harm"
    ]

    static func checkMessage(_ content: String) -> SafetyResult {
        // Returns .safe, .flagged(reason), or .crisis(resources)
    }
}

// Crisis response includes:
// - National Suicide Prevention Lifeline: 988
// - Crisis Text Line: Text HOME to 741741
// - International Association for Suicide Prevention: https://www.iasp.info/resources/Crisis_Centres/
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Feb 2026 | Product | Initial PRD |

---

*This PRD is actionable for T1 (UI) and T2 (Backend) implementation. All interface contracts and data models are implementation-ready.*
