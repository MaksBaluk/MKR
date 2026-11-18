"""Smoke test of the running Docker stack (PostgreSQL): resume, idempotent answer, stale version, isolation.
Creates two throwaway test users (`*@example.test`) in the dev database; makes no LLM call that matters (LLM may be down:
the product then asks bank questions and stores answers UNGRADED, which is exactly the failure path being checked)."""
from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
results: list[dict] = []


def rec(name, ok, detail=""):
    results.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})


def main() -> int:
    stamp = int(time.time())
    c = httpx.Client(base_url=BASE, timeout=120)
    def user(tag):
        body = {"email": f"ch4-{tag}-{stamp}@example.test", "password": f"Smoke-{stamp}-pw!", "display_name": f"ch4 {tag}"}
        r = c.post("/auth/register", json=body)
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['token']}"}
    a, b = user("a"), user("b")
    p = c.post("/profiles", headers=a, json={"name": "smoke", "track": "python", "target_level": "middle", "years_experience": 3})
    rec("profile created on PostgreSQL", p.status_code == 201, str(p.status_code)); pid = p.json()["id"]
    att = c.post(f"/profiles/{pid}/attempts", headers=a); att.raise_for_status(); iv = att.json()
    q = c.post(f"/interviews/{iv['id']}/next-question", headers=a, json={"version": iv["version"]}).json()
    turn = q["turn"]
    state = c.get(f"/interviews/{iv['id']}", headers=a).json()
    rec("resume: open interview returns the pending question from the server", state.get("pending_turn", {}).get("id") == turn["id"])
    stale = c.post(f"/interviews/{iv['id']}/next-question", headers=a, json={"version": iv["version"]})
    rec("stale version rejected (409)", stale.status_code == 409, str(stale.status_code))
    body = {"turn_id": turn["id"], "text": "Працював із цим на проєкті.", "version": q["version"], "idempotency_key": f"smoke-{stamp}"}
    r1 = c.post(f"/interviews/{iv['id']}/answers", headers=a, json=body)
    r2 = c.post(f"/interviews/{iv['id']}/answers", headers=a, json=body)
    rec("answer accepted", r1.status_code == 200, f"{r1.status_code} {r1.json().get('assessment_status')}")
    rec("replay with the same idempotency key returns the same result", r2.status_code == 200 and r1.json().get("version") == r2.json().get("version"),
        f"{r2.status_code} v{r1.json().get('version')} vs v{r2.json().get('version')}")
    again = c.get(f"/interviews/{iv['id']}", headers=a).json()
    answered = [t for t in again.get("turns", []) if t.get("answer_text")]
    rec("answer text persisted even when the evaluator is unavailable/ungraded", len(answered) == 1, f"status={r1.json().get('assessment_status')}")
    rec("isolation: another user cannot read the interview", c.get(f"/interviews/{iv['id']}", headers=b).status_code in (403, 404))
    rec("isolation: another user cannot read the profile results", c.get(f"/profiles/{pid}/results", headers=b).status_code in (403, 404))
    json.dump({"base": "http://localhost:8000 (Docker, PostgreSQL)", "results": results}, sys.stdout, ensure_ascii=False, indent=1)
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
