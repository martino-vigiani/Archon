# DeepSeek API Integration Strategy

## Serenity AI Wellness App

This document outlines the complete integration strategy for DeepSeek's LLM API in the Serenity wellness application.

---

## 1. Why DeepSeek

### Cost Effectiveness

| Provider | Input Cost (per 1M tokens) | Output Cost (per 1M tokens) |
|----------|---------------------------|----------------------------|
| DeepSeek | $0.14 | $0.28 |
| OpenAI GPT-4 | $30.00 | $60.00 |
| Anthropic Claude 3 | $15.00 | $75.00 |

**DeepSeek is approximately 100-200x cheaper** than leading alternatives while maintaining strong conversational quality.

### Technical Advantages

- **32K Context Window**: Sufficient for maintaining rich conversation history and user context
- **OpenAI-Compatible API**: Drop-in replacement, easy migration path if needed
- **Strong Conversational Capabilities**: Excellent for empathetic, nuanced wellness conversations
- **Low Latency**: Fast response times suitable for real-time chat experiences
- **Multilingual Support**: Can serve diverse user bases

### Ideal for Wellness Use Case

- Natural, flowing dialogue style
- Good at following complex system prompts
- Maintains consistent persona across conversations
- Handles sensitive topics appropriately

---

## 2. API Setup

### Endpoint Configuration

```
Base URL: https://api.deepseek.com
Chat Endpoint: /chat/completions
```

### Authentication

```http
Authorization: Bearer sk-your-api-key-here
Content-Type: application/json
```

### Model Selection

```
Model ID: deepseek-chat
```

### Request Format (OpenAI-Compatible)

```json
{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": false
}
```

### Response Format

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Response text here..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350
  }
}
```

---

## 3. Request Structure

### Messages Array Format

```swift
struct ChatMessage: Codable {
    let role: String      // "system", "user", or "assistant"
    let content: String
}
```

### Recommended Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `temperature` | 0.7 | Warm, varied responses without being erratic |
| `max_tokens` | 1024 | Sufficient for thoughtful responses |
| `top_p` | 0.95 | Slight diversity in word choice |
| `frequency_penalty` | 0.3 | Reduces repetitive phrases |
| `presence_penalty` | 0.2 | Encourages topic exploration |

### Request Body Construction

```swift
struct ChatRequest: Codable {
    let model: String
    let messages: [ChatMessage]
    let temperature: Double
    let maxTokens: Int
    let topP: Double
    let frequencyPenalty: Double
    let presencePenalty: Double

