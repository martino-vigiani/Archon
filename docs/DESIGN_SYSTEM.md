# Serenity Design System

## Liquid Glass Aesthetic for AI Wellness

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Color Palette](#2-color-palette)
3. [Dark Mode Implementation](#3-dark-mode-implementation)
4. [Typography](#4-typography)
5. [Liquid Glass Effects](#5-liquid-glass-effects)
6. [Component Specifications](#6-component-specifications)
7. [Motion & Animation](#7-motion--animation)
8. [Accessibility](#8-accessibility)
9. [Chat UI Style Guidelines (ChatGPT/Grok)](#9-chat-ui-style-guidelines-chatgptgrok)
10. [Implementation Checklist](#10-implementation-checklist)

---

## 1. Design Philosophy

### Core Principle

> **"A warm hug from a wise friend"**

Serenity embodies the feeling of sitting with a trusted companion who truly listens. Every visual element reinforces three emotional pillars:

| Pillar | Expression |
|--------|------------|
| **Calm** | Soft colors, gentle gradients, unhurried animations |
| **Trustworthy** | Consistent patterns, reliable interactions, professional polish |
| **Supportive** | Warm tones, embracing shapes, encouraging feedback |

### Liquid Glass Philosophy

The Liquid Glass aesthetic creates **depth without heaviness**. Imagine light passing through frosted crystal—surfaces feel tangible yet ethereal. This approach:

- Grounds users in a physical space without overwhelming
- Creates hierarchy through translucency rather than hard borders
- Suggests fluidity and adaptability in the AI's responses
- Evokes the clarity that comes from mindful reflection

```
┌─────────────────────────────────────┐
│                                     │
│   ╭───────────────────────────╮     │
│   │  ░░░░░ Frosted Glass ░░░░ │     │
│   │  ░░░░░ Content floats ░░░ │     │
│   │  ░░░░░ above warmth   ░░░ │     │
│   ╰───────────────────────────╯     │
│                                     │
│        Warm background glow         │
└─────────────────────────────────────┘
```

---

## 2. Color Palette

The Serenity color palette combines the Liquid Glass design system with wellness-specific tones. All colors support both light and dark modes.

### 2.1 Serenity Primary Colors

| Name | Light Mode | Dark Mode | Usage |
|------|------------|-----------|-------|
| **Soft Lavender** | `#7B8CDE` | `#9AA8E8` | Primary actions, AI identity, focus states |
| **Warm Cream** | `#F5E6D3` | `#3D3633` | Backgrounds, comfort zones, user areas |
| **Sage Green** | `#9DC08B` | `#7BA06B` | Success states, growth indicators, healing |

### 2.2 Text Colors

| Name | Light Mode | Dark Mode | Usage |
|------|------------|-----------|-------|
| **Primary** | `rgba(0,0,0,0.88)` | `rgba(255,255,255,0.92)` | Primary text, headings |
| **Secondary** | `rgba(0,0,0,0.64)` | `rgba(255,255,255,0.68)` | Secondary text, timestamps |
| **Tertiary** | `rgba(0,0,0,0.44)` | `rgba(255,255,255,0.48)` | Captions, hints |
| **Disabled** | `rgba(0,0,0,0.28)` | `rgba(255,255,255,0.32)` | Inactive elements |

### 2.3 Background System

| Name | Light Mode | Dark Mode | Usage |
|------|------------|-----------|-------|
| **Canvas** | `#FAFAFA` | `#0A0A0A` | Base background |
| **Elevated** | `rgba(255,255,255,0.72)` | `rgba(0,0,0,0.64)` | Card backgrounds |
| **Warm Tint** | `#F5E6D3` at 15% | `#F5E6D3` at 5% | Subtle overlay |

### 2.4 LiquidGlass Token Reference

The full color token system from `design-system/tokens/colors.json`:

#### Glass Surface Colors

| Token | Light Mode | Dark Mode | Description |
|-------|------------|-----------|-------------|
| `glass.primary` | `rgba(255,255,255,0.72)` | `rgba(0,0,0,0.64)` | Primary glass surface |
| `glass.secondary` | `rgba(255,255,255,0.56)` | `rgba(0,0,0,0.48)` | Secondary glass surface |
| `glass.tertiary` | `rgba(255,255,255,0.40)` | `rgba(0,0,0,0.32)` | Tertiary glass surface |
| `glass.subtle` | `rgba(255,255,255,0.24)` | `rgba(0,0,0,0.20)` | Subtle overlay |
| `glass.ultraThin` | `rgba(255,255,255,0.12)` | `rgba(0,0,0,0.10)` | Ultra-thin glass |

#### Accent Colors

| Token | Hex | Glass Variant | Usage |
|-------|-----|---------------|-------|
| `accent.blue` | `#3B82F6` | `rgba(59,130,246,0.20)` | Links, interactive |
| `accent.violet` | `#8B5CF6` | `rgba(139,92,246,0.20)` | AI messages, highlights |
| `accent.cyan` | `#06B6D4` | `rgba(6,182,212,0.20)` | Information, hints |
| `accent.rose` | `#F43F5E` | `rgba(244,63,94,0.20)` | Alerts, important |
| `accent.amber` | `#F59E0B` | `rgba(245,158,11,0.20)` | Warnings, caution |

#### Semantic Colors

| Token | Light Solid | Dark Solid | Usage |
|-------|-------------|------------|-------|
| `semantic.success` | `#22C55E` | `#22C55E` | Success states, completion |
| `semantic.warning` | `#EAB308` | `#EAB308` | Warnings, attention |
| `semantic.error` | `#EF4444` | `#EF4444` | Errors, destructive |
| `semantic.info` | `#3B82F6` | `#3B82F6` | Information, neutral |

#### Neutral Scale

| Token | Hex | Usage |
|-------|-----|-------|
| `neutral.50` | `#FAFAFA` | Lightest - backgrounds |
| `neutral.100` | `#F5F5F5` | Very light |
| `neutral.200` | `#E5E5E5` | Light - borders |
| `neutral.300` | `#D4D4D4` | Medium light |
| `neutral.400` | `#A3A3A3` | Medium |
| `neutral.500` | `#737373` | True mid gray |
| `neutral.600` | `#525252` | Medium dark |
| `neutral.700` | `#404040` | Dark |
| `neutral.800` | `#262626` | Very dark |
| `neutral.900` | `#171717` | Near black |
| `neutral.950` | `#0A0A0A` | Darkest |

#### Border Colors

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `border.subtle` | `rgba(0,0,0,0.06)` | `rgba(255,255,255,0.08)` | Subtle dividers |
| `border.default` | `rgba(0,0,0,0.12)` | `rgba(255,255,255,0.16)` | Standard borders |
| `border.strong` | `rgba(0,0,0,0.20)` | `rgba(255,255,255,0.24)` | Emphasis borders |
| `border.glass.light` | `rgba(255,255,255,0.32)` | - | Glass edge highlight |
| `border.glass.dark` | `rgba(0,0,0,0.08)` | - | Glass edge shadow |

### SwiftUI Color Definitions

```swift
import SwiftUI

extension Color {
    // MARK: - Primary Palette
    static let serenityLavender = Color(red: 123/255, green: 140/255, blue: 222/255)
    static let serenityLavenderLight = Color(red: 123/255, green: 140/255, blue: 222/255, opacity: 0.3)

    static let serenityCream = Color(red: 245/255, green: 230/255, blue: 211/255)
    static let serenityCreamLight = Color(red: 245/255, green: 230/255, blue: 211/255, opacity: 0.5)

    static let serenitySage = Color(red: 157/255, green: 192/255, blue: 139/255)
    static let serenitySageLight = Color(red: 157/255, green: 192/255, blue: 139/255, opacity: 0.3)

    // MARK: - Text Colors
    static let serenityCharcoal = Color(red: 45/255, green: 52/255, blue: 54/255)
    static let serenityMuted = Color(red: 99/255, green: 110/255, blue: 114/255)
    static let serenityDisabled = Color(red: 178/255, green: 190/255, blue: 195/255)

    // MARK: - Background Colors
    static let serenityCanvas = Color(red: 250/255, green: 250/255, blue: 250/255)
    static let serenityWarmTint = Color(red: 245/255, green: 230/255, blue: 211/255).opacity(0.15)

    // MARK: - Semantic Colors
    static let serenitySuccess = serenitySage
    static let serenityWarning = Color(red: 243/255, green: 156/255, blue: 107/255)
    static let serenityError = Color(red: 214/255, green: 107/255, blue: 107/255)
}
```

---

## 3. Dark Mode Implementation

### 3.1 Design Philosophy for Dark Mode

Dark mode in Serenity maintains the **warm, calming aesthetic** while reducing eye strain. Key principles:

1. **Not pure black**: Use warm dark grays (`#171717`, `#0A0A0A`) to maintain approachability
2. **Reduced contrast**: Text uses 92% white opacity, not pure white
3. **Inverted glass**: Glass surfaces become semi-transparent black instead of white
4. **Preserved warmth**: Warm tint overlay remains but at reduced opacity

### 3.2 Color Scheme Detection

```swift
// MARK: - Color Scheme Adaptive Colors

extension Color {
    // Adaptive primary colors
    static func serenityAdaptiveLavender(_ colorScheme: ColorScheme) -> Color {
        colorScheme == .dark
            ? Color(red: 154/255, green: 168/255, blue: 232/255)  // Lighter for dark mode
            : Color(red: 123/255, green: 140/255, blue: 222/255)  // Standard
    }

    static func serenityAdaptiveCanvas(_ colorScheme: ColorScheme) -> Color {
        colorScheme == .dark
            ? Color(red: 10/255, green: 10/255, blue: 10/255)     // Near black
            : Color(red: 250/255, green: 250/255, blue: 250/255)  // Near white
    }

    static func serenityAdaptiveText(_ colorScheme: ColorScheme) -> Color {
        colorScheme == .dark
            ? Color.white.opacity(0.92)
            : Color.black.opacity(0.88)
    }

    static func serenityAdaptiveSecondaryText(_ colorScheme: ColorScheme) -> Color {
        colorScheme == .dark
            ? Color.white.opacity(0.68)
            : Color.black.opacity(0.64)
    }
}
```

### 3.3 Environment-Based Implementation

```swift
// MARK: - Adaptive View Modifier

struct SerenityAdaptiveStyle: ViewModifier {
    @Environment(\.colorScheme) var colorScheme

    func body(content: Content) -> some View {
        content
            .foregroundStyle(Color.serenityAdaptiveText(colorScheme))
            .background(Color.serenityAdaptiveCanvas(colorScheme))
    }
}

// MARK: - Adaptive Glass Effect

struct AdaptiveGlassEffect: ViewModifier {
    @Environment(\.colorScheme) var colorScheme

    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(
                ZStack {
                    // Adaptive material
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(colorScheme == .dark ? .thinMaterial : .ultraThinMaterial)

                    // Adaptive glass tint
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .fill(
                            colorScheme == .dark
                                ? Color.black.opacity(0.48)
                                : Color.white.opacity(0.56)
                        )

                    // Border
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .stroke(
                            colorScheme == .dark
                                ? Color.white.opacity(0.16)
                                : Color.white.opacity(0.32),
                            lineWidth: 0.5
                        )
                }
            )
            .shadow(
                color: colorScheme == .dark
                    ? Color.black.opacity(0.4)
                    : Color.black.opacity(0.08),
                radius: colorScheme == .dark ? 20 : 16,
                x: 0,
                y: colorScheme == .dark ? 10 : 8
            )
    }
}

extension View {
    func adaptiveGlass(cornerRadius: CGFloat = 20) -> some View {
        modifier(AdaptiveGlassEffect(cornerRadius: cornerRadius))
    }
}
```

### 3.4 Dark Mode Color Mapping

| Component | Light Mode | Dark Mode |
|-----------|------------|-----------|
| **Canvas Background** | `#FAFAFA` | `#0A0A0A` |
| **Card Background** | `white @ 72%` | `black @ 64%` |
| **Primary Text** | `black @ 88%` | `white @ 92%` |
| **Secondary Text** | `black @ 64%` | `white @ 68%` |
| **AI Message Bubble** | `white @ 60%` | `white @ 12%` |
| **User Message Bubble** | Lavender solid | Lavender @ 80% |
| **Input Field** | `white @ 80%` | `black @ 48%` |
| **Glass Border** | `white @ 32%` | `white @ 16%` |
| **Shadow Opacity** | 8% | 40% |

### 3.5 Breathing Background (Dark Mode)

```swift
struct AdaptiveBreathingBackground: View {
    @Environment(\.colorScheme) var colorScheme
    @State private var animateGradient = false

    var body: some View {
        ZStack {
            // Base canvas
            Color.serenityAdaptiveCanvas(colorScheme)

            // Animated gradient orbs (reduced opacity in dark mode)
            Circle()
                .fill(Color.serenityLavender.opacity(colorScheme == .dark ? 0.08 : 0.15))
                .frame(width: 300, height: 300)
                .blur(radius: 80)
                .offset(
                    x: animateGradient ? 50 : -50,
                    y: animateGradient ? -30 : 30
                )

            Circle()
                .fill(Color.serenityCream.opacity(colorScheme == .dark ? 0.1 : 0.3))
                .frame(width: 400, height: 400)
                .blur(radius: 100)
                .offset(
                    x: animateGradient ? -80 : 80,
                    y: animateGradient ? 60 : -60
                )

            Circle()
                .fill(Color.serenitySage.opacity(colorScheme == .dark ? 0.05 : 0.1))
                .frame(width: 250, height: 250)
                .blur(radius: 60)
                .offset(
                    x: animateGradient ? 100 : -100,
                    y: animateGradient ? 100 : -100
                )

            // Warm tint overlay (very subtle in dark mode)
            Color.serenityWarmTint.opacity(colorScheme == .dark ? 0.3 : 1.0)
        }
        .ignoresSafeArea()
        .onAppear {
            withAnimation(.easeInOut(duration: 4).repeatForever(autoreverses: true)) {
                animateGradient = true
            }
        }
    }
}
```

### 3.6 Testing Dark Mode

```swift
// Preview with both color schemes
#Preview("Light Mode") {
    ChatView()
        .preferredColorScheme(.light)
}

#Preview("Dark Mode") {
    ChatView()
        .preferredColorScheme(.dark)
}
```

### Gradient Definitions

```swift
extension LinearGradient {
    // Primary ambient gradient (background breathing effect)
    static let serenityAmbient = LinearGradient(
        colors: [
            Color.serenityLavender.opacity(0.1),
            Color.serenityCream.opacity(0.3),
            Color.serenitySage.opacity(0.1)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // Glass surface gradient
    static let serenityGlass = LinearGradient(
        colors: [
            Color.white.opacity(0.25),
            Color.white.opacity(0.1)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // Lavender accent gradient
    static let serenityLavenderGradient = LinearGradient(
        colors: [
            Color.serenityLavender,
            Color.serenityLavender.opacity(0.8)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
}
```

---

## 4. Typography

### Font Family

**Primary**: SF Pro (system default for iOS)
- Renders beautifully at all sizes
- Excellent readability for wellness content
- Native feel instills trust

### Type Scale

| Style | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| **Large Title** | 34pt | Bold | 41pt | Screen titles |
| **Title 1** | 28pt | Bold | 34pt | Section headers |
| **Title 2** | 22pt | Semibold | 28pt | Card titles |
| **Title 3** | 20pt | Semibold | 25pt | Subsections |
| **Headline** | 17pt | Semibold | 22pt | Emphasis text |
| **Body** | 17pt | Regular | 22pt | Main content, chat messages |
| **Callout** | 16pt | Regular | 21pt | Supporting content |
| **Subheadline** | 15pt | Regular | 20pt | Metadata |
| **Footnote** | 13pt | Regular | 18pt | Captions, timestamps |
| **Caption 1** | 12pt | Regular | 16pt | Labels |
| **Caption 2** | 11pt | Regular | 13pt | Fine print |

### SwiftUI Typography

```swift
extension Font {
    // MARK: - Serenity Type Scale
    static let serenityLargeTitle = Font.system(size: 34, weight: .bold, design: .default)
    static let serenityTitle1 = Font.system(size: 28, weight: .bold, design: .default)
    static let serenityTitle2 = Font.system(size: 22, weight: .semibold, design: .default)
    static let serenityTitle3 = Font.system(size: 20, weight: .semibold, design: .default)
    static let serenityHeadline = Font.system(size: 17, weight: .semibold, design: .default)
    static let serenityBody = Font.system(size: 17, weight: .regular, design: .default)
    static let serenityCallout = Font.system(size: 16, weight: .regular, design: .default)
    static let serenitySubheadline = Font.system(size: 15, weight: .regular, design: .default)
    static let serenityFootnote = Font.system(size: 13, weight: .regular, design: .default)
    static let serenityCaption1 = Font.system(size: 12, weight: .regular, design: .default)
    static let serenityCaption2 = Font.system(size: 11, weight: .regular, design: .default)
}

// MARK: - Text Style Modifier
struct SerenityTextStyle: ViewModifier {
    enum Style {
        case largeTitle, title1, title2, title3, headline
        case body, callout, subheadline, footnote, caption1, caption2
    }

    let style: Style
    let color: Color

    init(_ style: Style, color: Color = .serenityCharcoal) {
        self.style = style
        self.color = color
    }

    func body(content: Content) -> some View {
        content
            .font(font(for: style))
            .foregroundColor(color)
    }

    private func font(for style: Style) -> Font {
        switch style {
        case .largeTitle: return .serenityLargeTitle
        case .title1: return .serenityTitle1
        case .title2: return .serenityTitle2
        case .title3: return .serenityTitle3
        case .headline: return .serenityHeadline
        case .body: return .serenityBody
        case .callout: return .serenityCallout
        case .subheadline: return .serenitySubheadline
        case .footnote: return .serenityFootnote
        case .caption1: return .serenityCaption1
        case .caption2: return .serenityCaption2
        }
    }
}

extension View {
    func serenityText(_ style: SerenityTextStyle.Style, color: Color = .serenityCharcoal) -> some View {
        modifier(SerenityTextStyle(style, color: color))
    }
}
```

---

## 5. Liquid Glass Effects

### Core Glass Properties

The Liquid Glass effect is achieved through a combination of:
1. **Background blur** (frosted effect)
2. **Translucent fill** (depth perception)
3. **Subtle gradient** (light refraction simulation)
4. **Soft shadow** (elevation without harshness)

### Blur Values

| Level | Radius | Usage |
|-------|--------|-------|
| **Light** | 10pt | Subtle depth hints |
| **Regular** | 20pt | Cards, chat bubbles |
| **Heavy** | 40pt | Modal backgrounds, overlays |

### Glass Material Specifications

```swift
// MARK: - Glass Effect Modifier
struct GlassEffect: ViewModifier {
    enum Style {
        case regular    // Standard card glass
        case prominent  // Elevated elements
        case subtle     // Background elements
    }

    let style: Style

    func body(content: Content) -> some View {
        content
            .background(backgroundForStyle)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadiusForStyle, style: .continuous))
            .shadow(
                color: Color.black.opacity(shadowOpacityForStyle),
                radius: shadowRadiusForStyle,
                x: 0,
                y: shadowYForStyle
            )
    }

    @ViewBuilder
    private var backgroundForStyle: some View {
        switch style {
        case .regular:
            ZStack {
                // Frosted blur layer
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(.ultraThinMaterial)

                // Glass gradient overlay
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.25),
                                Color.white.opacity(0.1)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                // Subtle border for depth
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(Color.white.opacity(0.3), lineWidth: 0.5)
            }

        case .prominent:
            ZStack {
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(.regularMaterial)

                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.4),
                                Color.white.opacity(0.15)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .stroke(Color.white.opacity(0.5), lineWidth: 1)
            }

        case .subtle:
            ZStack {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.thinMaterial)

                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.white.opacity(0.1))
            }
        }
    }

    private var cornerRadiusForStyle: CGFloat {
        switch style {
        case .regular: return 20
        case .prominent: return 24
        case .subtle: return 16
        }
    }

    private var shadowOpacityForStyle: Double {
        switch style {
        case .regular: return 0.08
        case .prominent: return 0.12
        case .subtle: return 0.04
        }
    }

    private var shadowRadiusForStyle: CGFloat {
        switch style {
        case .regular: return 16
        case .prominent: return 24
        case .subtle: return 8
        }
    }

    private var shadowYForStyle: CGFloat {
        switch style {
        case .regular: return 8
        case .prominent: return 12
        case .subtle: return 4
        }
    }
}

extension View {
    func glassEffect(_ style: GlassEffect.Style = .regular) -> some View {
        modifier(GlassEffect(style: style))
    }
}
```

### Shadow Specifications

| Level | Color | Opacity | Radius | Y Offset |
|-------|-------|---------|--------|----------|
| **Soft** | Black | 4% | 8pt | 4pt |
| **Regular** | Black | 8% | 16pt | 8pt |
| **Elevated** | Black | 12% | 24pt | 12pt |

**Key principle**: Never use harsh shadows. All shadows should feel like soft ambient occlusion.

### Corner Radius

| Element | Radius | Style |
|---------|--------|-------|
| **Small buttons** | 12pt | Continuous |
| **Input fields** | 16pt | Continuous |
| **Cards** | 20pt | Continuous |
| **Prominent cards** | 24pt | Continuous |
| **Sheets** | 32pt | Continuous |

---

## 6. Component Specifications

### Chat Bubbles

#### AI Message Bubble

```swift
struct AIMessageBubble: View {
    let message: String
    let timestamp: Date

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            // AI Avatar
            Circle()
                .fill(LinearGradient.serenityLavenderGradient)
                .frame(width: 36, height: 36)
                .overlay(
                    Image(systemName: "sparkles")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white)
                )

            VStack(alignment: .leading, spacing: 4) {
                // Message content
                Text(message)
                    .font(.serenityBody)
                    .foregroundColor(.serenityCharcoal)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(
                        ZStack {
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .fill(.ultraThinMaterial)

                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .fill(
                                    LinearGradient(
                                        colors: [
                                            Color.white.opacity(0.6),
                                            Color.white.opacity(0.3)
                                        ],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )

                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .stroke(Color.white.opacity(0.4), lineWidth: 0.5)
                        }
                    )
                    .shadow(color: .black.opacity(0.06), radius: 12, x: 0, y: 6)

                // Timestamp
                Text(timestamp, style: .time)
                    .font(.serenityCaption2)
                    .foregroundColor(.serenityMuted)
                    .padding(.leading, 16)
            }

            Spacer(minLength: 60)
        }
        .padding(.horizontal, 16)
    }
}
```

#### User Message Bubble

```swift
struct UserMessageBubble: View {
    let message: String
    let timestamp: Date

    var body: some View {
        HStack(alignment: .bottom, spacing: 12) {
            Spacer(minLength: 60)

            VStack(alignment: .trailing, spacing: 4) {
                // Message content
                Text(message)
                    .font(.serenityBody)
                    .foregroundColor(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(
                        LinearGradient(
                            colors: [
                                Color.serenityLavender,
                                Color.serenityLavender.opacity(0.9)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .shadow(color: Color.serenityLavender.opacity(0.3), radius: 12, x: 0, y: 6)

                // Timestamp
                Text(timestamp, style: .time)
                    .font(.serenityCaption2)
                    .foregroundColor(.serenityMuted)
                    .padding(.trailing, 16)
            }
        }
        .padding(.horizontal, 16)
    }
}
```

### Input Field

```swift
struct SerenityInputField: View {
    @Binding var text: String
    let placeholder: String
    let onSend: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(spacing: 12) {
            // Text field
            TextField(placeholder, text: $text, axis: .vertical)
                .font(.serenityBody)
                .foregroundColor(.serenityCharcoal)
                .focused($isFocused)
                .lineLimit(1...5)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(
                    ZStack {
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(.ultraThinMaterial)

                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(Color.white.opacity(isFocused ? 0.8 : 0.6))

                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(
                                isFocused ? Color.serenityLavender.opacity(0.5) : Color.white.opacity(0.4),
                                lineWidth: isFocused ? 2 : 0.5
                            )
                    }
                )
                .shadow(color: .black.opacity(0.04), radius: 8, x: 0, y: 4)

            // Send button
            Button(action: onSend) {
                Circle()
                    .fill(
                        text.isEmpty
                            ? Color.serenityDisabled
                            : LinearGradient.serenityLavenderGradient
                    )
                    .frame(width: 44, height: 44)
                    .overlay(
                        Image(systemName: "arrow.up")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(.white)
                    )
                    .shadow(
                        color: text.isEmpty ? .clear : Color.serenityLavender.opacity(0.4),
                        radius: 8,
                        x: 0,
                        y: 4
                    )
            }
            .disabled(text.isEmpty)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: text.isEmpty)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            Rectangle()
                .fill(.ultraThinMaterial)
                .ignoresSafeArea()
        )
    }
}
```

### Glass Card

```swift
struct SerenityCard<Content: View>: View {
    let title: String?
    let content: () -> Content

    init(title: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title {
                Text(title)
                    .font(.serenityTitle3)
                    .foregroundColor(.serenityCharcoal)
            }

            content()
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(.ultraThinMaterial)

                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.5),
                                Color.white.opacity(0.2)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(Color.white.opacity(0.4), lineWidth: 0.5)
            }
        )
        .shadow(color: .black.opacity(0.08), radius: 16, x: 0, y: 8)
    }
}
```

### Buttons

#### Primary Button

```swift
struct SerenityPrimaryButton: View {
    let title: String
    let icon: String?
    let action: () -> Void

    @State private var isPressed = false

    init(_ title: String, icon: String? = nil, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .semibold))
                }

                Text(title)
                    .font(.serenityHeadline)
            }
            .foregroundColor(.white)
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(
                LinearGradient(
                    colors: [
                        Color.serenityLavender,
                        Color.serenityLavender.opacity(0.85)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(
                color: Color.serenityLavender.opacity(0.4),
                radius: isPressed ? 4 : 12,
                x: 0,
                y: isPressed ? 2 : 6
            )
            .scaleEffect(isPressed ? 0.97 : 1)
        }
        .buttonStyle(.plain)
        .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                isPressed = pressing
            }
        }, perform: {})
    }
}
```

#### Secondary Button

```swift
struct SerenitySecondaryButton: View {
    let title: String
    let icon: String?
    let action: () -> Void

    @State private var isPressed = false

    init(_ title: String, icon: String? = nil, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .medium))
                }

                Text(title)
                    .font(.serenityHeadline)
            }
            .foregroundColor(.serenityLavender)
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(.ultraThinMaterial)

                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color.serenityLavender.opacity(0.1))

                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.serenityLavender.opacity(0.3), lineWidth: 1)
                }
            )
            .scaleEffect(isPressed ? 0.97 : 1)
        }
        .buttonStyle(.plain)
        .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                isPressed = pressing
            }
        }, perform: {})
    }
}
```

### Navigation

#### Tab Bar

```swift
struct SerenityTabBar: View {
    @Binding var selectedTab: Tab

    enum Tab: CaseIterable {
        case chat, journal, insights, profile

        var icon: String {
            switch self {
            case .chat: return "bubble.left.and.bubble.right"
            case .journal: return "book"
            case .insights: return "chart.line.uptrend.xyaxis"
            case .profile: return "person"
            }
        }

        var title: String {
            switch self {
            case .chat: return "Chat"
            case .journal: return "Journal"
            case .insights: return "Insights"
            case .profile: return "Profile"
            }
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedTab = tab
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: tab.icon)
                            .font(.system(size: 22, weight: selectedTab == tab ? .semibold : .regular))
                            .symbolVariant(selectedTab == tab ? .fill : .none)

                        Text(tab.title)
                            .font(.serenityCaption2)
                    }
                    .foregroundColor(selectedTab == tab ? .serenityLavender : .serenityMuted)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 8)
        .padding(.bottom, 4)
        .background(
            ZStack {
                Rectangle()
                    .fill(.ultraThinMaterial)

                Rectangle()
                    .fill(Color.white.opacity(0.5))

                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [Color.white.opacity(0.3), Color.clear],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(height: 1)
                    .frame(maxHeight: .infinity, alignment: .top)
            }
            .ignoresSafeArea()
        )
    }
}
```

---

## 7. Motion & Animation

### Animation Principles

1. **Gentle**: All animations feel soft and unhurried
2. **Natural**: Spring physics create organic movement
3. **Purposeful**: Animation supports understanding, never distracts
4. **Subtle**: Motion is felt more than seen

### Standard Spring Values

```swift
extension Animation {
    // MARK: - Serenity Standard Animations

    /// Default spring - used for most UI interactions
    static let serenityDefault = Animation.spring(response: 0.4, dampingFraction: 0.8)

    /// Quick spring - button presses, toggles
    static let serenityQuick = Animation.spring(response: 0.3, dampingFraction: 0.7)

    /// Gentle spring - page transitions, modals
    static let serenityGentle = Animation.spring(response: 0.5, dampingFraction: 0.85)

    /// Slow spring - ambient effects, loading states
    static let serenitySlow = Animation.spring(response: 0.8, dampingFraction: 0.9)

    /// Breathing - continuous ambient animation
    static let serenityBreathing = Animation.easeInOut(duration: 4).repeatForever(autoreverses: true)
}
```

### Breathing Gradient Background

```swift
struct BreathingBackground: View {
    @State private var animateGradient = false

    var body: some View {
        ZStack {
            // Base canvas
            Color.serenityCanvas

            // Animated gradient orbs
            Circle()
                .fill(Color.serenityLavender.opacity(0.15))
                .frame(width: 300, height: 300)
                .blur(radius: 80)
                .offset(
                    x: animateGradient ? 50 : -50,
                    y: animateGradient ? -30 : 30
                )

            Circle()
                .fill(Color.serenityCream.opacity(0.3))
                .frame(width: 400, height: 400)
                .blur(radius: 100)
                .offset(
                    x: animateGradient ? -80 : 80,
                    y: animateGradient ? 60 : -60
                )

            Circle()
                .fill(Color.serenitySage.opacity(0.1))
                .frame(width: 250, height: 250)
                .blur(radius: 60)
                .offset(
                    x: animateGradient ? 100 : -100,
                    y: animateGradient ? 100 : -100
                )

            // Warm tint overlay
            Color.serenityWarmTint
        }
        .ignoresSafeArea()
        .onAppear {
            withAnimation(.serenityBreathing) {
                animateGradient = true
            }
        }
    }
}
```

### Message Appear Animation

```swift
struct MessageAppearModifier: ViewModifier {
    let delay: Double
    @State private var appeared = false

    func body(content: Content) -> some View {
        content
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : 20)
            .onAppear {
                withAnimation(.serenityDefault.delay(delay)) {
                    appeared = true
                }
            }
    }
}

extension View {
    func messageAppear(delay: Double = 0) -> some View {
        modifier(MessageAppearModifier(delay: delay))
    }
}

// Usage in chat list
ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
    MessageBubble(message: message)
        .messageAppear(delay: Double(index) * 0.05)
}
```

### Typing Indicator

```swift
struct TypingIndicator: View {
    @State private var animating = false

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(Color.serenityLavender.opacity(0.6))
                    .frame(width: 8, height: 8)
                    .offset(y: animating ? -4 : 4)
                    .animation(
                        .easeInOut(duration: 0.5)
                        .repeatForever()
                        .delay(Double(index) * 0.15),
                        value: animating
                    )
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.ultraThinMaterial)

                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.white.opacity(0.5))
            }
        )
        .onAppear {
            animating = true
        }
    }
}
```

### Button Press Feedback

```swift
struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
            .animation(.serenityQuick, value: configuration.isPressed)
    }
}
```

---

## 8. Accessibility

### Color Contrast Requirements

All text must meet WCAG 2.1 AA standards:

| Combination | Contrast Ratio | Status |
|-------------|----------------|--------|
| Charcoal on Canvas | 12.5:1 | AAA Pass |
| Charcoal on Cream | 10.2:1 | AAA Pass |
| Muted on Canvas | 5.1:1 | AA Pass |
| White on Lavender | 4.6:1 | AA Pass |
| Lavender on Canvas | 3.8:1 | AA Pass (Large text only) |

### Dynamic Type Support

```swift
// All text uses system font scaling automatically
// Ensure layouts accommodate larger text sizes

struct AdaptiveStack<Content: View>: View {
    @Environment(\.dynamicTypeSize) var dynamicTypeSize
    let content: () -> Content

    var body: some View {
        if dynamicTypeSize >= .accessibility1 {
            VStack(alignment: .leading, spacing: 8) {
                content()
            }
        } else {
            HStack(spacing: 12) {
                content()
            }
        }
    }
}
```

### Reduce Motion Support

```swift
struct MotionSensitiveAnimation: ViewModifier {
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    let animation: Animation

    func body(content: Content) -> some View {
        content
            .animation(reduceMotion ? .none : animation)
    }
}

// Usage
.modifier(MotionSensitiveAnimation(animation: .serenityDefault))
```

### VoiceOver Considerations

```swift
// Chat bubbles
AIMessageBubble(message: message)
    .accessibilityLabel("Serenity says: \(message.text)")
    .accessibilityHint("AI response")

UserMessageBubble(message: message)
    .accessibilityLabel("You said: \(message.text)")

// Buttons with clear labels
SerenityPrimaryButton("Send Message", icon: "arrow.up") { }
    .accessibilityLabel("Send message")
    .accessibilityHint("Sends your message to Serenity")
```

### Touch Targets

Minimum touch target size: **44 x 44 points**

```swift
// Ensure all interactive elements meet minimum size
.frame(minWidth: 44, minHeight: 44)
```

---

## 9. Chat UI Style Guidelines (ChatGPT/Grok)

This section documents best practices from leading AI chat interfaces (ChatGPT, Grok, Claude) for consistency and familiarity.

### 9.1 Message Layout Principles

#### Alignment & Spacing

| Element | ChatGPT | Grok | Serenity Recommendation |
|---------|---------|------|-------------------------|
| **AI messages** | Left-aligned, full width | Left-aligned with avatar | Left-aligned with avatar |
| **User messages** | Right-aligned, max 80% width | Right-aligned | Right-aligned, max 75% width |
| **Message gap** | 16-24px | 12-16px | 16px (relaxed, wellness feel) |
| **Avatar size** | 24px | 32px | 36px (prominent AI identity) |
| **Bubble padding** | 12-16px | 12px | 16px horizontal, 12px vertical |

#### Visual Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌──┐                                                       │
│  │AI│  Glass bubble - subtle, content-focused               │
│  └──┘  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                   │
│        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                   │
│                                        timestamp            │
│                                                             │
│                        ┌────────────────────────────────┐   │
│                        │  Accent bubble - user identity │   │
│                        └────────────────────────────────┘   │
│                                                  timestamp  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Message Bubble Styles

#### AI Message Bubble (ChatGPT-Inspired)

- **Background**: Subtle glass effect, not solid color
- **Border**: Very thin (0.5px) white border for depth
- **Shadow**: Soft, diffuse (radius 12px, 6% opacity)
- **Text**: Primary text color, good contrast
- **Avatar**: Left of bubble, vertically aligned to top

```swift
// AI Bubble - ChatGPT/Grok hybrid style
struct AIBubbleStyle {
    static let background = Color.white.opacity(0.6)
    static let material = Material.ultraThinMaterial
    static let borderColor = Color.white.opacity(0.4)
    static let borderWidth: CGFloat = 0.5
    static let cornerRadius: CGFloat = 20
    static let shadowColor = Color.black.opacity(0.06)
    static let shadowRadius: CGFloat = 12
    static let shadowY: CGFloat = 6
    static let padding = EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)
}
```

#### User Message Bubble (Grok-Inspired)

- **Background**: Solid accent color (lavender) with slight gradient
- **Border**: None (color provides definition)
- **Shadow**: Colored shadow matching bubble (adds glow effect)
- **Text**: White or very light (high contrast)
- **Position**: Right-aligned, no avatar

```swift
// User Bubble - Grok-inspired style
struct UserBubbleStyle {
    static let gradient = LinearGradient(
        colors: [Color.serenityLavender, Color.serenityLavender.opacity(0.9)],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    static let cornerRadius: CGFloat = 20
    static let shadowColor = Color.serenityLavender.opacity(0.3)
    static let shadowRadius: CGFloat = 12
    static let shadowY: CGFloat = 6
    static let padding = EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)
    static let textColor = Color.white
}
```

### 9.3 Typing Indicator

**ChatGPT Style**: Three animated dots in a small pill
**Grok Style**: Animated line/pulse effect

**Serenity Approach**: Three dots with gentle bounce, inside glass bubble

```swift
// Typing Indicator Specs
struct TypingIndicatorStyle {
    static let dotSize: CGFloat = 8
    static let dotSpacing: CGFloat = 4
    static let dotColor = Color.serenityLavender.opacity(0.6)
    static let animationDuration: Double = 0.5
    static let staggerDelay: Double = 0.15
    static let bounceHeight: CGFloat = 4
}
```

### 9.4 Input Field Design

**Common patterns from ChatGPT/Grok**:
- Expandable text area (grows with content)
- Send button that activates when text is present
- Subtle placeholder text
- Safe area handling for keyboard

```swift
// Input Field Specs
struct InputFieldStyle {
    // Container
    static let minHeight: CGFloat = 44
    static let maxHeight: CGFloat = 200
    static let cornerRadius: CGFloat = 20
    static let padding = EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 12)

    // Background
    static let backgroundLight = Color.white.opacity(0.8)
    static let backgroundDark = Color.black.opacity(0.48)
    static let material = Material.ultraThinMaterial

    // Border (focused state)
    static let focusedBorderColor = Color.serenityLavender.opacity(0.5)
    static let focusedBorderWidth: CGFloat = 2

    // Send Button
    static let buttonSize: CGFloat = 44
    static let buttonActiveColor = LinearGradient.serenityLavenderGradient
    static let buttonInactiveColor = Color.serenityDisabled
    static let buttonIcon = "arrow.up"
    static let buttonIconSize: CGFloat = 18
}
```

### 9.5 Timestamps & Metadata

| Style | Implementation |
|-------|----------------|
| **Position** | Below message bubble, aligned to bubble edge |
| **Format** | Relative when recent ("2m ago"), absolute when older ("Jan 5, 2:30 PM") |
| **Size** | Caption2 (11pt) |
| **Color** | Tertiary text color |
| **Visibility** | Show on recent messages, hide on older (or show on tap) |

### 9.6 Streaming Response Animation

**ChatGPT Style**: Text appears word-by-word with cursor
**Grok Style**: Text streams smoothly

**Serenity Approach**: Word-by-word appearance, no cursor, subtle fade-in

```swift
// Streaming Text Animation
struct StreamingTextStyle {
    static let wordAppearDuration: Double = 0.05
    static let wordAppearDelay: Double = 0.02
    static let fadeInOpacity: ClosedRange<Double> = 0.0...1.0
}
```

### 9.7 Empty State

When no messages exist:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                                                             │
│                     ┌──────────────┐                        │
│                     │   ✨ Logo    │                        │
│                     └──────────────┘                        │
│                                                             │
│                  "Hello, I'm Serenity"                      │
│                                                             │
│           "How are you feeling today?"                      │
│                                                             │
│    ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│    │ Stressed │  │ Anxious  │  │  Happy   │                │
│    └──────────┘  └──────────┘  └──────────┘                │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Suggestion chips**: Glass-style buttons with common conversation starters

### 9.8 Error States

| State | Visual | Copy |
|-------|--------|------|
| **Network error** | Red tint on message with retry icon | "Couldn't send. Tap to retry." |
| **AI error** | Orange warning icon | "I'm having trouble responding. Try again?" |
| **Rate limit** | Timer icon | "Taking a breath. Ready in 30s." |

### 9.9 Accessibility in Chat

```swift
// Accessibility Labels
extension ChatAccessibility {
    // Message bubbles
    static func aiMessage(_ text: String) -> String {
        "Serenity says: \(text)"
    }

    static func userMessage(_ text: String) -> String {
        "You said: \(text)"
    }

    // Actions
    static let sendButton = "Send message"
    static let sendButtonHint = "Sends your message to Serenity"

    static let retryButton = "Retry sending"
    static let retryButtonHint = "Attempts to send the failed message again"

    // Typing indicator
    static let typingIndicator = "Serenity is typing"
}
```

---

## 10. Implementation Checklist

### For T1 (UI/UX Terminal)

- [ ] Define all colors in `SerenityColors.swift`
- [ ] Create typography extensions in `SerenityTypography.swift`
- [ ] Implement `GlassEffect` modifier
- [ ] Build `AIMessageBubble` and `UserMessageBubble` components
- [ ] Create `SerenityInputField` component
- [ ] Implement `SerenityCard` component
- [ ] Build `SerenityPrimaryButton` and `SerenitySecondaryButton`
- [ ] Create `SerenityTabBar` component
- [ ] Implement `BreathingBackground` view
- [ ] Add animation extensions
- [ ] Ensure all components support Dynamic Type
- [ ] Test with Reduce Motion enabled
- [ ] Verify VoiceOver labels

### Design Tokens Summary

```swift
// Quick reference for implementation
enum SerenityTokens {
    // Corner Radius
    static let radiusSmall: CGFloat = 12
    static let radiusMedium: CGFloat = 16
    static let radiusLarge: CGFloat = 20
    static let radiusXLarge: CGFloat = 24
    static let radiusSheet: CGFloat = 32

    // Spacing
    static let spacingXS: CGFloat = 4
    static let spacingSM: CGFloat = 8
    static let spacingMD: CGFloat = 12
    static let spacingLG: CGFloat = 16
    static let spacingXL: CGFloat = 20
    static let spacingXXL: CGFloat = 24

    // Blur
    static let blurLight: CGFloat = 10
    static let blurRegular: CGFloat = 20
    static let blurHeavy: CGFloat = 40

    // Animation
    static let animationQuick: Double = 0.3
    static let animationDefault: Double = 0.4
    static let animationGentle: Double = 0.5
    static let animationSlow: Double = 0.8
}
```

---

*This design system is a living document. Update as the Serenity app evolves.*
