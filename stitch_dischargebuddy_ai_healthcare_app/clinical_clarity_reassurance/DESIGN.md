---
name: Clinical Clarity & Reassurance
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#3d4947'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#6d7a77'
  outline-variant: '#bcc9c6'
  surface-tint: '#006a61'
  primary: '#00685f'
  on-primary: '#ffffff'
  primary-container: '#008378'
  on-primary-container: '#f4fffc'
  inverse-primary: '#6bd8cb'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#b61722'
  on-tertiary: '#ffffff'
  tertiary-container: '#da3437'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#89f5e7'
  primary-fixed-dim: '#6bd8cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#005049'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.03em
  code-verbatim:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 22px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system is engineered for patients transitioning from inpatient hospital environments to recovery at home. The core brand ethos is anchored in cognitive reassurance, absolute clarity, and medical authority delivered without bureaucratic coldness. Patients and their caregivers often interact with this interface during states of physical fatigue, high anxiety, and medication-induced grogginess; therefore, the visual environment must actively lower cognitive strain.

The design movement combines **Clean Clinical Minimalism** with **Humanized Soft-Tech Tactility**. It rejects both sterile, utilitarian institutional software and overly whimsical consumer-app aesthetics. Instead, it employs generous breathing room, ultra-clear visual hierarchy, deliberate signposting of critical health warnings, and grounded spatial depth to engender immediate trust and emotional stability.

## Colors

The palette is tuned specifically for optical comfort and unambiguous clinical signaling in high-stakes recovery contexts.

- **Primary Teal (`#0D9488`)**: Represents restorative healing, clarity, and assistive intelligence. Dark teal (`#115E59`) is reserved for focused states and high-contrast interactive text; light teal tint (`#CCFBF1`) is utilized for AI summary backdrops and subtle active states.
- **Secondary Mint (`#10B981`)**: Evokes recovery milestones, successful medication adherence, and safe discharge criteria. Paired with deep emerald (`#059669`) for affirmative text and soft mint (`#D1FAE5`) for progress indicators.
- **Alert Coral (`#EF4444`) & Warning Amber (`#F59E0B`)**: Dedicated strictly to urgent discharge red flags (e.g., fever thresholds, abnormal bleeding warnings, emergency room indicators). These colors must never be used decoratively.
- **Neutrals & Surfaces**: Clean medical white (`#FFFFFF`) forms the foundational surface layer, set upon a soft anti-glare canvas (`#F8FAFC`). Borders use crisp slate (`#E2E8F0`). Text hierarchy strictly adheres to deep slate (`#0F172A`) for effortless legibility, supported by secondary slate (`#475569`) for non-critical metadata.

## Typography

The type system prioritizes high-legibility geometry and comfortable tracking for recovering patients. 

**Plus Jakarta Sans** provides a friendly, welcoming cadence for editorial content, primary actions, and major instructional headlines. **Inter** is employed across utility labels, data tables, multi-language switchers, and clinical verification blocks due to its strict, objective tabular metrics.

- Body text maintains a minimum line-height ratio of 1.6 to prevent visual crowding when users read dosage schedules or physical therapy restrictions.
- In multilingual contexts (English, Hindi, Bengali), vertical line height scales up by an additional 10% to accommodate non-Latin script ascenders and descenders without clipping.
- Never use font weights below 400 or font sizes below 13px for any actionable or clinical guidance.

## Layout & Spacing

The layout model is built on an adaptive 12-column grid for desktop (`1280px` max content container) and tablet, collapsing to a single-column sequence on mobile screens (`< 768px`).

- **Grid & Alignment**: Desktop utilizes `24px` gutters with a centered max-width frame. Side margins adjust dynamically on ultrawide screens while preserving a minimum safety margin of `32px`.
- **Rhythm**: Component spacing uses an explicit 4px/8px modular base. Dense information displays are forbidden; instructional cards must enforce at least `1.5rem` (`space-lg`) of internal padding to maintain calm visual pacing.
- **Section Pacing**: Primary diagnostic streams (e.g., Medication Schedules vs. Warning Signs) are separated by `2.5rem` (`space-xl`) vertically to prevent accidental cognitive blending of separate discharge domains.

