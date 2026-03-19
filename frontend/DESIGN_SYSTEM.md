# Digital Commons Style Guide Implementation

This document describes the implementation of the NC DIT Digital Commons Style Guide in the Public Comment Analyzer application.

## Overview

The Digital Commons Style Guide is NC DIT's design system that unifies North Carolina's web presence throughout design and development. It ensures a high-quality and consistent user experience across all nc.gov websites.

## Design Principles

1. **Unify the Experience** - Single underlying system that unifies the user experience
2. **Empower But Don't Overwhelm** - Provide sensible defaults without burdening users
3. **Actively Advocate** - Advocate for the citizen experience
4. **Be Accessible** - Government serves all people, and so should government websites

## Color Palette - First in Flight (Primary)

### Primary Colors
- **Primary**: `#092940` - Dark blue used for headers, primary text, and main UI elements
- **Primary RGB**: `rgb(9, 41, 64)`

### Secondary Colors
- **Secondary Light**: `#EEF7FF` - Light blue for backgrounds
- **Secondary (dark text)**: `#3892E1` - Use only with dark text
- **Secondary (white text)**: `#1E79C8` - Use only with white text
- **Secondary Dark**: `#3B75A9` - Darker blue for accents

### Notification Colors
- **Info**: `#3D7AAF` - Information messages
- **Success**: `#008945` - Success states
- **Warning**: `#C65200` - Warning messages
- **Error**: `#BC2442` - Error states

### Neutral Colors
- **White**: `#FFFFFF`
- **Black**: `#000000`
- **Gray Light**: `#F5F5F5`
- **Gray**: `#CCCCCC`
- **Gray Dark**: `#666666`

## Typography

### Font Family
- **Primary**: Source Sans Pro (imported from Google Fonts)
- **Weights**: 400 (regular), 600 (semibold), 700 (bold)

### Heading Sizes
- **H1**: 42px / 2.625rem, weight 700, line-height 50.4px
- **H2**: 36px / 2.25rem, weight 700, line-height 43.2px, letter-spacing 0.4px
- **H3**: 28px / 1.75rem, weight 700, line-height 33.6px
- **H4**: 24px / 1.5rem, weight 700, line-height 28.8px
- **H5**: 21px / 1.3125rem, weight 700, line-height 25.2px
- **H6**: 18px / 1.125rem, weight 700, line-height 21.1px

### Body Text
- **Body**: 18px / 1.125rem, weight 400, line-height 30px
- **Body Bold**: Same size, weight 700
- **Body Semibold**: Same size, weight 600
- **Body Italic**: Same size, italic style

### Special Text
- **Breadcrumb**: 16.7px / 1.0437rem, weight 400, letter-spacing 0.2px
- **Pull Quote**: 18px, weight 400, italic, with left border

## Iconography

### Guidelines
- Use open-source Bootstrap or Icomoon icons in SVG format
- Icons should be single-color only
- Standard size: 75px × 75px
- Smaller sizes available: 24px (sm), 48px (md)

### Approved Color Combinations
1. **Primary background** with **White foreground**
2. **Secondary Light background** with **Primary foreground**

### Usage Rules
- ✅ DO: Use approved color combinations
- ✅ DO: Keep icons within the same family
- ❌ DON'T: Combine colors across palettes
- ❌ DON'T: Use multi-color icons

## Spacing System

- **XS**: 0.25rem (4px)
- **SM**: 0.5rem (8px)
- **MD**: 1rem (16px)
- **LG**: 1.5rem (24px)
- **XL**: 2rem (32px)
- **XXL**: 3rem (48px)

## Layout

- **Max Content Width**: 1200px
- **Border Radius**: 4px (standard), 8px (large)

## Shadows

- **Small**: `0 1px 3px rgba(0, 0, 0, 0.12)`
- **Medium**: `0 2px 4px rgba(0, 0, 0, 0.1)`
- **Large**: `0 4px 8px rgba(0, 0, 0, 0.15)`

## Transitions

- **Fast**: 150ms ease-in-out
- **Normal**: 250ms ease-in-out
- **Slow**: 350ms ease-in-out

## File Structure

```
src/styles/
├── _variables.scss      # Design system variables
├── _typography.scss     # Typography styles
├── _components.scss     # Reusable component styles
└── styles.scss          # Global styles and imports
```

## Usage in Components

Import variables in component SCSS files:

```scss
@import '../../../styles/variables';

.my-component {
  color: $color-primary;
  padding: $spacing-lg;
  font-size: $font-size-body;
}
```

## Accessibility

All color combinations meet WCAG/Section 508 4.5:1 color contrast ratio requirements. Do not use grayed-out combinations shown in the style guide accessibility sections.

### Testing
- Use [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) for custom color combinations
- Ensure all interactive elements are keyboard accessible
- Provide appropriate ARIA labels for screen readers

## Component Examples

### Buttons
```html
<button class="btn-primary">Primary Action</button>
<button class="btn-secondary">Secondary Action</button>
<button class="btn-outline">Outline Button</button>
```

### Alerts
```html
<div class="alert alert-info">Information message</div>
<div class="alert alert-success">Success message</div>
<div class="alert alert-warning">Warning message</div>
<div class="alert alert-error">Error message</div>
```

### Cards
```html
<div class="card">
  <div class="card-header">
    <h3 class="card-title">Card Title</h3>
    <p class="card-subtitle">Card subtitle</p>
  </div>
  <div class="card-content">
    Card content goes here
  </div>
  <div class="card-actions">
    <button class="btn-primary">Action</button>
  </div>
</div>
```

## Resources

- [Digital Commons Style Guide](https://zeroheight.com/6cc837e20/p/638fcb-welcome)
- [Source Sans Pro on Google Fonts](https://fonts.google.com/specimen/Source+Sans+Pro)
- [Bootstrap Icons](https://icons.getbootstrap.com/)
- [Icomoon Icons](https://icomoon.io/app/#/select)
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)

## Screenshots

Design system screenshots are available in the project root:
- `design-system-welcome.png` - Welcome page
- `design-system-color-palettes.png` - Color palette overview
- `design-system-first-in-flight.png` - Primary palette details
- `design-system-global-colors.png` - Global notification colors
- `design-system-typography.png` - Typography specifications
- `design-system-iconography.png` - Icon guidelines
- `design-system-principles.png` - Design principles
