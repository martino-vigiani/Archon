import Testing
import Foundation
@testable import Archon

@Suite("Motion spring conversion")
struct MotionTests {

    @Test("SI → SwiftUI spring conversion (REQ-DSN-055)")
    func springConversion() {
        // Orb idle → listening expand: k=280, c=24.
        let spring = SpringParameters(stiffness: 280, damping: 24)
        // response = 2π / sqrt(280) ≈ 0.37564
        #expect(abs(spring.response - 0.37564) < 0.001)
        // dampingFraction = 24 / (2·sqrt(280)) ≈ 0.7171
        #expect(abs(spring.dampingFraction - 0.7171) < 0.001)
    }

    @Test("each motion event exposes its locked constants")
    func lockedConstants() {
        #expect(MotionEvent.orbExpand.spring.stiffness == 280)
        #expect(MotionEvent.kanbanDragRelease.spring.stiffness == 350)
        #expect(MotionEvent.viewSwitch.spring.damping == 24)
    }

    @Test("reduce motion: drag-release is instant (nil), view switch is a cross-fade")
    func reduceMotionSubstitutions() {
        #expect(MotionEvent.kanbanDragRelease.animation(reduceMotion: true) == nil)
        #expect(MotionEvent.viewSwitch.animation(reduceMotion: true) != nil)
        #expect(MotionEvent.orbExpand.animation(reduceMotion: false) != nil)
    }
}

@Suite("ULID generation")
struct ULIDTests {

    @Test("ULID is 26 Crockford base32 chars")
    func shape() {
        let ulid = ULID.generate()
        #expect(ulid.count == 26)
        let allowed = Set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        #expect(ulid.allSatisfy { allowed.contains($0) })
    }

    @Test("later timestamp sorts lexicographically greater")
    func monotonicByTime() {
        let early = ULID.generate(date: Date(timeIntervalSince1970: 1_000_000))
        let late = ULID.generate(date: Date(timeIntervalSince1970: 2_000_000))
        #expect(late > early)
    }

    @Test("two ULIDs are distinct")
    func distinct() {
        #expect(ULID.generate() != ULID.generate())
    }
}
