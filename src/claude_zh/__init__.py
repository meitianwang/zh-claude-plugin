"""claude_zh — an update-resilient Simplified Chinese localization for Claude Desktop (macOS).

The package is organised so the risky, signature-breaking work is isolated and
optional:

- appinfo / backup / signing / config_locale : bundle plumbing
- patches/*                                   : individual, failure-isolated edits
- corpus                                      : translation data (pheohu seed + Claude backfill)
- translate                                   : fill coverage gaps with Claude
- autopatch                                   : LaunchAgent that re-applies after Claude updates

See README.md for the design and the known trade-offs (ad-hoc signing, Cowork).
"""

__version__ = "0.1.0"
