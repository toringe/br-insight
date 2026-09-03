"""main.js "random essay" click behavior (run under Node).

Imports the real main.js orchestrator against a minimal fake DOM, grabs
the listener it attaches to [data-random-link], and asserts the
observable outcome as JSON. Guards against the default-navigation race:
a plain click must preventDefault() before sending the browser to the
picked essay, otherwise the anchor's own navigation to /library/ wins.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not available")


@pytest.fixture(scope="module")
def main_mod(tmp_path_factory):
    """Copy assets/js (keeping main.js → ./modules/… relative imports) as .mjs."""
    js_dir = tmp_path_factory.mktemp("mainjs")
    shutil.copytree(REPO_ROOT / "assets/js", js_dir / "assets/js")
    (js_dir / "assets/js/main.js").rename(js_dir / "assets/js/main.mjs")
    return js_dir / "assets/js/main.mjs"


def run_main(main_mod, snippet: str) -> str:
    script = (
        f'import "{main_mod.as_uri()}";\n'
        f"{snippet}\n"
    )
    proc = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


SLUGS = ["love-letter", "worn-down-hell", "measure-of-a-man"]


class TestRandomEssayClick:
    def _wire_and_click(self, main_mod, event_props: dict) -> dict:
        props = ", ".join(f"{k}: {json.dumps(v)}" for k, v in event_props.items())
        script = f"""
        // fakes must exist BEFORE main.js evaluates — dynamic import,
        // because static imports are hoisted above this body.
        const listeners = [];
        const link = {{
          addEventListener(name, fn) {{
            if (name === "click") listeners.push(fn);
          }},
        }};
        const payload = {{ textContent: JSON.stringify({json.dumps(SLUGS)}) }};
        globalThis.document = {{
          querySelector(sel) {{
            return sel === "[data-random-link]" ? link : null;
          }},
          getElementById(id) {{
            return id === "essay-slugs" ? payload : null;
          }},
          addEventListener() {{}},
          querySelectorAll() {{ return []; }},
        }};
        const nav = {{ href: "unset" }};
        globalThis.window = {{
          location: nav,
          open() {{}},
        }};
        globalThis.history = {{ replaceState() {{}} }};

        await import("{main_mod.as_uri()}");

        const prevented = [];
        const event = {{
          {props},
          preventDefault() {{ prevented.push(true); }},
        }};
        for (const fn of listeners) fn(event);
        console.log(JSON.stringify({{
          wired: listeners.length,
          prevented: prevented.length > 0,
          navigatedTo: nav.href,
        }}));
        """
        proc = subprocess.run(
            [node, "--input-type=module", "--eval", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout.strip())

    def test_plain_click_prevents_default_and_navigates(self, main_mod):
        data = self._wire_and_click(main_mod, {"metaKey": False, "ctrlKey": False, "shiftKey": False})
        assert data["wired"] == 1
        assert data["prevented"] is True, (
            "plain click must preventDefault, or the anchor's default "
            "navigation to /library/ cancels the JS navigation"
        )
        assert data["navigatedTo"].startswith("/library/")
        assert data["navigatedTo"] != "/library/"
        assert data["navigatedTo"] in {f"/library/{s}/" for s in SLUGS}

    def test_modifier_click_opens_new_tab(self, main_mod):
        data = self._wire_and_click(main_mod, {"metaKey": True, "ctrlKey": False, "shiftKey": False})
        assert data["prevented"] is True
        assert data["navigatedTo"] == "unset"  # new-tab path, same-tab nav untouched