    enum CodingKeys: String, CodingKey {
        case model, messages, temperature
        case maxTokens = "max_tokens"
        case topP = "top_p"
        case frequencyPenalty = "frequency_penalty"
        case presencePenalty = "presence_penalty"
    }
}
```

---

## 4. System Prompt Template

### Complete System Prompt for Psychological Support

```swift
let systemPrompt = """
You are Serenity, a warm and supportive AI wellness companion. Your purpose is to provide emotional support, encourage healthy coping strategies, and be a compassionate presence for users navigating life's challenges.

## Your Core Qualities

**Warmth & Empathy**
- Respond with genuine care and understanding
- Validate emotions before offering suggestions
- Use warm, conversational language (not clinical terminology)
- Mirror the user's emotional tone appropriately

**Active Listening**
- Acknowledge what the user shares
- Ask thoughtful follow-up questions
- Remember context from earlier in the conversation
- Notice and gently explore emotional undertones

**Supportive Guidance**
- Offer evidence-based coping strategies when appropriate
- Suggest mindfulness, breathing exercises, or journaling prompts
- Celebrate small wins and progress
- Encourage self-compassion

## Communication Style

- Use "I" statements: "I hear that you're feeling..." instead of "You are feeling..."
- Keep responses concise but meaningful (2-4 paragraphs typically)
- Use gentle language: "might," "perhaps," "when you're ready"
- Occasionally use reflective phrases: "It sounds like...", "I'm wondering if..."

## Important Boundaries

**You Are NOT:**
- A replacement for professional mental health care
- Qualified to diagnose conditions
- Able to prescribe treatments or medications
- An emergency service

**When to Redirect:**
If a user expresses:
- Thoughts of self-harm or suicide
- Harm to others
- Severe mental health crisis
- Need for medication advice

Respond with: "I care about you, and what you're sharing sounds really serious. I want to make sure you get the support you deserve. Please consider reaching out to a mental health professional or crisis helpline. In the US, you can text HOME to 741741 for the Crisis Text Line, or call 988 for the Suicide & Crisis Lifeline."

## User Context

{USER_CONTEXT}

## Current Conversation Guidelines

- This is {TIME_OF_DAY}, so adjust your energy and suggestions accordingly
- The user has been using Serenity for {DAYS_ACTIVE} days
- Recent mood trend: {MOOD_TREND}
- Topics to be mindful of: {SENSITIVE_TOPICS}

Remember: You're a supportive friend who happens to know about wellness, not a therapist. Keep it human.
"""
```

### Context Injection Pattern

```swift
func buildSystemPrompt(for user: User, at date: Date) -> String {
    let timeOfDay = getTimeOfDay(from: date)
    let daysActive = user.daysSinceFirstUse
    let moodTrend = user.recentMoodTrend?.description ?? "not yet established"
    let sensitiveTopics = user.sensitiveTopics.joined(separator: ", ")

    let userContext = """
    Name: \(user.preferredName ?? "Friend")
    Goals: \(user.wellnessGoals.joined(separator: ", "))
    Preferred coping strategies: \(user.preferredStrategies.joined(separator: ", "))
    """

    return systemPrompt
        .replacingOccurrences(of: "{USER_CONTEXT}", with: userContext)
        .replacingOccurrences(of: "{TIME_OF_DAY}", with: timeOfDay)
        .replacingOccurrences(of: "{DAYS_ACTIVE}", with: String(daysActive))
        .replacingOccurrences(of: "{MOOD_TREND}", with: moodTrend)
        .replacingOccurrences(of: "{SENSITIVE_TOPICS}", with: sensitiveTopics.isEmpty ? "none identified" : sensitiveTopics)
}
```

### Tone Guidelines

| Situation | Tone | Example |
|-----------|------|---------|
| User shares good news | Celebratory, warm | "That's wonderful! I can feel how proud you are..." |
| User is anxious | Calm, grounding | "I'm here with you. Let's take a breath together..." |
| User is sad | Gentle, validating | "It makes sense that you'd feel that way..." |
| User is angry | Understanding, spacious | "Those feelings are valid. Would you like to talk about what happened?" |
| User is confused | Curious, patient | "Let's explore this together. What stands out to you most?" |

---

## 5. Context Management

### Token Counting Strategy

```swift
/// Approximate token count (4 characters = 1 token for English)
func estimateTokens(_ text: String) -> Int {
    return max(1, text.count / 4)
}

/// More accurate counting for critical operations
func countTokens(_ messages: [ChatMessage]) -> Int {
    // Each message has ~4 tokens overhead for role/formatting
    let overhead = messages.count * 4
    let contentTokens = messages.reduce(0) { $0 + estimateTokens($1.content) }
    return overhead + contentTokens
}
```

### Context Budget Allocation

```
Total Context Window: 32,000 tokens

Allocation:
├── System Prompt:      2,000 tokens (fixed)
├── User Context:       1,000 tokens (dynamic)
├── Conversation History: 26,000 tokens (sliding window)
├── Current Message:    1,000 tokens (user input)
└── Response Buffer:    2,000 tokens (max_tokens)
```

### When to Truncate/Summarize

```swift
struct ContextManager {
    static let maxHistoryTokens = 26_000
    static let summarizeThreshold = 20_000

    func manageContext(messages: [ChatMessage]) -> [ChatMessage] {
        let tokenCount = countTokens(messages)

        if tokenCount < summarizeThreshold {
            return messages
        }

        if tokenCount < maxHistoryTokens {
            // Truncate oldest messages
            return truncateOldest(messages, targetTokens: summarizeThreshold)
        }

        // Summarize older conversation
        return summarizeAndTruncate(messages)
    }

