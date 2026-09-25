"""Device-code test runner — test the gp-m365 pipeline against the TEST tenant with a real
delegated Graph token, WITHOUT the add-in SSO and WITHOUT copying tokens by hand.

How it works: it starts a Microsoft "device code" login using the registered app's client
id, prints a URL + short code, you open the URL and sign in as the test user, and it then
runs the full pipeline (Graph search → fetch → injection-scan → anonymize → LLM → restore)
and prints the answer.

Run (inside the docker network so it can reach gliner + OWUI):
    docker compose run --rm \
      -e M365_TENANT_ID=<tenant-id> -e M365_CLIENT_ID=<client-id> \
      gp-m365 python devicelogin.py "Ką man rašė paskutiniame laiške?"

Requirements on the app registration:
  * Authentication → "Allow public client flows" = Yes (device code is a public-client flow;
    no client secret needed for this test).
  * Delegated Graph permissions granted + admin consent (you are Global Admin of the test
    tenant): User.Read, Mail.Read, Files.Read.All, Sites.Read.All.
"""
import sys
import time
import asyncio

import httpx

import config
import graph
import rag

SCOPES = "User.Read Mail.Read Files.Read.All offline_access"


async def _device_token() -> str:
    tenant, client = config.ENTRA_TENANT_ID, config.ENTRA_CLIENT_ID
    if "REPLACE_WITH" in tenant or "REPLACE_WITH" in client:
        print("ERROR: set M365_TENANT_ID and M365_CLIENT_ID (the registered test app).")
        sys.exit(2)

    async with httpx.AsyncClient(timeout=30) as c:
        # 1. Ask for a device code.
        r = await c.post(
            f"{config.AAD_AUTHORITY}/{tenant}/oauth2/v2.0/devicecode",
            data={"client_id": client, "scope": SCOPES})
        r.raise_for_status()
        d = r.json()
        print("\n==================================================")
        print(f"  Atidaryk:  {d['verification_uri']}")
        print(f"  Įvesk kodą: {d['user_code']}")
        print(f"  Prisijunk kaip TEST vartotojas. Laukiu...")
        print("==================================================\n")

        # 2. Poll for the token.
        interval = int(d.get("interval", 5))
        deadline = time.monotonic() + int(d.get("expires_in", 900))
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            t = await c.post(
                f"{config.AAD_AUTHORITY}/{tenant}/oauth2/v2.0/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                      "client_id": client, "device_code": d["device_code"]})
            j = t.json()
            if "access_token" in j:
                print("Prisijungta ✅\n")
                return j["access_token"]
            err = j.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            print(f"ERROR: {err}: {j.get('error_description', '')[:200]}")
            sys.exit(3)
        print("ERROR: baigėsi laikas laukiant prisijungimo.")
        sys.exit(4)


async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "Apibendrink mano naujausius dokumentus."
    token = await _device_token()
    # Feed the delegated token into the pipeline via the DEV bypass path (no OBO needed).
    config.DEV_GRAPH_TOKEN = token
    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
        graph.set_client(client)
        print(f"Klausimas: {question}\n")
        out = await rag.answer(client, question, sso_token="", user_key="devtest")
        print("--- ATSAKYMAS ---")
        print(out.get("answer", ""))
        print(f"\n--- Šaltiniai ({len(out.get('sources', []))}) ---")
        for s in out.get("sources", []):
            print(f"  [{s.get('source')}] {s.get('title')}  {s.get('web_url', '')}")
        print(f"\nLLM iškvietimų: {out.get('llm_calls')}")


if __name__ == "__main__":
    asyncio.run(main())
