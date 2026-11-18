# Colours (hot pink to orange, used sparingly)

The brand colours are hot pink `#FF2D6F` to orange `#FF6B35`, but they appear only in small places. Everything big is black and white.
Files: `lumin-app/app/globals.css` (the variables and button styles) and `lumin-app/tailwind.config.ts` (the names).

## What each thing looks like
| Where | Look |
|---|---|
| Main buttons (`.brand-gradient`, kept as a name) | Plain near-black on light, near-white on dark. No gradient, no edge |
| "+" add buttons, selected chips and tabs, progress, avatars, banners (`.fill-violet`, kept as a name) | Flat red `#E3243F` (a touch deeper than the brand pink so white text passes AA), white text |
| Counters and notification badges | Orange `#FF6B35` with black text |
| Middle Scan button of the bottom navigation (`.brand-scan`) | Coral-red to orange-red gradient `#F5334A` to `#EE5A24`, diagonal, white icon, soft red glow (the look from the earlier build) |
| The product-drawer edge, the watermark (`.brand-sig`) | The pink to orange gradient `#FF2D6F` to `#FF6B35` |
| Thin lines, selected rings, tab underlines, small accent text | Ink on light, near-white on dark (never pink: the old build had 83 pink text uses and 53 pink borders) |
| Errors, delete, out of stock | Red (`danger`) |
| Pay buttons (cart, Stripe sheet) | Plain neutral button |

## Names
`accent` orange, `on-accent` text on orange, `accent2` pink (fills), `mark` thin lines, `accent-ink` small accent text, `danger` red.

## Going back
- To the yellow and violet version: `lumin-yellow-violet-backup.zip` (full project copy before this switch).
Unzip it over the project. Older backups (coral, red-orange, plain lime) were lost when the workspace was reset.

## Not covered
The logo, splash and app icon images are still the old pink (they are pictures). The admin app keeps its own palette (red-orange).