    private func truncateOldest(_ messages: [ChatMessage], targetTokens: Int) -> [ChatMessage] {
        var result = messages
        while countTokens(result) > targetTokens && result.count > 2 {
            // Keep system message (index 0) and most recent messages
            result.remove(at: 1)
        }
        return result
    }

    private func summarizeAndTruncate(_ messages: [ChatMessage]) -> [ChatMessage] {
        // Keep system message
        let systemMessage = messages.first!

        // Get older messages to summarize (keep last 10 exchanges)
        let recentCount = min(20, messages.count - 1)
        let olderMessages = Array(messages[1..<(messages.count - recentCount)])
        let recentMessages = Array(messages.suffix(recentCount))

        // Create summary message
        let summaryContent = "[Previous conversation summary: \(createSummary(olderMessages))]"
        let summaryMessage = ChatMessage(role: "system", content: summaryContent)

        return [systemMessage, summaryMessage] + recentMessages
    }
}
```

### Priority Order for Context Injection

1. **System Prompt** (always first, never truncated)
2. **Safety Information** (crisis resources, boundaries)
3. **User Profile Context** (goals, preferences)
4. **Conversation Summary** (if applicable)
5. **Recent Messages** (last 10-20 exchanges)
6. **Current User Message** (never truncated)

---

## 6. Error Handling

### Rate Limit Handling

```swift
enum DeepSeekError: Error {
    case rateLimited(retryAfter: Int)
    case networkError(underlying: Error)
    case invalidResponse
    case serverError(statusCode: Int)
    case unauthorized
}

struct RateLimitHandler {
    private var lastRequestTime: Date?
    private var requestCount = 0
    private let maxRequestsPerMinute = 60

    mutating func checkRateLimit() async throws {
        let now = Date()

        // Reset counter every minute
        if let lastTime = lastRequestTime,
           now.timeIntervalSince(lastTime) > 60 {
            requestCount = 0
        }

        requestCount += 1
        lastRequestTime = now

        if requestCount > maxRequestsPerMinute {
            throw DeepSeekError.rateLimited(retryAfter: 60)
        }
    }
}
```

### Network Error Recovery

```swift
struct RetryConfiguration {
    let maxAttempts: Int = 3
    let baseDelay: TimeInterval = 1.0
    let maxDelay: TimeInterval = 30.0

    func delay(for attempt: Int) -> TimeInterval {
        let exponentialDelay = baseDelay * pow(2.0, Double(attempt - 1))
        return min(exponentialDelay, maxDelay)
    }
}

func executeWithRetry<T>(
    config: RetryConfiguration = .init(),
    operation: () async throws -> T
) async throws -> T {
    var lastError: Error?

    for attempt in 1...config.maxAttempts {
        do {
            return try await operation()
        } catch let error as DeepSeekError {
            lastError = error

            switch error {
            case .rateLimited(let retryAfter):
                try await Task.sleep(nanoseconds: UInt64(retryAfter) * 1_000_000_000)
            case .networkError:
                let delay = config.delay(for: attempt)
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            case .serverError(let code) where code >= 500:
                let delay = config.delay(for: attempt)
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            default:
                throw error // Don't retry auth errors or invalid responses
            }
        }
    }

    throw lastError ?? DeepSeekError.networkError(underlying: URLError(.unknown))
}
```

### Fallback Responses

```swift
struct FallbackResponses {
    static let networkError = """
    I'm having a little trouble connecting right now. \
    Let's take a moment to breathe together while I try to reconnect. \
    Take a slow, deep breath in... and out. I'll be right back with you.
    """

    static let rateLimited = """
    I want to give you my full attention, and I need just a moment to gather my thoughts. \
    While we wait, maybe check in with yourself - how are you feeling in your body right now?
    """

    static let generalError = """
    Something unexpected happened on my end. \
    I'm still here with you though. Would you like to share what's on your mind again?
    """

    static func get(for error: DeepSeekError) -> String {
        switch error {
        case .rateLimited:
            return rateLimited
        case .networkError:
            return networkError
        default:
            return generalError
        }
    }
}
```

---

## 7. Cost Optimization

### Estimated Costs Per Conversation

```
Assumptions:
- Average system prompt: 800 tokens
- Average user message: 50 tokens
- Average AI response: 200 tokens
- Average conversation: 10 exchanges

