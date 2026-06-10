# GuardianNode Brand Kit

Optimized derivatives generated from the source kit in [`assets/`](../). Use these
in the README, docs site, dashboard, and installers — don't re-derive from the
source PNGs unless regenerating everything.

## Files

| File | Use |
|---|---|
| `logo-horizontal.png` (1000×192, transparent) | README header, docs site header, wide layouts |
| `logo-vertical.png` (600×232, transparent) | Hero sections, login/setup screens |
| `icon.png` (512², transparent) | App icon source, PWA icon |
| `icon-192.png` | PWA / small contexts |
| `apple-touch-icon.png` (180², Deep Teal background) | iOS home screen |
| `favicon.ico` (48/32/16) + `favicon-32.png` / `favicon-16.png` | Browser tabs |
| `og-card.png` (1200×630) | Open Graph / social link previews |

## Color palette

| Color | Hex | Meaning |
|---|---|---|
| Deep Teal | `#0D3B4A` | Trust, security — **primary** |
| Forest Green | `#275E3D` | Growth, protection — secondary |
| Slate Gray | `#475569` | Clarity, balance — body text |
| Sky Blue | `#7EC6F5` | Calm, reassurance — accents |
| Light Neutral | `#F3F6F8` | Clean space — backgrounds |

## Typography

- **Headings:** Sora SemiBold — modern, approachable, confident
- **Body & UI:** Inter Regular — clean, highly readable, built for interfaces

The dashboard self-hosts both via `@fontsource/*` packages — never load fonts
from a CDN inside the product (see [PRIVACY.md](../../PRIVACY.md): GuardianNode
does not phone home).

## Voice

Tagline: **"Protecting Families, Privately."**

Brand values: Private by Design · Family First · Trustworthy · Technical & Modern ·
Calm & Supportive. Write copy that is calm and honest — no fear-mongering, no
overpromising (see `docs/PARENT_GUIDES/what-this-cannot-stop.md` for tone).

## Regenerating

Source images: `assets/4.png` (horizontal), `assets/5.png` (icon), `assets/6.png`
(vertical). Background removal uses corner flood-fill (not global white→transparent,
which would punch holes in the white house outline):

```bash
magick assets/4.png -alpha set -fuzz 4% -fill none \
  -draw "color 0,0 floodfill" -draw "color 2171,0 floodfill" \
  -draw "color 0,723 floodfill" -draw "color 2171,723 floodfill" \
  -trim +repage -resize 1000x -strip assets/brand/logo-horizontal.png
```
