# Product Requirements Document: CounterApp

## Overview

**Product**: CounterApp  
**Version**: 1.0 (MVP)  
**Platform**: iOS (SwiftUI)  
**Architecture**: MVVM  

## Problem Statement

Users need a simple, focused way to count things - whether it's reps at the gym, inventory, or any tally. Existing counter apps are bloated with features.

## Solution

A minimal counter app with one screen, one purpose: count up, count down, reset.

## Target User

- Anyone who needs to count things
- Developers learning SwiftUI + MVVM patterns

## MVP Features

| Feature | Priority | Description |
|---------|----------|-------------|
| Count Display | P0 | Large, centered number showing current count |
| Increment (+) | P0 | Button to add 1 to count |
| Decrement (-) | P0 | Button to subtract 1 from count |
| Reset | P1 | Button to return count to 0 |

## Technical Constraints

- SwiftUI only (no UIKit)
- MVVM architecture
- No persistence (state resets on app close)
- iOS 17+ minimum deployment target
- No third-party dependencies

## User Interface

```
┌─────────────────────┐
│                     │
│                     │
│         42          │  <- Large count display
│                     │
│    [ - ]   [ + ]    │  <- Decrement/Increment buttons
│                     │
│       [Reset]       │  <- Reset button (optional)
│                     │
└─────────────────────┘
```

## Success Metrics

1. App builds without warnings
2. All interactions work correctly
3. Count updates immediately on button press
4. No crashes

## Out of Scope (v1.1+)

- Persistence
- Multiple counters
- Custom increment steps
- Haptic feedback
- Themes
- Share/export
- Widget

## Timeline

Phase 1: Build (T1 UI, T2 Logic) - Parallel  
Phase 2: Integrate (Connect UI to ViewModel)  
Phase 3: Test & Verify  

---

*Document Version: 1.0*  
*Last Updated: 2026-02-02*