Per Conversation Cost:
├── System prompt (sent each time): 800 tokens × 10 = 8,000 input tokens
├── User messages: 50 × 10 = 500 input tokens
├── Context (growing): ~2,500 tokens average
├── AI responses: 200 × 10 = 2,000 output tokens

Total: ~11,000 input + 2,000 output tokens
Cost: ($0.14 × 0.011) + ($0.28 × 0.002) = $0.00154 + $0.00056 = ~$0.002

Estimated cost per conversation: $0.002 (less than 1 cent)
Monthly cost for 1000 daily active users (3 conversations each): ~$180/month
```

### Token Reduction Strategies

#### 1. System Prompt Optimization

```swift
// BAD: Verbose system prompt
let verbosePrompt = """
You are an AI assistant that is designed to help users with their mental wellness...
[500 words of detailed instructions]
"""

// GOOD: Concise system prompt
let concisePrompt = """
You're Serenity, a warm AI wellness companion. Be empathetic, validate feelings, \
suggest coping strategies. Not a therapist - redirect crises to 988.

User: {USER_NAME}, {DAYS_ACTIVE} days active, goals: {GOALS}
"""
```

#### 2. Smart History Management

```swift
struct SmartHistory {
    /// Only include messages that add context
    func compress(_ messages: [ChatMessage]) -> [ChatMessage] {
        return messages.filter { message in
            // Keep all user messages
            if message.role == "user" { return true }

            // Filter out short acknowledgments from assistant
            let content = message.content.lowercased()
            let shortResponses = ["i understand", "that makes sense", "i hear you"]
            return !shortResponses.contains(where: content.hasPrefix)
        }
    }
}
```

#### 3. Batch Context Updates

```swift
/// Update user context only when significantly changed
struct ContextCache {
    private var cachedContext: String?
    private var lastUpdate: Date?

    mutating func getContext(for user: User) -> String {
        let fiveMinutes: TimeInterval = 300

        if let cached = cachedContext,
           let lastUpdate = lastUpdate,
           Date().timeIntervalSince(lastUpdate) < fiveMinutes {
            return cached
        }

        let newContext = buildContext(for: user)
        cachedContext = newContext
        lastUpdate = Date()
        return newContext
    }
}
```

#### 4. Response Length Hints

```swift
// Add to system prompt based on conversation state
func getResponseLengthHint(conversationLength: Int) -> String {
    switch conversationLength {
    case 0...2:
        return "Respond warmly in 2-3 sentences to start building rapport."
    case 3...5:
        return "Keep responses focused, 2-4 sentences."
    default:
        return "Be concise but caring, 1-3 sentences unless depth is needed."
    }
}
```

---

## 8. Swift Implementation

### Service Protocol

```swift
import Foundation

/// Represents a message in the chat conversation
struct ChatMessage: Codable, Identifiable, Equatable {
    let id: UUID
    let role: MessageRole
    let content: String
    let timestamp: Date

    init(id: UUID = UUID(), role: MessageRole, content: String, timestamp: Date = Date()) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
    }

    enum MessageRole: String, Codable {
        case system
        case user
        case assistant
    }
}

/// Response from the AI service
struct AIResponse {
    let message: ChatMessage
    let usage: TokenUsage
}

struct TokenUsage {
    let promptTokens: Int
    let completionTokens: Int
    let totalTokens: Int
}

/// Protocol for AI chat services - allows swapping providers
protocol AIChatService {
    /// Send a message and receive a response
    func sendMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) async throws -> AIResponse

    /// Stream a response for real-time display
    func streamMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) -> AsyncThrowingStream<String, Error>

    /// Check service availability
    func checkHealth() async -> Bool
}

/// User context for personalization
struct UserContext {
    let preferredName: String?
    let daysActive: Int
    let wellnessGoals: [String]
    let preferredStrategies: [String]
    let recentMoodTrend: MoodTrend?
    let sensitiveTopics: [String]
}

enum MoodTrend: String {
    case improving
    case stable
    case declining
    case fluctuating
}
```

### Network Layer Design

```swift
import Foundation

