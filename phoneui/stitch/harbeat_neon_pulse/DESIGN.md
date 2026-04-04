# Design System Strategy: The Kinetic Pulse

## 1. Overview & Creative North Star: "The Digital Cypher"
Street dance is about explosive movement, raw energy, and the tension between the spotlight and the shadows. This design system moves away from static, rigid grids to embrace **The Digital Cypher**—a creative north star that prioritizes rhythmic depth, high-contrast "neon-on-ink" aesthetics, and an editorial "Big Poster" layout.

We break the "standard app" feel by using intentional asymmetry. Large-scale typography should bleed off-canvas or overlap glass containers to create a sense of motion. The UI isn't a container for content; it’s a stage where the music and movement take center stage.

---

## 2. Colors: High-Voltage Ink
The palette is rooted in an ultra-dark environment (`#0d0d15`) to make the primary Electric Purple and secondary Neon Cyan feel like light sources rather than mere colors.

### The "No-Line" Rule
Standard 1px borders are strictly prohibited for sectioning. We define space through **Tonal Shifts**. 
- Use `surface-container-low` for large section backgrounds.
- Use `surface-container-high` for interactive elements sitting atop those sections.
- Boundaries are felt through color transitions, not drawn with lines.

### Surface Hierarchy & Nesting
Treat the UI as layers of frosted obsidian. 
*   **Base:** `surface` (#0d0d15) - The stage.
*   **Layer 1:** `surface-container-low` (#13131b) - Sectioning large areas.
*   **Layer 2:** `surface-container-highest` (#252530) - Actionable cards or floating panels.

### The "Glass & Gradient" Rule
To achieve a premium, custom feel, use Glassmorphism for high-level navigation and floating players. Apply `surface-variant` at 40% opacity with a `20px` backdrop-blur. 
**Signature Texture:** Main CTAs should use a linear gradient from `primary` (#cc97ff) to `primary-dim` (#9c48ea) at a 135-degree angle to simulate the shimmer of a neon tube.

---

## 3. Typography: The Big Poster Aesthetic
We utilize a dual-font system to balance "Street Brutalism" with high-end readability.

*   **Display & Headlines (Space Grotesk):** This is your "Voice." Use `display-lg` and `headline-lg` for style categories and song titles. Don't be afraid of tight letter-spacing and uppercase transformations to mimic dance event posters.
*   **Title & Body (Manrope):** This is your "Data." Manrope provides a clean, technical contrast to the aggressive headlines.
*   **The Hierarchy of Energy:** 
    *   **Level 1 (The Hook):** `display-lg` (3.5rem) - Used for hero style names (e.g., "KRUMP").
    *   **Level 2 (The Verse):** `title-lg` (1.375rem) - Used for track metadata.
    *   **Level 3 (The Info):** `body-md` (0.875rem) - Used for descriptions and settings.

---

## 4. Elevation & Depth: Tonal Layering
Traditional drop shadows look muddy on ultra-dark backgrounds. We use **Luminance and Blur** instead.

*   **The Layering Principle:** Instead of a shadow, place a `surface-container-high` element over a `surface-dim` background. The subtle shift in hex value creates a cleaner "lift."
*   **Ambient Shadows:** For floating "Now Playing" bars, use an extra-diffused shadow: `0 20px 40px rgba(0, 0, 0, 0.6)`. Add a 1px "Ghost Border" using `outline-variant` at 15% opacity to catch the "light" on the top edge only.
*   **Neon Glow:** Elements with high priority (like a "Live Battle" indicator) should use a `0 0 12px` outer glow using the `secondary` (#53ddfc) color at 30% opacity.

---

## 5. Components: Built for the Battle
All components must adhere to the `xl` (3rem) or `md` (1.5rem) roundedness scale to feel modern and "human."

*   **Action Buttons:** 
    *   **Primary:** Gradient fill (`primary` to `primary-dim`), `xl` rounded corners, minimum height 56px for high-speed touch accuracy.
    *   **Secondary:** Glass-filled `surface-variant` (20% opacity) with a `Ghost Border` of `outline-variant`.
*   **Genre Chips:** 
    *   Utilize the **Dance Style Color Palette**. A "Breaking" chip uses a `breaking` (#3B82F6) glow or text color. 
    *   Forbid dividers in lists. Use `2.75rem` (8) vertical spacing between list items to let the typography breathe.
*   **The "Beat-Seeker" (Progress Bar):**
    *   Base track: `surface-container-highest`.
    *   Active track: Gradient of `primary` to `secondary`.
    *   Thumb: A 12px circular glow of `secondary-fixed`.
*   **Interactive Cards:** 
    *   No borders. Background: `surface-container`. 
    *   On hover/press: Shift background to `surface-bright`.

---

## 6. Do’s and Don’ts

### Do:
*   **Use Asymmetry:** Place a large `display-sm` header partially overlapping a `surface-container` card.
*   **Respect the 44px Rule:** Street dance apps are often used while moving. Ensure all interactive areas (chips, play buttons, menus) exceed the 44px minimum touch target.
*   **Color-Code the Experience:** If the user selects "Popping," allow the `primary` glow effects to subtly shift toward the `popping` (#8B5CF6) global variable.

### Don't:
*   **Don't use 100% white text:** Always use `on-surface` (#efecf8) for body text to prevent eye strain against the ultra-dark background.
*   **Don't use Divider Lines:** If content feels cluttered, increase the spacing scale (e.g., move from `6` to `8`) rather than adding a line.
*   **Don't use Sharp Corners:** Avoid anything less than `sm` (0.5rem) radius. Sharp corners feel "corporate"; we want "fluid."