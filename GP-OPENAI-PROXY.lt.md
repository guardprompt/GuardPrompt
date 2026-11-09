<p align="center">🌐 <a href="GP-OPENAI-PROXY.md">English</a> · <b>Lietuvių</b></p>

# GuardPrompt OpenAI šliuzas (`gp-openai-proxy`)

**OpenAI-compatible** šliuzas į **OpenRouter** su **grįžtama** anonimizacija — įrankiams,
kalbantiems OpenAI `/v1/chat/completions` protokolu (Oracle SQL Developer / SQLcl,
VS Code + Continue ar bet koks OpenAI klientas). Leidžia, pvz., PL/SQL programuotojams
naudoti pažangų LLM, kad nei viena jautri reikšmė neišeitų atviru tekstu.

Tai **atskiras servisas** nuo Claude šliuzo ([GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md)):
Claude Code / VS Code devai toliau naudoja `gp-claude-proxy` portą 8006 nepakeistą;
OpenAI-protokolo klientai — `gp-openai-proxy` portą 8013.

## Ką daro

```
klientas  ──►  maskavimas (grįžtamas, per-owner vault)  ──►  OpenRouter  ──►  atstatymas  ──►  klientas
```

1. Gauna OpenAI pokalbio užklausą.
2. **Fiksuoja modelį** į `OPENROUTER_MODEL` — kliento nurodytas ignoruojamas, tad
   niekas nesirenka brangaus.
3. **Grįžtamai** pseudonimizuoja žinutes: jautrios **reikšmės** tampa `GP_…` tokenais
   (vardai, asmens kodai, paštai, IBAN, BDAR 9/10 str., paslaptys…), o įprasti
   identifikatoriai (lentelių/stulpelių vardai, raktažodžiai) lieka nepaliesti.
4. Siunčia į OpenRouter naudodamas OpenRouter raktą, **skaitomą iš OpenWebUI konfigo**
   (vienas raktas rotuoti, ne du).
5. **Atstato** tikras reikšmes atsakyme (ir non-stream, ir SSE), tad atsakymas
   referuoja tikrus programuotojo identifikatorius, ne `GP_…`.
6. Įrašo **kas-ką-siuntė audito eilutę** (jau anonimizuotą) į `gp_audit` (BDAR 30 str.).

Maskavimas **fail-closed**: jei anonimizatorius/NER nepasiekiamas — užklausa blokuojama,
o ne siunčiama neapsaugota.

Kodėl grįžtamas (vs vienpusis OpenWebUI filtras): kodui užmaskuotas lentelės ar
stulpelio vardas, kuris negrįžtų, padarytų atsakymą nenaudingą. Čia vault jį atstato.

## Galiniai taškai

| Metodas | Kelias | Pastabos |
|---------|--------|----------|
| POST | `/v1/chat/completions` | OpenAI pokalbis, stream ir non-stream |
| GET | `/v1/models` | Rodo vienintelį fiksuotą modelį |
| GET | `/health` | `{"status":"ok","model":"<fiksuotas>"}` |

Auth: `Authorization: Bearer <raktas>`, kur raktas — vienas iš `GP_OAI_PROXY_KEYS`
(tuščia ⇒ atvira, remiasi tinklo izoliacija).

## Konfigūracija (`.env`)

