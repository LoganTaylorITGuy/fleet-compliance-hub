#!/usr/bin/env bash
# Rebuild the logo and icon files in app/static/brand/ from the source art.
#
#   scripts/build-brand-assets.sh [source-dir]     # default: brand-src/
#
# Source art (1024x1024, kept out of the repo; placeholder, AI-generated):
#   logo-full.png   full-color sample provider badge on a dark background
#   icon-navy.png   navy truck in a ring on a flat light-gray background
#
# Output:
#   provider-logo-sample.webp   badge cropped square, background kept (480 px)
#   icon-192.png                navy truck: transparent outside the ring,
#   favicon-32.png, favicon-16.png   white inside it, so it reads on light and
#                                     dark tabs alike
#   apple-touch-icon.png        180 px, opaque white square (iOS fills
#                               transparency with black)
#
# Requires ImageMagick 7 (magick).

set -euo pipefail

SRC="${1:-brand-src}"
cd "$(dirname "$0")/.."
OUT=app/static/brand
command -v magick >/dev/null || { echo "ImageMagick is required: brew install imagemagick" >&2; exit 1; }
for f in logo-full.png icon-navy.png; do
  [[ -f "$SRC/$f" ]] || { echo "Missing $SRC/$f" >&2; exit 1; }
done
mkdir -p "$OUT"

# Geometry measured on the 1024 px sources.
BADGE_CROP="800x800+112+105"     # full badge with its banner and some glow
RING_CENTER="511.5,511.5"        # navy ring: outer edge spans x and y 179..844
RING_EDGE="511.5,179.5"          # a point on the ring's outer edge
RING_CROP="670x670+177+177"      # the ring plus a 2 px margin
BACKGROUND="rgb(221,225,226)"    # flat background of icon-navy.png

magick "$SRC/logo-full.png" -crop "$BADGE_CROP" +repage -resize 480x480 \
  -strip -quality 86 "$OUT/provider-logo-sample.webp"

# Navy icon master: background to white, then an exact circular alpha mask.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
MASTER="$WORK/icon-master.png"
magick "$SRC/icon-navy.png" -fuzz 10% -fill white -opaque "$BACKGROUND" \
  \( -size 1024x1024 xc:black -fill white -draw "circle $RING_CENTER $RING_EDGE" \) \
  -alpha off -compose CopyOpacity -composite -crop "$RING_CROP" +repage "$MASTER"

# The art is navy on white: a small palette removes JPEG noise and keeps files small.
for size in 192 32 16; do
  name="icon-$size.png"
  [[ $size -le 32 ]] && name="favicon-$size.png"
  magick "$MASTER" -filter Lanczos -resize "${size}x${size}" -colors 48 -strip "$OUT/$name"
done

magick -size 180x180 xc:white \( "$MASTER" -resize 164x164 \) -gravity center \
  -composite -colors 48 -strip "$OUT/apple-touch-icon.png"

ls -l "$OUT"
