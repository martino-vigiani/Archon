import Foundation

/// Pure, testable exponential-backoff-with-jitter policy.
///
/// Used by the WS auto-reconnect (REQ-ARCH-007: start ≤ 500 ms, cap ≤ 15 s)
/// and the orchestrator restart supervisor (Addendum §A4: max 3 attempts,
/// exponential backoff). Delays are computed in seconds so the math is trivial
/// to assert in unit tests.
struct BackoffPolicy: Sendable, Equatable {
    var initialSeconds: Double
    var maxSeconds: Double
    var multiplier: Double
    /// ± fraction of the base delay applied as jitter (0 = none, 0.5 = ±50%).
    var jitterFraction: Double

    init(
        initialSeconds: Double,
        maxSeconds: Double,
        multiplier: Double = 2.0,
        jitterFraction: Double = 0.5
    ) {
        self.initialSeconds = initialSeconds
        self.maxSeconds = maxSeconds
        self.multiplier = multiplier
        self.jitterFraction = jitterFraction
    }

    /// WS stream auto-reconnect (REQ-ARCH-007).
    static let reconnect = BackoffPolicy(
        initialSeconds: 0.5,
        maxSeconds: 15,
        multiplier: 2.0,
        jitterFraction: 0.5
    )

    /// Orchestrator process restart supervision (Addendum §A4).
    static let restart = BackoffPolicy(
        initialSeconds: 1.0,
        maxSeconds: 30,
        multiplier: 2.0,
        jitterFraction: 0.3
    )

    /// API retry-with-backoff for idempotent calls (Addendum §A4).
    static let apiRetry = BackoffPolicy(
        initialSeconds: 0.25,
        maxSeconds: 8,
        multiplier: 2.0,
        jitterFraction: 0.4
    )

    /// Deterministic base delay for a 0-based `attempt`, capped at `maxSeconds`.
    func baseDelaySeconds(forAttempt attempt: Int) -> Double {
        guard attempt > 0 else { return min(initialSeconds, maxSeconds) }
        let raw = initialSeconds * pow(multiplier, Double(attempt))
        return min(raw, maxSeconds)
    }

    /// Base delay with jitter applied. `random` is expected in `0...1`
    /// (injected in tests; `random = 0.5` yields exactly the base delay).
    func delaySeconds(forAttempt attempt: Int, random: Double) -> Double {
        let base = baseDelaySeconds(forAttempt: attempt)
        let clamped = min(max(random, 0), 1)
        let factor = 1 + (clamped * 2 - 1) * jitterFraction   // in [1-j, 1+j]
        return max(0, base * factor)
    }

    /// Convenience using the system RNG.
    func delaySeconds(forAttempt attempt: Int) -> Double {
        delaySeconds(forAttempt: attempt, random: Double.random(in: 0...1))
    }

    /// As a `Duration`, suitable for `Task.sleep(for:)`.
    func duration(forAttempt attempt: Int) -> Duration {
        .seconds(delaySeconds(forAttempt: attempt))
    }
}
