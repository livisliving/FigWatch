"""Tone of Voice audit handler — responds to @tone comments."""

import os
import subprocess

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_PATH = os.path.join(_THIS_DIR, '..', 'skills', 'tone', 'skill.md')
_REFS_DIR = os.path.join(_THIS_DIR, '..', 'skills', 'tone', 'references')
_HOME = os.path.expanduser('~')
_FALLBACK_SKILL = os.path.join(_HOME, '.claude', 'skills', 'tone-reviewer', 'SKILL.md')
_FALLBACK_REFS = os.path.join(_HOME, '.claude', 'skills', 'tone-reviewer', 'references')

_cache = {}

UK_GUIDELINES = (
    "Joybuy Tone of Voice — UK (English)\n"
    "Friendly & approachable, clear & direct, trustworthy, helpful.\n"
    "GBP (£) before amount, no space. Full stop decimal. \"delivery\" not \"shipping\".\n"
    "Avoid: hype language, exclamation mark overuse (max 1 per screen), ambiguous CTAs."
)


def _load(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return None


def _cached_load(key, path, fallback=None):
    if key in _cache:
        return _cache[key]
    content = _load(path) or (fallback and _load(fallback))
    if content:
        _cache[key] = content
    return content


def _load_tov_guide(locale):
    file_map = {'de': 'tov-de.md', 'fr': 'tov-fr.md', 'nl': 'tov-nl.md', 'benelux': 'tov-benelux.md'}
    fname = file_map.get(locale.lower())
    if not fname:
        return None
    key = f'tov-{locale}'
    if key in _cache:
        return _cache[key]
    content = _load(os.path.join(_REFS_DIR, fname)) or _load(os.path.join(_FALLBACK_REFS, fname))
    if content:
        _cache[key] = content
    return content


def _strip_markdown(text):
    import re
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def tone_handler(*, texts, targeted, target_name, primary_text, locale, node_name, extra, claude_path, model='sonnet', reply_lang='en', **_):
    tov_guide = _load_tov_guide(locale) or UK_GUIDELINES
    skill = _cached_load('skill', _SKILL_PATH, _FALLBACK_SKILL)

    text_list = '\n'.join(
        f'{i+1}. [{t["name"]}]: "{t["text"]}"' for i, t in enumerate(texts)
    )

    scope_instruction = ''
    if targeted and primary_text:
        scope_instruction = f'The reviewer placed their comment directly on the text "{primary_text}" (layer: "{target_name}"). Focus your audit primarily on this text. The nearby text nodes are included for context only.'
    elif targeted:
        scope_instruction = f'The reviewer placed their comment near the text layer "{target_name}". Focus your audit on the nearest text nodes listed below.'
    else:
        scope_instruction = f'The reviewer is auditing all text in the frame "{node_name}". Review each text node briefly.'

    skill_section = "Here is the skill definition:\n" + skill + "\n" if skill else ""
    extra_line = '- extra context from reviewer: "' + extra + '"' if extra else ""

    prompt = (
        "You have a skill called tone-reviewer. Use Mode 3: Comment Reply.\n\n"
        + skill_section
        + "Here is the ToV guide for " + locale.upper() + ":\n"
        + tov_guide + "\n\n"
        + "Now run Mode 3 with this input:\n"
        + "- locale: " + locale + "\n"
        + "- targeted: " + str(targeted) + "\n"
        + "- targetName: " + (target_name or "N/A") + "\n"
        + "- primaryText: " + (primary_text or "N/A") + "\n"
        + extra_line + "\n\n"
        + scope_instruction + "\n\n"
        + "Text nodes:\n" + text_list + "\n\n"
        + ("IMPORTANT: Write your entire reply in Simplified Chinese (\u7b80\u4f53\u4e2d\u6587). All text, explanations, and suggestions must be in Chinese.\n\n" if reply_lang == "cn" else "")
        + "Respond with ONLY the comment reply. No preamble, no explanation — just the output as specified by Mode 3."
    )

    # .app bundles inherit a minimal PATH, so claude can't find node.
    # Prepend the common Homebrew / system bin dirs so the CLI resolves.
    env = {**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '/usr/bin:/bin')}"}
    result = subprocess.run(
        [claude_path, '--print', '-p', prompt, '--model', model],
        capture_output=True, timeout=60, env=env,
    )

    stdout = result.stdout.decode('utf-8', errors='replace').strip()
    if stdout:
        reply = _strip_markdown(stdout)
    else:
        err = result.stderr.decode('utf-8', errors='replace').strip()
        if len(err) > 400:
            err = err[:400] + '\u2026'
        reply = 'Unable to generate audit.\n\n' + (f'Error: {err}' if err else f'claude exited with code {result.returncode}')
    header = '\U0001f5e3\ufe0f Claude \u8bed\u6c14\u5ba1\u6838' if reply_lang == 'cn' else '\U0001f5e3\ufe0f Claude ToV Audit'
    return f'{header}\n\n{reply}\n\n\u2014 Claude'
