from __future__ import annotations

# Compatibility shim retained because production.py imports renderer_safe.
# Subtitle generation now lives in renderer.py so long-form and vertical Shorts
# cannot silently diverge into incompatible caption layouts.
import renderer


def main():
    return renderer.main()


if __name__ == "__main__":
    main()