/// DeepSeek API client
actor DeepSeekClient: AIChatService {
    private let apiKey: String
    private let baseURL = URL(string: "https://api.deepseek.com")!
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private var rateLimitHandler = RateLimitHandler()

    init(apiKey: String, session: URLSession = .shared) {
        self.apiKey = apiKey
        self.session = session

        self.encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase

        self.decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - AIChatService Protocol

    func sendMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) async throws -> AIResponse {
        try await rateLimitHandler.checkRateLimit()

        let request = buildRequest(
            message: message,
            history: conversationHistory,
            context: userContext
        )

        return try await executeWithRetry {
            try await self.performRequest(request)
        }
    }

    func streamMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    try await rateLimitHandler.checkRateLimit()

                    var request = buildRequest(
                        message: message,
                        history: conversationHistory,
                        context: userContext,
                        stream: true
                    )

                    let (bytes, response) = try await session.bytes(for: request.urlRequest)

                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        throw DeepSeekError.invalidResponse
                    }

                    for try await line in bytes.lines {
                        if line.hasPrefix("data: "),
                           let chunk = parseStreamChunk(line) {
                            continuation.yield(chunk)
                        }
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func checkHealth() async -> Bool {
        do {
            let url = baseURL.appendingPathComponent("health")
            let (_, response) = try await session.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    // MARK: - Private Methods

    private func buildRequest(
        message: String,
        history: [ChatMessage],
        context: UserContext,
        stream: Bool = false
    ) -> ChatCompletionRequest {
        let systemPrompt = SystemPromptBuilder.build(for: context)

        var messages: [APIMessage] = [
            APIMessage(role: "system", content: systemPrompt)
        ]

        // Add conversation history
        for msg in history {
            messages.append(APIMessage(role: msg.role.rawValue, content: msg.content))
        }

        // Add current message
        messages.append(APIMessage(role: "user", content: message))

        return ChatCompletionRequest(
            model: "deepseek-chat",
            messages: messages,
            temperature: 0.7,
            maxTokens: 1024,
            topP: 0.95,
            frequencyPenalty: 0.3,
            presencePenalty: 0.2,
            stream: stream
        )
    }

    private func performRequest(_ request: ChatCompletionRequest) async throws -> AIResponse {
        var urlRequest = URLRequest(url: baseURL.appendingPathComponent("chat/completions"))
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(request)

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw DeepSeekError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200:
            let apiResponse = try decoder.decode(ChatCompletionResponse.self, from: data)
            return mapResponse(apiResponse)
        case 401:
            throw DeepSeekError.unauthorized
        case 429:
            let retryAfter = httpResponse.value(forHTTPHeaderField: "Retry-After")
                .flatMap(Int.init) ?? 60
            throw DeepSeekError.rateLimited(retryAfter: retryAfter)
        case 500...:
            throw DeepSeekError.serverError(statusCode: httpResponse.statusCode)
        default:
            throw DeepSeekError.invalidResponse
        }
    }

    private func mapResponse(_ apiResponse: ChatCompletionResponse) -> AIResponse {
        let content = apiResponse.choices.first?.message.content ?? ""

        return AIResponse(
            message: ChatMessage(
                role: .assistant,
                content: content
            ),
            usage: TokenUsage(
                promptTokens: apiResponse.usage.promptTokens,
                completionTokens: apiResponse.usage.completionTokens,
                totalTokens: apiResponse.usage.totalTokens
            )
        )
    }

    private func parseStreamChunk(_ line: String) -> String? {
        guard line.hasPrefix("data: ") else { return nil }
        let jsonString = String(line.dropFirst(6))
        guard jsonString != "[DONE]" else { return nil }

        guard let data = jsonString.data(using: .utf8),
              let chunk = try? decoder.decode(StreamChunk.self, from: data),
              let content = chunk.choices.first?.delta.content else {
            return nil
        }

        return content
    }
}

// MARK: - API Models

private struct APIMessage: Codable {
    let role: String
    let content: String
}

private struct ChatCompletionRequest: Codable {
    let model: String
    let messages: [APIMessage]
    let temperature: Double
    let maxTokens: Int
    let topP: Double
    let frequencyPenalty: Double
    let presencePenalty: Double
    let stream: Bool
}

private struct ChatCompletionResponse: Codable {
    let id: String
    let choices: [Choice]
    let usage: Usage

    struct Choice: Codable {
        let message: APIMessage
        let finishReason: String?
    }

    struct Usage: Codable {
        let promptTokens: Int
        let completionTokens: Int
        let totalTokens: Int
    }
}

private struct StreamChunk: Codable {
    let choices: [StreamChoice]

    struct StreamChoice: Codable {
        let delta: Delta
    }

    struct Delta: Codable {
        let content: String?
    }
}
```

### System Prompt Builder

```swift
import Foundation

enum SystemPromptBuilder {
    static func build(for context: UserContext) -> String {
        let userName = context.preferredName ?? "Friend"
        let goals = context.wellnessGoals.isEmpty ? "general wellness" : context.wellnessGoals.joined(separator: ", ")
        let strategies = context.preferredStrategies.isEmpty ? "various approaches" : context.preferredStrategies.joined(separator: ", ")
        let moodTrend = context.recentMoodTrend?.rawValue ?? "not yet established"
        let sensitiveTopics = context.sensitiveTopics.isEmpty ? "none identified" : context.sensitiveTopics.joined(separator: ", ")
        let timeOfDay = getTimeOfDay()

        return """
        You're Serenity, a warm AI wellness companion. Core traits:
        - Empathetic & validating (acknowledge feelings before suggestions)
        - Warm language, not clinical
        - Suggest coping strategies: breathing, mindfulness, journaling
        - Celebrate progress, encourage self-compassion

        Style: "I hear that..." not "You are...", 2-4 paragraphs typically, gentle words (might, perhaps, when ready)

        BOUNDARIES: Not a therapist. Cannot diagnose or prescribe. For crisis (self-harm, suicide), say: "What you're sharing sounds serious. Please reach out to a professional or call 988 (Suicide & Crisis Lifeline)."

        USER: \(userName), \(context.daysActive) days active
        Goals: \(goals)
        Preferred strategies: \(strategies)
        Mood trend: \(moodTrend)
        Sensitive topics: \(sensitiveTopics)
        Time: \(timeOfDay)

        Be a supportive friend who knows wellness, not a therapist. Keep it human.
        """
    }

    private static func getTimeOfDay() -> String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12: return "morning"
        case 12..<17: return "afternoon"
        case 17..<21: return "evening"
        default: return "night"
        }
    }
}
```

### Chat View Model Integration

```swift
import Foundation
import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isLoading = false
    @Published private(set) var error: String?
    @Published var inputText = ""

    private let chatService: AIChatService
    private let contextManager: ContextManager
    private let userContext: UserContext

    init(
        chatService: AIChatService,
        contextManager: ContextManager = ContextManager(),
        userContext: UserContext
    ) {
        self.chatService = chatService
        self.contextManager = contextManager
        self.userContext = userContext
    }

    func sendMessage() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        // Add user message immediately
        let userMessage = ChatMessage(role: .user, content: text)
        messages.append(userMessage)
        inputText = ""
        isLoading = true
        error = nil

        do {
            // Manage context before sending
            let managedHistory = contextManager.manageContext(messages: Array(messages.dropLast()))

            let response = try await chatService.sendMessage(
                text,
                conversationHistory: managedHistory,
                userContext: userContext
            )

            messages.append(response.message)
        } catch let deepSeekError as DeepSeekError {
            let fallbackMessage = ChatMessage(
                role: .assistant,
                content: FallbackResponses.get(for: deepSeekError)
            )
            messages.append(fallbackMessage)
            error = "Connection issue - using offline response"
        } catch {
            let fallbackMessage = ChatMessage(
                role: .assistant,
                content: FallbackResponses.generalError
            )
            messages.append(fallbackMessage)
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func sendMessageWithStreaming() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        let userMessage = ChatMessage(role: .user, content: text)
        messages.append(userMessage)
        inputText = ""
        isLoading = true
        error = nil

        // Add placeholder for streaming response
        var streamingContent = ""
        let streamingMessage = ChatMessage(role: .assistant, content: "")
        messages.append(streamingMessage)
        let streamingIndex = messages.count - 1

        do {
            let managedHistory = contextManager.manageContext(messages: Array(messages.dropLast(2)))

            let stream = chatService.streamMessage(
                text,
                conversationHistory: managedHistory,
                userContext: userContext
            )

            for try await chunk in stream {
                streamingContent += chunk
                messages[streamingIndex] = ChatMessage(
                    id: streamingMessage.id,
                    role: .assistant,
                    content: streamingContent,
                    timestamp: streamingMessage.timestamp
                )
            }
        } catch {
            messages[streamingIndex] = ChatMessage(
                id: streamingMessage.id,
                role: .assistant,
                content: FallbackResponses.generalError,
                timestamp: streamingMessage.timestamp
            )
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}
```

### Dependency Injection Setup

```swift
import Foundation

/// App-wide dependency container
@MainActor
final class AppDependencies {
    static let shared = AppDependencies()

    let chatService: AIChatService

    private init() {
        // Load API key from Keychain or environment
        guard let apiKey = KeychainHelper.load(key: "deepseek_api_key")
              ?? ProcessInfo.processInfo.environment["DEEPSEEK_API_KEY"] else {
            fatalError("DeepSeek API key not configured")
        }

        self.chatService = DeepSeekClient(apiKey: apiKey)
    }
}

// MARK: - Usage in SwiftUI App

@main
struct SerenityApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.chatService, AppDependencies.shared.chatService)
        }
    }
}

