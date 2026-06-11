"""Make the language picker show "简体中文" for zh-CN.

The picker renders each whitelisted locale's display name via
``Intl.DisplayNames``. Left alone it would label zh-CN with the host system's
rendering (or "Chinese, Simplified" in English). We append a tiny, idempotent
override to the main ``index-*.js`` bundle that special-cases the Chinese
locales and delegates everything else to the original implementation.
"""

from __future__ import annotations

from ..appinfo import AppInfo
from ..util import log
from . import PatchError

MARKER = "__claudeZhLabelPatch"

_OVERRIDE = (
    ";(()=>{const e=Intl.DisplayNames&&Intl.DisplayNames.prototype;"
    "if(!e||e." + MARKER + ")return;const n=e.of;"
    'e.of=function(e){const t=String(e);'
    'return t==="zh-CN"?"简体中文":t==="zh-TW"?"繁体中文（中国台湾）":'
    't==="zh-HK"?"繁体中文（中国香港）":n.call(this,e)};'
    'Object.defineProperty(e,"' + MARKER + '",{value:!0})})();'
)


def apply(app: AppInfo) -> int:
    candidates = sorted(app.frontend_assets.glob("index-*.js"))
    if not candidates:
        raise PatchError(f"no index-*.js bundle in {app.frontend_assets}")

    patched = 0
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            continue
        path.write_text(text + _OVERRIDE, encoding="utf-8")
        patched += 1
    if patched:
        log(f"  display-names: patched {patched} bundle(s)")
    else:
        log("  display-names: already patched")
    return patched