| Kintamasis | Reikšmė |
|------------|---------|
| `OPENROUTER_MODEL` | **Fiksuotas** modelis (vienintelis naudojamas). Būtinas, pvz. `qwen/qwen-2.5-coder-32b-instruct`. |
| `OPENROUTER_BASE_URL` | OpenAI-compatible bazė. Numatyta `https://openrouter.ai/api/v1`. |
| `OPENROUTER_API_KEY` | Neprivalomas raktas. **Tuščias ⇒ skaitomas iš OpenWebUI** (`openrouter` ryšys). |
| `GP_OAI_PROXY_KEYS` | Bearer raktai klientams (per kablelį). Tuščia ⇒ atvira. |
| `GP_TOKEN_SECRET` | Tokenų išvedimo paslaptis (bendra su Claude proxy; owner-scoped, vault'ai atskiri). |
| `GP_DB_URL` | Postgres vault DSN (token → tikra reikšmė). Ta pati DB kaip Claude proxy. |
| `GP_FAIL_CLOSED` | `true` (numatyta) ⇒ blokuoti, jei maskavimas nepavyko. |
| `GP_AUDIT_ENABLED` | `true` (numatyta) ⇒ įrašyti anonimizuotą naują turn'ą į `gp_audit`. |

OpenRouter raktas ateina iš OpenWebUI konfigo lentelės (`openai.api_base_urls` /
`openai.api_keys`, atitikmuo per `OPENROUTER_KEY_MATCH`, numatyta `openrouter`) — tad
OpenRouter ryšį nustatyk **vieną kartą OpenWebUI'e** (Admin → Settings → Connections).

## Tinklas ir sauga

Portas prijungtas prie `0.0.0.0` (LAN-pasiekiamas), kad IDE klientai jungtųsi
tiesiogiai. Kadangi jis **neša kredencialus ir pasiekia plaintext vault**, apsaugok:

- nustatyk `GP_OAI_PROXY_KEYS` ir kiekvienam devui duok raktą (atleidžiant — atšauki vieną raktą);
- **firewall** portą 8013 tik į patikimus dev subnetus;
- vault (`gp_vault`) laiko tikras reikšmes — riboк DB rolę, remkis TTL prune (`GP_VAULT_TTL_DAYS`, numatyta 30).

## Kliento nustatymas

Veikia bet koks OpenAI-compatible klientas, leidžiantis custom base URL. Modelio laukas
**ignoruojamas** (fiksuotas serveryje), tad rašyk bet ką.

| Nustatymas | Reikšmė |
|------------|---------|
| Base URL | `http://<host>:8013/v1` |
| API raktas | vienas iš `GP_OAI_PROXY_KEYS` |
| Modelis | bet kas (fiksuota `OPENROUTER_MODEL`) |

**VS Code + Continue** (`~/.continue/config.json`) — patikrintas kelias:

```json
{
  "models": [{
    "title": "GuardPrompt (OpenRouter)",
    "provider": "openai",
    "apiBase": "http://YOUR_HOST:8013/v1",
    "apiKey": "YOUR_GP_OAI_PROXY_KEY",
    "model": "pinned"
  }]
}
```

**Oracle SQL Developer / SQLcl:** naudok SQLcl 24.3+ (ar IDE AI plėtinį), priimantį
custom OpenAI base URL + raktą. Klasikinis SQL Developer be tokio nustatymo į custom
OpenAI endpointą nukreipti negali — tada VS Code + Continue arba OpenWebUI naršyklėje.

## Diegimas

Siunčiamas pyarmor-obfuskuotas (yra `publish.ps1` sąraše). Serveryje:

```bash
# 1. .env: modelis + klientų raktai
#    OPENROUTER_MODEL=qwen/qwen-2.5-coder-32b-instruct
#    GP_OAI_PROXY_KEYS=<sugeneruotas raktas>
# 2. build + start (saugu shared host'e — jokių -v / --remove-orphans)
docker compose up -d --build gp-openai-proxy
```

Įsitikink, kad **OpenRouter ryšys yra OpenWebUI'e** (kad raktą būtų iš kur skaityti),
arba nustatyk `OPENROUTER_API_KEY` tiesiogiai.

## Patikra

```bash
# health + fiksuotas modelis
curl -s http://localhost:8013/health

# pokalbis (pridėk -H "Authorization: Bearer <raktas>", jei GP_OAI_PROXY_KEYS nustatytas)
curl -s http://localhost:8013/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"Ka daro SELECT ename FROM emp WHERE ename='"'"'Jonas Petraitis'"'"';?"}]}'
```

Patikrink, kad į OpenRouter nuėjo **maskuota** (auditas saugo anonimizuotą turn'ą):

```bash
docker exec postgres psql -U <user> -d <db> \
  -c "SELECT ts, model, left(content,150) FROM gp_audit ORDER BY ts DESC LIMIT 3;"
```

`content` turi rodyti `GP_…` tokenus (ne tikrą vardą) — įrodymas, kad maskuota prieš
išsiuntimą; o klientas mato atstatytas tikras reikšmes.

## Ryšys su kitais keliais

| | `gp-openai-proxy` | OpenWebUI `/api/chat/completions` | `gp-claude-proxy` |
|---|---|---|---|
| Protokolas | OpenAI → OpenRouter | OpenAI (OWUI) | Anthropic → Anthropic |
| Anonimizacija | **grįžtama** (vault) | vienpusis filtras | grįžtama (vault) |
| Modelis | **env-fiksuotas** | per OWUI prieigą | Claude modeliai |
| Kam | SQL Developer / OpenAI įrankiai | naršyklė / ad-hoc | Claude Code / VS Code |