// Environment key for dependency injection
private struct ChatServiceKey: EnvironmentKey {
    static let defaultValue: AIChatService = MockChatService()
}

extension EnvironmentValues {
    var chatService: AIChatService {
        get { self[ChatServiceKey.self] }
        set { self[ChatServiceKey.self] = newValue }
    }
}

// Mock for previews and testing
final class MockChatService: AIChatService {
    func sendMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) async throws -> AIResponse {
        try await Task.sleep(nanoseconds: 500_000_000) // Simulate network delay
        return AIResponse(
            message: ChatMessage(
                role: .assistant,
                content: "I hear you. That sounds like it's been weighing on you. Would you like to explore that feeling a bit more?"
            ),
            usage: TokenUsage(promptTokens: 100, completionTokens: 50, totalTokens: 150)
        )
    }

    func streamMessage(
        _ message: String,
        conversationHistory: [ChatMessage],
        userContext: UserContext
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                let response = "I hear you. That sounds meaningful."
                for char in response {
                    try await Task.sleep(nanoseconds: 50_000_000)
                    continuation.yield(String(char))
                }
                continuation.finish()
            }
        }
    }

    func checkHealth() async -> Bool { true }
}
```

---

## Quick Reference

### API Checklist

- [ ] API key stored securely (Keychain, not UserDefaults)
- [ ] Rate limiting implemented
- [ ] Retry logic with exponential backoff
- [ ] Fallback responses for offline/error states
- [ ] Context management for long conversations
- [ ] Token counting for cost tracking
- [ ] Streaming support for better UX

### Key Constants

```swift
enum DeepSeekConstants {
    static let baseURL = "https://api.deepseek.com"
    static let model = "deepseek-chat"
    static let maxContextTokens = 32_000
    static let defaultMaxTokens = 1024
    static let defaultTemperature = 0.7
}
```

### Cost Formula

```
Monthly Cost = (Daily Active Users × Conversations/User × Tokens/Conversation × Price/Token)

Example:
1000 DAU × 3 conv × 13000 tokens × $0.00000021 = ~$8.20/day = ~$246/month
```

---

## Next Steps for T2 Implementation

1. **Create `DeepSeekClient.swift`** - Copy the network layer implementation
2. **Create `ChatService.swift`** - Implement the protocol
3. **Create `SystemPromptBuilder.swift`** - Build dynamic prompts
4. **Create `ContextManager.swift`** - Handle token management
5. **Add to `ChatViewModel.swift`** - Wire up the service
6. **Configure API key storage** - Use Keychain
7. **Add unit tests** - Test error handling and context management