## Elevation & Depth

Visual hierarchy relies on soft, atmospheric tonal separation rather than sharp drop shadows or heavy industrial borders.

- **Level 0 (Canvas)**: Background tone (`#F8FAFC`). Flat, non-reflective.
- **Level 1 (Card Containers)**: Pure white (`#FFFFFF`) with a delicate hairline boundary (`1px solid #E2E8F0`) and an ambient glow shadow: `0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.03)`.
- **Level 2 (Active/Interactive Containers & Flyouts)**: Elevated interactive elements (upload dropzone drag states, language menus, active checklist summaries) use a soft teal-tinted ambient shadow: `0 10px 15px -3px rgba(13, 148, 136, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.03)`.
- **Level 3 (Urgent Callouts & Modal Overlays)**: High-priority warning panels and verification dialogues carry a focused shadow: `0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.04)`.

## Shapes

The design system enforces balanced, soft geometry (`roundedness: 2`) across all primary interactive surfaces, delivering a protective, approachable visual language.

- **Base Cards & Modules**: `0.5rem` (`8px`) border-radius provides structural stability without rigid, institutional harshness.
- **Prominent Cards & Upload Dropzones**: `rounded-lg` (`1rem` / `16px`) used for full-width summaries, upload zones, and medication groups.
- **Pills & Status Badges**: Full-pill treatment (`9999px`) for severity indicators, language switches, and state chips to visually differentiate status data from rectangular body content cards.

## Components

### 1. Split-Card Callouts (AI Plain-Language vs. Medical Record)
- **Structure**: A side-by-side or stacked comparative card container.
- **AI Plain-Language Summary**: Framed in a light teal background (`#F0FDFA`) with a subtle gradient border (`#0D9488` to `#10B981`, `1.5px`). Accompanied by a rounded pill badge reading "DischargeBuddy AI Summary" in teal primary text on `#CCFBF1`.
- **Official Medical Record Excerpt**: Displayed directly beside or beneath the AI summary in a neutral, monochrome slate box (`#F1F5F9`) with a flat hairline border (`#CBD5E1`). Set in `code-verbatim` font styling to communicate authentic, unedited clinical source documentation.

### 2. Buttons & Actions
- **Primary Action**: Solid teal (`#0D9488`), white text, `rounded-md` (8px), padding `0.75rem 1.5rem`. Hover state transitions to `#115E59`.
- **Secondary Action**: White surface, slate border (`#E2E8F0`), text `#0F172A`. Hover transitions to `#F8FAFC`.
- **Urgent Emergency Action**: Alert coral background (`#EF4444`), white bold text, dedicated to "Call Care Team" or "Emergency Signs".

### 3. Checklists & Recovery Tasks
- Large touch targets (`minimum 44x44px`) with a smooth interactive checkbox.
- Checkbox active state fills with `#10B981` (mint), sporting an animated check icon. Checked tasks shift typography to muted slate (`#64748B`) with an accessible strikethrough.

### 4. Pills & Badges
- Pill-shaped (`rounded-full`), padded `0.25rem 0.75rem`.
- **Mild/Routine**: `#D1FAE5` background with `#065F46` text.
- **Warning/Monitor**: Amber light background (`#FEF3C7`) with `#92400E` text.
- **Emergency/Immediate Action**: `#FEE2E2` background with `#991B1B` text.

### 5. Multi-Language Toggles
- Compact segmented pill switch featuring English, Hindi (हिन्दी), and Bengali (বাংলা).
- Active segment is filled with white and elevated with `shadow-sm`, with text rendered in primary teal `#0D9488`.

### 6. Document Upload Dropzone
- Outlined with a 2px dashed border (`#99F6E4`), resting on an anti-glare canvas tint (`#F0FDFA`).
- Drag-hover shifts the border to solid `#0D9488` and displays an active processing micro-interaction indicating secure HIPAA-compliant ingestion.

### 7. Recovery Progress Stepper
- Horizontal chain on desktop, vertical rail on mobile. Connected by a 2px progress track colored `#E2E8F0` (inactive) and `#10B981` (completed). Steps feature high-contrast numeric or icon markers.