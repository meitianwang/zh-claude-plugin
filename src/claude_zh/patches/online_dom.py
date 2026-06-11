"""Translate the remote claude.ai page rendered inside Claude Desktop.

When logged in with an official account, the main chat/projects/Artifacts UI is
the claude.ai web frontend served remotely. claude.ai does not offer Chinese, so
whitelisting zh-CN locally is not enough — the remote page renders in English.
This patch wraps the main view's ``dom-ready`` handler (in app.asar's
``.vite/build/index.js``) so that after the page loads we run a display-layer
translation script in it: a TreeWalker over text nodes plus a few attributes,
backed by a source-text→zh map built from the corpus, re-applied on mutation.

It only rewrites visible text/attributes. It never touches network requests,
responses, model routing, or page logic. This is the one patch that edits
app.asar; it is failure-isolated, so if the anchor drifts the rest of the
install still succeeds (the shell/menus stay translated, only remote-page text
stays English).
"""

from __future__ import annotations

import json
import re

from .. import asar
from ..appinfo import AppInfo
from ..corpus import Corpus
from ..util import load_json, log
from . import PatchError

TARGET = ".vite/build/index.js"
MARKER = "/*__claudeZhOnlineDOM*/"
_MAX_LEN = 100

# Match `WC.webContents.on("dom-ready",()=>{ BODY })` where BODY has no braces.
_HANDLER_RE = re.compile(
    r'(?P<wc>[A-Za-z_$][\w$]*)\.webContents\.on\("dom-ready",\(\)=>\{(?P<body>[^{}]*)\}\)'
)


def _build_map(app: AppInfo, corpus: Corpus) -> dict[str, str]:
    english = load_json(app.frontend_i18n / "en-US.json")
    mapping: dict[str, str] = {}
    for key, en in english.items():
        zh = corpus.frontend.get(key)
        if (
            isinstance(en, str) and isinstance(zh, str) and en != zh
            and en.strip() == en and 1 <= len(en) <= _MAX_LEN
            and not any(ch in en for ch in "{<\n") and "http" not in en
        ):
            mapping.setdefault(en, zh)
    return dict(sorted(mapping.items()))


def _build_script(lang: str, mapping: dict[str, str]) -> str:
    m = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
    # Greeting + relative-time rules that carry a runtime value (not in the map).
    rules = (
        '[[/^Good morning, (.+)$/,"早上好，$1"],[/^Morning, (.+)$/,"早上好，$1"],'
        '[/^Good afternoon, (.+)$/,"下午好，$1"],[/^Afternoon, (.+)$/,"下午好，$1"],'
        '[/^Good evening, (.+)$/,"晚上好，$1"],[/^Evening, (.+)$/,"晚上好，$1"],'
        '[/^(\\d+) selected$/,"已选择 $1 项"],'
        '[/^Mon$/,"周一"],[/^Tue$/,"周二"],[/^Wed$/,"周三"],[/^Thu$/,"周四"],'
        '[/^Fri$/,"周五"],[/^Sat$/,"周六"],[/^Sun$/,"周日"]]'
    )
    return (
        "(()=>{try{"
        f'var L="{lang}",M={m},RX={rules};'
        'try{localStorage.setItem("spa:locale",L);'
        'document.documentElement&&document.documentElement.setAttribute("lang",L)}catch(e){}'
        'var N=function(s){return (s||"").replace(/\\s+/g," ").trim()};'
        'var R=function(s){var n=N(s);if(!n)return;if(M[n])return M[n];'
        'for(var i=0;i<RX.length;i++){var mm=n.match(RX[i][0]);if(mm)return RX[i][1].replace("$1",mm[1])}};'
        'var SKIP={SCRIPT:1,STYLE:1,NOSCRIPT:1,TEXTAREA:1};'
        'function walk(){try{'
        'var b=document.body||document.documentElement;if(!b)return;'
        'var w=document.createTreeWalker(b,NodeFilter.SHOW_TEXT,{acceptNode:function(n){'
        'var p=n.parentElement;if(!p||SKIP[p.tagName]||p.isContentEditable)return NodeFilter.FILTER_REJECT;'
        'return R(n.nodeValue)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}});'
        'var n;while(n=w.nextNode()){var v=R(n.nodeValue);if(v)n.nodeValue=v}'
        'var els=document.querySelectorAll("[aria-label],[title],[placeholder]");'
        'for(var i=0;i<els.length;i++){var e=els[i];'
        '["aria-label","title","placeholder"].forEach(function(a){'
        'try{var cur=e.getAttribute(a);var t=R(cur);if(t&&t!==cur)e.setAttribute(a,t)}catch(_){}})}'
        '}catch(_){}}'
        'walk();'
        'var t;new MutationObserver(function(){clearTimeout(t);t=setTimeout(walk,40)})'
        '.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true});'
        "}catch(e){}})()"
    )


def _strip_existing(text: str) -> str:
    # Remove a previous injection: restore the wrapped handler to its plain form.
    pattern = re.compile(
        r'(?P<wc>[A-Za-z_$][\w$]*)\.webContents\.on\("dom-ready",\(\)=>\{'
        r'(?P<body>[^{}]*);'
        r'(?P=wc)\.executeJavaScript\((?:"(?:\\.|[^"\\])*")\)\.catch\(\(\)=>\{\}\)'
        r'\}\);' + re.escape(MARKER)
    )
    return pattern.sub(lambda m: f'{m.group("wc")}.webContents.on("dom-ready",()=>{{{m.group("body")}}})', text)


def apply(app: AppInfo, corpus: Corpus, lang: str = "zh-CN") -> None:
    text = asar.read_file(app.app_asar, TARGET).decode("utf-8")
    text = _strip_existing(text)

    handlers = list(_HANDLER_RE.finditer(text))
    if not handlers:
        raise PatchError("no webContents dom-ready handler found; remote-page translation skipped")
    chosen = next((h for h in handlers if "main_view_dom_ready" in h.group("body")), handlers[0])

    mapping = _build_map(app, corpus)
    script = _build_script(lang, mapping)
    wc, body = chosen.group("wc"), chosen.group("body")
    injection = (
        f'{wc}.webContents.on("dom-ready",()=>{{{body};'
        f"{wc}.executeJavaScript({json.dumps(script)}).catch(()=>{{}})}});{MARKER}"
    )
    patched = (text[: chosen.start()] + injection + text[chosen.end():]).encode("utf-8")

    if asar.replace_file(app.app_asar, app.info_plist, TARGET, patched):
        log(f"  online-dom: injected translation for {len(mapping)} strings into app.asar")
    else:
        log("  online-dom: already up to date")
