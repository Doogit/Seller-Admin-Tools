# Build the committed Tailwind stylesheet from web/static/app.src.css.
#
# Uses the pinned standalone Tailwind CLI (a single Go binary, no Node). The
# binary itself is NOT committed (see .gitignore); download it once per machine:
#
#   Tailwind CLI: v3.4.17
#   https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/
#     tailwindcss-windows-x64.exe   (or -linux-x64 / -macos-arm64)
#   -> save as tools/tailwindcss.exe  (tools/tailwindcss on *nix)
#
# The BUILT web/static/tailwind.css IS committed, so a fresh clone runs offline
# without the binary; the binary is only needed to *change* styles.
#
# Determinism: `make css` on unchanged input produces a byte-identical file.
# CI/verify: `make css && git diff --exit-code web/static/tailwind.css`.

TAILWIND ?= tools/tailwindcss.exe

.PHONY: css
css:
	$(TAILWIND) -i web/static/app.src.css -o web/static/tailwind.css --minify
