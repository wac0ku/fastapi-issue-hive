# 09 — Code Review

> Review-Stand: Commit `84a07a3` (nach der uv-Migration), Juli 2026.
> Bewertungsmaßstab sind gängige Python-/FastAPI-Industriestandards 2026 — siehe
> [Referenztabelle](#referenzen--industriestandard-2026) am Ende.
>
> **Dieses Dokument ist bewusst auf Deutsch**, alle anderen Repo-Inhalte bleiben englisch.
>
> **Nachtrag Juli 2026:** In einer Folgeaufgabe wurden drei Findings behoben — P2-3, P2-7
> und das unten ergänzte P1-5. Sie sind als ✅ **behoben** markiert und mit dem
> tatsächlichen Fix beschrieben, statt sie aus dem Dokument zu entfernen. Alle übrigen
> Findings stehen unverändert offen.

---

## Gesamtbild

Für 689 Zeilen Code ist das hier ein ungewöhnlich sauber geschnittenes Projekt. Die
Trennung Queen/Worker ist konsequent durchgehalten, die Datengrenzen sind vollständig
mit Pydantic typisiert, und die „Graceful Degradation" ohne API-Key ist keine Behauptung,
sondern real: die 12 Tests laufen komplett offline. Das ist mehr Disziplin, als man in
Projekten dieser Größe üblicherweise sieht.

Der Abstand zum Industriestandard liegt fast vollständig **außerhalb** der Fachlogik —
in Tooling, Observability und Testabdeckung der I/O-Ränder. Dazu kommen vier konkrete
Defekte im Code, die unten mit Reproduktion belegt sind.

**Was gut ist**

- Klare Schichtung: `main` (HTTP) → `queen` (Orchestrierung) → `workers` (Entscheidung) →
  `services` (I/O). Keine Zirkularität, keine Logik im Router.
- Die Knowledge-Base (`app/knowledge/connectivity.py`) ist Daten, nicht Code — neue
  Kategorien brauchen keine Codeänderung.
- `asyncio.gather` für die unabhängigen Worker (`queen.py:28-31`) ist genau richtig
  angesetzt: Diagnosis und Research hängen beide nur vom Triage-Ergebnis ab.
- Die Doku ist für die Projektgröße überdurchschnittlich — 8 Kapitel plus Nischen-Research.

**Bewertung nach Dimension**

| Dimension | Stand | Kommentar |
|---|---|---|
| Architektur & Schnitt | 🟢 gut | Worker-Trennung trägt; Erweiterungspunkte sind real |
| Typisierung an den Grenzen | 🟢 gut | Pydantic durchgängig, bis auf zwei Endpunkte (P2-4) |
| Fachlogik / Korrektheit | 🟡 mittel | Triage-Scoring ist nicht kalibriert (P1-2) |
| Robustheit / Fehlerbehandlung | 🔴 schwach | Ein `except Exception: return None` verschluckt alles (P1-3) |
| Observability | 🔴 fehlt | Keine einzige Log-Zeile im gesamten Projekt |
| Security | 🟡 mittel | Ungeprüfte Pfadsegmente, Keys als Klartext-`str` |
| Kostenkontrolle | 🟢 gut | Calls an Triage gekoppelt, Output-Budget hart, Scan begrenzt (P1-5, P2-3, P2-7 behoben) |
| NotebookLM-Integration | 🟢 gut | Einzel-Brief selbsttragend, Korpus dedupliziert (Sonderteil unten) |
| Tests | 🟡 mittel | 24 grüne Tests; `services/github.py` weiterhin ungetestet |
| Tooling (Lint/Format/Typen) | 🔴 fehlt | Kein ruff, kein mypy, kein pre-commit |
| CI/CD | 🟡 mittel | Läuft, prüft aber ausschließlich Tests |
| Packaging | 🟢 gut | Seit der uv-Migration PEP 621 + PEP 735 + Lockfile |

---

## P1 — Kritisch

### P1-1 · `prompts/` ist nicht Teil des Pakets, `PROMPTS_PATH` zeigt ins Leere

**Fundstelle:** `app/services/claude.py:14`

```python
PROMPTS_PATH = Path(__file__).resolve().parents[2] / "prompts" / "templates.json"
```

`parents[2]` ist relativ zur Datei gedacht — aus dem Repo heraus ergibt das korrekt
`<repo>/prompts/templates.json`. Aus einem **installierten** Paket ergibt dieselbe Zeile
`<site-packages>/prompts/templates.json`, und dort liegt nichts: `prompts/` wird von
`[tool.hatch.build.targets.wheel] packages = ["app"]` gar nicht mitgepackt (vorher von
Poetrys `packages = [{include = "app"}]` genauso wenig).

Belegt: Ein Wheel-Build enthält 16 Module unter `app/`, aber keinen einzigen
`prompts/`-Eintrag. Die alte Deployment-Anweisung `pip install .` in
`docs/06-deployment.md` hätte den Claude-Modus also stillschweigend deaktiviert — der
Fehler wäre nicht einmal sichtbar geworden, weil `ask_claude()` jede Exception zu `None`
verschluckt (siehe P1-3) und der Nutzer bloß dauerhaft heuristische Ergebnisse bekommt.

Dass es heute funktioniert, ist Layout-Zufall: Sowohl lokal als auch im Container ist das
Arbeitsverzeichnis das Verzeichnis über `app/`.

**Vorschlag** — Prompts als Package-Data führen und über `importlib.resources` laden:

```python
# app/prompts/templates.json  (Datei nach app/ verschieben)
from importlib.resources import files
from functools import lru_cache
import json

@lru_cache(maxsize=1)
def _templates() -> dict:
    return json.loads(
        files("app.prompts").joinpath("templates.json").read_text(encoding="utf-8")
    )

def load_prompt(worker: str) -> dict:
    return _templates()[worker]
```

Dazu in `pyproject.toml` sicherstellen, dass die JSON mitgeht (bei hatchling reicht es,
dass sie unter `app/` liegt). Danach kann das Dockerfile die App regulär installieren
(`uv sync --locked --no-dev --no-editable`) statt sie aus dem `WORKDIR` zu serven — der
entsprechende Kommentar im `Dockerfile` verweist genau auf dieses Finding.

*Nebeneffekt:* Der `lru_cache` behebt zugleich P2-2.

---

### P1-2 · Triage-Scoring ist nicht kalibriert

**Fundstelle:** `app/hive/workers/triage.py:14`, `:31`

```python
MIN_CONFIDENCE = 0.15
...
score = min(1.0, (len(hits) + title_bonus) / (len(category.signals) * 0.75))
```

Drei getrennte Probleme in einer Formel:

**a) Normalisierung über die Kategoriegröße statt über die Evidenzstärke.** Der Nenner ist
die Anzahl der *definierten* Signale. Die Kategorien sind aber unterschiedlich groß —
`cors` hat 6 Signale, `reverse_proxy` 11. Eine kleine Kategorie erreicht dieselbe
Confidence mit weniger Belegen. Wer eine Kategorie um Signale *erweitert*, senkt damit
ihre Confidence — genau der falsche Anreiz für ein Projekt, dessen `CONTRIBUTING.md`
neue Signale ausdrücklich als wertvollsten Beitrag bewirbt.

**b) Der Score sättigt und verliert die Rangfolge.** Durch `min(1.0, …)` landen viele
Treffer auf exakt `1.0`. Reproduziert:

| Eingabe | Treffer | Confidence |
|---|---|---|
| CORS-Issue mit 6 Signaltreffern | 6/6 | **1.0** |
| Proxy-Issue mit 8 Signaltreffern | 8/11 | **1.0** |

Bei `cors` genügen bereits **3 Titeltreffer** (wegen `title_bonus` doppelt gewichtet), um
zu klippen. Oberhalb der Schwelle sagt die Zahl dann nichts mehr aus — obwohl sie als
`confidence` im API-Contract steht und in den Research-Brief geschrieben wird
(`research.py:31`).

**c) Die `0.75` ist eine unkommentierte Magic Number.** Der Kommentar in Zeile 12-13
begründet nur `MIN_CONFIDENCE`, nicht den Nenner.

**Folge — reproduzierbarer False Positive:**

```
Titel: "Add a dark mode toggle to the settings page"
Body:  "Design wants a theme switch. The fade timeout should be 300ms."
→ is_connectivity_issue = True, Kategorie "timeout", confidence 0.33
```

Ein reiner Feature-Request wird als Connectivity-Problem klassifiziert, weil „timeout"
und ein zweites schwaches Signal matchen. Der Kommentar „a single weak signal match can
be coincidence; require a minimum score" hält damit nicht, was er verspricht: bei kleinen
Kategorien reicht **ein** Body-Treffer über die 0.15-Schwelle
(1 / (6 × 0.75) = 0.22).

**Vorschlag** — Signale gewichten statt zählen, und die Schwelle empirisch setzen:

```python
@dataclass(frozen=True)
class Signal:
    pattern: str
    weight: float = 1.0        # starke Signale ("access-control-allow-origin") > 1.0,
                               # generische ("timeout", "127.0.0.1") < 1.0

# Score = gewichtete Trefferpunkte gegen eine feste Sättigungskonstante,
# nicht gegen die Kategoriegröße:
score = 1 - exp(-sum(hit_weights) / SATURATION)
```

Das ist monoton, sättigt sanft statt hart zu klippen, und das Erweitern einer Kategorie
kann eine Confidence nicht mehr senken. Wichtig unabhängig von der konkreten Formel: Ein
kleiner **Fixture-Datensatz** aus echten Issue-Texten mit erwarteter Kategorie, gegen den
Precision/Recall gemessen wird — sonst ist jede Änderung an Signalen oder Schwellen ein
Blindflug. Genau dafür wäre die vorhandene Teststruktur der richtige Ort.

---

### P1-3 · `except Exception: return None` macht den Claude-Modus unbeobachtbar

**Fundstelle:** `app/services/claude.py:26-40`

```python
    try:
        from anthropic import AsyncAnthropic
        template = load_prompt(worker)
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(...)
        return response.content[0].text
    except Exception:
        # Any API problem degrades gracefully to heuristic mode.
        return None
```

Die Absicht — nie hart failen — ist richtig. Die Umsetzung verschluckt aber **alles**, ohne
eine einzige Log-Zeile: ungültiger API-Key, Rate-Limit, Netzwerkfehler, ein `KeyError`
aus `load_prompt()` bei falschem Worker-Namen, ein `AttributeError` aus
`response.content[0].text`, wenn der erste Content-Block kein Text-Block ist (bei
Thinking- oder Tool-Blöcken der Fall). Alles sieht für den Betreiber identisch aus: Die
API antwortet `"enhanced_by_claude": false`, und der Grund ist nicht rekonstruierbar.

Für ein Feature, das Geld kostet und dessen Ausfall stillschweigend die Produktqualität
halbiert, ist das die teuerste Variante von Fehlerbehandlung.

**Vorschlag** — erwartete Fehler von Programmierfehlern trennen und beide loggen:

```python
import logging
from anthropic import AnthropicError

logger = logging.getLogger(__name__)

    except AnthropicError as exc:
        logger.warning("claude_call_failed", extra={"worker": worker, "error": str(exc)})
        return None
    except Exception:
        logger.exception("claude_call_bug", extra={"worker": worker})
        return None   # weiterhin nicht hart failen, aber mit Stacktrace im Log
```

Zusätzlich `/health` um einen Zähler der letzten Fehlschläge ergänzen, damit ein stiller
Dauerausfall überhaupt auffällt.

---

### P1-4 · `frozen=True` schützt die Knowledge-Base nicht

**Fundstelle:** `app/knowledge/connectivity.py:10-18`

```python
@dataclass(frozen=True)
class ConnectivityCategory:
    ...
    signals: list[str] = field(default_factory=list)
```

`frozen=True` verhindert nur die Neuzuweisung von Attributen, nicht die Mutation ihrer
Inhalte. Zwei belegte Konsequenzen:

```python
hash(CATEGORIES[0])              # TypeError: unhashable type: 'list'
CATEGORIES[0].signals.append(x)  # mutiert den globalen Zustand prozessweit
```

`CATEGORIES` ist ein Modul-Level-Singleton, das von drei Workern geteilt wird
(`triage.py:9`, `diagnosis.py:12`, `research.py:13`). Eine versehentliche Mutation an
einer Stelle wirkt prozessweit und über Requests hinweg — in einem
`--workers 2`-Deployment sogar unterschiedlich pro Worker-Prozess. Die Unhashbarkeit
verhindert außerdem, dass Kategorien je als Dict-Key oder Set-Element benutzt werden
können, was bei Caching-Optimierungen sofort aufschlägt.

**Vorschlag:**

```python
signals: tuple[str, ...] = ()
root_causes: tuple[str, ...] = ()
fixes: tuple[str, ...] = ()
doc_links: tuple[str, ...] = ()
```

Damit ist `frozen=True` tatsächlich wirksam und die Instanzen sind hashbar. Die
Aufrufstellen brauchen keine Änderung — `extend()`, Slicing und Iteration funktionieren
über Tupel unverändert.

---

### P1-5 · `research`-Worker bezahlte Claude-Calls für verworfene Issues ✅ **behoben**

*Nachgetragen bei der Token-Analyse.*

**Fundstelle:** `app/hive/workers/research.py:42`

`diagnosis.py:31` koppelte seinen Claude-Call an `triage.is_connectivity_issue`,
`research.py` **nicht**. Für jedes Issue, das die Triage ausdrücklich als „out of scope"
verwarf, wurde trotzdem ein Deep-Dive bezahlt — über ein Problem, zu dem die Triage
gerade festgestellt hatte, dass sie nichts dazu weiß.

Besonders unangenehm, weil es in Repo-Scans der **Regelfall** ist: In einem typischen
Issue-Tracker ist die Mehrheit der Tickets kein Connectivity-Problem. Gemessen für
`/analyze/repo` mit `limit=25` und 15 Out-of-Scope-Issues: **15 überflüssige Calls,
~13.800 Input-Token pro Scan.**

`docs/05-configuration.md` behauptete zu diesem Zeitpunkt bereits, Claude werde „only for
issues that pass triage" aufgerufen — die Doku beschrieb also das beabsichtigte Verhalten,
und der Code wich davon ab.

**Fix:** derselbe Guard wie in `diagnosis.py`. Abgesichert durch
`test_research_skips_claude_for_out_of_scope_issue` (zählt die Aufrufe) plus einen
Gegentest, der belegt, dass Connectivity-Issues weiterhin einen Call auslösen.

---

## P2 — Wichtig

### P2-1 · HTTP-Clients werden pro Request neu gebaut

**Fundstelle:** `app/services/github.py:24`, `app/services/claude.py:30`

```python
async with httpx.AsyncClient(timeout=20) as client:   # pro Aufruf neu
...
client = AsyncAnthropic(api_key=settings.anthropic_api_key)   # pro Aufruf neu, nie geschlossen
```

Beides verhindert Connection-Pooling: Jeder Aufruf zahlt TCP- und TLS-Handshake neu. Bei
`/analyze/repo` mit 25 Issues sind das bis zu 50 Claude-Verbindungsaufbauten für eine
einzige Anfrage. Der `AsyncAnthropic`-Client wird zusätzlich nie geschlossen — sein
interner httpx-Client bleibt bis zum GC offen.

**Vorschlag** — geteilte Clients über den FastAPI-`lifespan`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=20)
    app.state.claude = AsyncAnthropic(...) if get_settings().claude_enabled else None
    yield
    await app.state.http.aclose()

app = FastAPI(..., lifespan=lifespan)
```

Das ist zugleich die Voraussetzung, um die Clients in Tests sauber austauschen zu können
(siehe P3-2).

### P2-2 · `load_prompt()` liest die JSON bei jedem Aufruf neu

**Fundstelle:** `app/services/claude.py:17-19` — `PROMPTS_PATH.read_text()` +
`json.loads()` laufen bei *jedem* Claude-Call, also zweimal pro analysiertem Issue.
Synchroner Datei-I/O im Event-Loop, in einer App, deren Knowledge-Base
`event_loop_blocking` als eigene Diagnosekategorie führt. Behoben durch den `lru_cache`
aus P1-1.

### P2-3 · `max_tokens` in `prompts/templates.json` ist tote Konfiguration ✅ **behoben**

`templates.json` definiert pro Worker `max_tokens` (512 / 512 / 400). Gelesen wurde davon
nichts: `ask_claude()` nutzte ausschließlich sein eigenes Default von `1024`, und kein
Aufrufer übergab den Parameter. Das Output-Budget war damit durchgehend **doppelt so hoch
wie konfiguriert** — bei einem Scan mit 25 Connectivity-Issues 51.200 statt 25.600 Token.

**Fix:** `_resolve_max_tokens(template, explicit)` in `app/services/claude.py` löst in der
Reihenfolge explizites Argument → `templates.json` → Default auf. Die Funktion bekommt das
bereits geladene Template übergeben statt eines Worker-Namens, damit die Auflösung keinen
zusätzlichen Dateizugriff kostet (P2-2 bleibt davon unberührt offen). Abgesichert durch
`tests/test_token_budget.py::test_max_tokens_precedence` und einen Test, der prüft, dass
alle ausgelieferten Templates ein Budget unterhalb des Defaults deklarieren.

### P2-4 · `/health` und `/categories` haben ein leeres OpenAPI-Schema

**Fundstelle:** `app/main.py:23`, `:33`

```python
async def health() -> dict: ...
async def categories() -> list[dict]: ...
```

Nackte `dict`/`list[dict]`-Annotationen erzeugen im generierten Schema ein leeres Objekt.
Für ein Projekt, dessen Verkaufsargument die interaktive `/docs`-Oberfläche ist, sind
das ausgerechnet die beiden Endpunkte, die ein Nutzer zuerst öffnet. Zwei kleine
Response-Models (`HealthResponse`, `CategoryInfo`) in `schemas.py` beheben das und passen
zur sonst durchgehaltenen Pydantic-Disziplin.

### P2-5 · `owner` und `repo` landen ungeprüft in der GitHub-URL

**Fundstelle:** `app/schemas.py:14-15` → `app/services/github.py:21`

```python
owner: str = Field(..., min_length=1, max_length=100)   # keine Zeichenbeschränkung
...
url = f"{API_BASE}/repos/{owner}/{repo}/issues"
```

Validiert wird nur die Länge. Ein Wert wie `../../` oder `foo/bar` verändert den Pfad und
adressiert einen anderen GitHub-Endpunkt als beabsichtigt. Der Schaden ist hier begrenzt
— das Ziel ist eine feste, öffentliche API, und ein gesetztes `GITHUB_TOKEN` würde
allenfalls gegen andere Endpunkte derselben API verwendet — aber es ist genau das Muster,
das in anderem Kontext zu SSRF wird.

**Vorschlag** — GitHubs tatsächliche Namensregeln abbilden:

```python
owner: str = Field(..., pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
repo:  str = Field(..., pattern=r"^[A-Za-z0-9._-]{1,100}$")
```

### P2-6 · API-Keys als `str` statt `SecretStr`

**Fundstelle:** `app/config.py:10-11`. `anthropic_api_key` und `github_token` sind
gewöhnliche Strings. Sobald irgendwo ein `Settings`-Objekt in einen Traceback, ein Log
oder eine Debug-Ausgabe gerät, steht der Key im Klartext darin. `pydantic.SecretStr`
maskiert die Repräsentation und gibt den Wert nur über `.get_secret_value()` heraus —
Standardpraxis und ein Einzeiler:

```python
anthropic_api_key: SecretStr = SecretStr("")
```

### P2-7 · `/analyze/repo` fächert unbegrenzt auf ✅ **behoben**

**Fundstelle:** `app/hive/queen.py:50`

```python
reports = await asyncio.gather(*(self.analyze_issue(issue) for issue in issues))
```

Bis zu 25 Issues (`RepoScanRequest.limit`, `le=25`) × 2 Claude-Calls = 50 parallele
API-Aufrufe aus einem einzigen HTTP-Request, ohne Semaphore und ohne Gesamt-Timeout. Bei
aktivem Claude-Modus ist das ein zuverlässiger Weg ins Rate-Limit; der Client hängt
derweil im offenen Request.

**Fix:** `asyncio.Semaphore(settings.max_concurrent_analyses)` (Default 5) begrenzt die
Gleichzeitigkeit, ein `asyncio.wait_for` mit `settings.scan_timeout_seconds` (Default 120)
den Gesamtlauf; `main.py` übersetzt den Timeout in ein `504` statt in ein `500`.

Bewusst `wait_for` statt des lesbareren `asyncio.timeout()`: letzteres gibt es erst ab
Python 3.11, und `requires-python` verspricht 3.10 — die CI-Matrix testet es.

Abgesichert durch `test_repo_scan_caps_concurrency` (misst die tatsächliche Parallelität)
und `test_repo_scan_times_out_instead_of_hanging`.

### P2-8 · `connectivity_reports` wird berechnet, aber nicht verwendet

**Fundstelle:** `app/hive/queen.py:52-58`

```python
connectivity_reports = [r for r in reports if r.triage.is_connectivity_issue]
return RepoScanReport(
    ...
    connectivity_issues_found=len(connectivity_reports),
    reports=list(reports),          # ungefiltert
)
```

Die gefilterte Liste fließt nur in den Zähler; `reports` enthält alle Issues. Das mag so
gewollt sein, aber der Name legt das Gegenteil nahe, und der API-Contract sagt dazu
nichts. Entweder filtern oder das Feld in `RepoScanReport` dokumentieren
(`Field(description=...)`), damit Aufrufer wissen, dass `reports` auch Nicht-Treffer
enthält.

### P2-9 · Keine Fehler-Middleware, keine Logs, keine Request-ID

Im gesamten Projekt gibt es **keine einzige** `logging`-Nutzung. Es gibt keinen globalen
Exception-Handler; ein unerwarteter Fehler wird zu einer nackten `500` ohne Korrelation
zu irgendeinem Log. `/analyze/repo` gibt Fehler als `HTTPException(502, detail=str(exc))`
zurück (`main.py:55`) — das FastAPI-Default-Format `{"detail": "..."}`, das jeder Client
gesondert parsen muss.

Der aktuelle Standard dafür ist **RFC 9457 Problem Details**
(`application/problem+json` mit `type`/`title`/`status`/`detail`/`instance`), kombiniert
mit strukturiertem Logging (structlog → JSON) und einer Request-ID, die per Middleware in
den Log-Kontext und in den Response-Header wandert. Für eine App dieser Größe reicht:
ein `logging`-Setup in `main.py`, eine Request-ID-Middleware, ein
`@app.exception_handler(Exception)`.

### P2-10 · Keine CORS-Middleware

Die App diagnostiziert CORS-Probleme als Kernkompetenz, konfiguriert selbst aber keine
`CORSMiddleware`. Sobald jemand ein Web-Frontend gegen `/analyze/issue` baut, läuft er
in genau den Fehler, den die eigene Knowledge-Base als ersten CORS-Root-Cause führt
(`app/knowledge/connectivity.py:32`). Optional per
Setting (`allowed_origins: list[str] = []`), damit die Default-Konfiguration restriktiv
bleibt.

### P2-11 · GitHub-Client ohne Retries, Pagination und 429-Behandlung

**Fundstelle:** `app/services/github.py:27-32`

- Kein Retry/Backoff bei `5xx` — ein einzelner GitHub-Schluckauf schlägt direkt zum
  Client durch.
- `429` wird nicht behandelt, `Retry-After` nicht gelesen. GitHubs sekundäres Rate-Limit
  antwortet mit `429`, nicht mit `403`.
- `403` wird pauschal als „rate limit exceeded" gemeldet, obwohl GitHub denselben Code
  auch für fehlende Berechtigungen und blockierte Repos verwendet. Für die Unterscheidung
  gibt es den Header `x-ratelimit-remaining: 0`.
- Keine Pagination: `per_page` wird gesetzt, `Link`-Header aber ignoriert.
- Nach dem PR-Filter (`github.py:36`) können weniger als `limit` Issues zurückkommen —
  die Antwort sagt dann `issues_scanned: 3`, obwohl 5 angefordert waren, ohne Hinweis.

### P2-12 · Version an zwei Stellen gepflegt

`app/__init__.py` setzt `__version__ = "1.0.0"`, `pyproject.toml` ebenfalls. Bei einem
Release driften die auseinander, und `/health` meldet dann die falsche Version.
`importlib.metadata.version("fastapi-issue-hive")` macht `pyproject.toml` zur einzigen
Quelle.

### P2-13 · Regex-Patterns werden nicht vorkompiliert

**Fundstelle:** `app/hive/workers/triage.py:23-30`. Pro Issue laufen ~73 `re.search`-Aufrufe
über Roh-Strings, ein Teil davon zweimal (einmal gegen `text`, einmal gegen den Titel für
den `title_bonus`). Pythons interner Pattern-Cache federt das ab, aber ein
`re.compile` beim Modulimport ist der Standard und macht die Absicht explizit — besonders
weil `triage.run()` synchron im Event-Loop läuft.

---

## P3 — Tooling, Tests, Hygiene

### P3-1 · Kein Lint-, Format- oder Type-Tooling

Es gibt weder ruff noch mypy noch pre-commit — obwohl `.gitignore` bereits `.ruff_cache/`
und `.mypy_cache/` listet, die Absicht also bestand. Das ist 2026 die größte einzelne
Lücke zum Standard: **ruff + mypy** ersetzen zusammen flake8, isort, black, pyupgrade und
pylint.

```toml
[tool.ruff]
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "S", "SIM", "RUF"]
ignore = ["E501"]                       # Formatter regelt Zeilenlänge

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]                    # assert ist in Tests erwünscht

[tool.mypy]
python_version = "3.10"
strict = true
```

`ANN` (Annotationsregeln) bewusst weglassen, wenn mypy `strict` läuft — sonst meldet man
dieselbe Sache doppelt. Dazu ein `.pre-commit-config.yaml` mit `ruff check --fix` **vor**
`ruff format` (die Reihenfolge ist wichtig) und mypy als dritter Hook.

### P3-2 · Beide I/O-Module sind vollständig ungetestet

Die 12 Tests decken Triage, Queen-Pipeline und die HTTP-Schicht ab — aber:

- **`app/services/github.py`: kein einziger Test.** Weder der 404-, 403- noch der
  generische Fehlerpfad, und auch nicht der PR-Filter (`github.py:36`), obwohl das die
  Stelle ist, an der die Issue-Zählung stillschweigend abweichen kann.
- **`app/services/claude.py`: kein einziger Test.** Der gesamte Claude-Pfad ist nie
  ausgeführt worden. `enhanced_by_claude` wird ausschließlich als `False` geprüft
  (`test_queen.py:23`). Ein Tippfehler im Claude-Zweig fiele erst in Produktion auf — und
  dort wegen P1-3 auch nur als „ist halt heuristisch".
- **`/analyze/repo`: kein Test.**

Das sind exakt die Module mit externem I/O, also die mit dem höchsten Testwert. Mittel
der Wahl ist `respx` oder `httpx.MockTransport`:

```python
@pytest.mark.asyncio
async def test_fetch_open_issues_filters_pull_requests(respx_mock):
    respx_mock.get(url__regex=r".*/repos/o/r/issues").respond(
        200, json=[{"title": "real issue", "body": "x"},
                   {"title": "a PR", "pull_request": {"url": "..."}}]
    )
    issues = await fetch_open_issues("o", "r", limit=5)
    assert [i.title for i in issues] == ["real issue"]
```

Dazu Coverage messen und ein Minimum erzwingen (`pytest-cov`, `--cov-fail-under=80`) —
ohne Zahl verfällt Testabdeckung erfahrungsgemäß.

Kleinigkeit am Rande: `tests/test_api.py:5` legt den `TestClient` auf Modulebene an statt
als Fixture. Das teilt Zustand zwischen Tests und verhindert, dass ein `lifespan`
(P2-1) sauber pro Test hoch- und runtergefahren wird.

### P3-3 · CI prüft ausschließlich Tests

`.github/workflows/ci.yml` läuft nach der uv-Migration sauber, deckt aber nur `pytest` ab.
Was fehlt:

- **Lint und Typecheck** als eigene Jobs (`uv run ruff check`, `uv run mypy app`).
- **`permissions:`** — ohne den Block bekommt `GITHUB_TOKEN` die Repo-Defaultrechte.
  `permissions: contents: read` auf Workflow-Ebene ist Least-Privilege-Standard.
- **`concurrency:`** — sonst laufen bei schneller Push-Folge veraltete Jobs weiter.
- **Dependency-Audit**: `uv run --with pip-audit pip-audit` fängt bekannte CVEs, bevor
  sie deployt werden.
- **Matrix-Lücke**: getestet wird 3.10 und 3.12, `requires-python = ">=3.10"` verspricht
  aber auch 3.11 und 3.13.
- **Trigger**: nur `main`/`master`. Feature-Branches laufen erst, wenn ein PR offen ist.

Ergänzend zum Repo, nicht zur CI: kein Dependabot/Renovate, kein `SECURITY.md`, kein
`CODEOWNERS`, keine Issue-/PR-Templates, kein `CHANGELOG.md`, kein `py.typed`.

### P3-4 · Dockerfile-Härtung offen

Die uv-Migration hat den Build auf Multi-Stage umgestellt, aber bewusst nichts an der
Sicherheitskonfiguration geändert. Offen bleiben:

- **Läuft als `root`.** Ein `USER`-Wechsel auf einen unprivilegierten Account ist der
  wirksamste Einzelfix.
- **Kein `HEALTHCHECK`**, obwohl mit `/health` ein passender Endpunkt existiert.
- **Kein `.dockerignore`.** Aktuell unkritisch, weil alle `COPY`-Pfade explizit sind, aber
  eine Zeile `COPY . .` genügt, um `.env` und `.git` mit ins Image zu ziehen.
- **Base-Image nicht per Digest gepinnt** (`python:3.12-slim` statt `python:3.12-slim@sha256:…`)
  — reproduzierbare Builds brauchen den Digest.

### P3-5 · Kleinere Doku- und Konfigurationsfehler

| Fundstelle | Problem |
|---|---|
| `app/hive/workers/research.py:6` | Verweist auf `docs/notebooklm-workflow.md`; die Datei heißt `docs/07-notebooklm-workflow.md` |
| `.env.example` | `MAX_ISSUES_PER_REPO` fehlt, obwohl in `config.py:13` vorhanden und in `docs/05-configuration.md` dokumentiert |
| `app/hive/queen.py:3-4` | Verweist auf `config/swarm-config.json` aus einem anderen Projekt — im Repo nicht vorhanden |

### P3-6 · Kommende Breaking Changes im Abhängigkeitsbaum

Die Neuauflösung des Lockfiles bei der uv-Migration hat die Abhängigkeiten auf aktuellen
Stand gehoben (u.a. FastAPI 0.140.8, Starlette 1.3.1, Pydantic 2.13.4, pytest 9.1.1).
Dabei zeigt sich eine Warnung, die bald zum Fehler wird:

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

Betrifft `tests/test_api.py` über `fastapi.testclient`. Solange die Testsuite Warnungen
nicht als Fehler behandelt, fällt so etwas erst auf, wenn die Deprecation entfernt wird.
Empfehlung: `filterwarnings = ["error"]` in `[tool.pytest.ini_options]`, mit gezielten
Ausnahmen für Fremdwarnungen. Ebenfalls dort setzen:
`asyncio_default_fixture_loop_scope = "function"` — pytest-asyncio warnt sonst über den
nicht gesetzten Default.

---

## Sonderteil: Taugt die NotebookLM-Integration? ✅ **verbessert**

Die Grundidee ist richtig. NotebookLM hat keine öffentliche API, also ist „erzeuge gute
Quelldokumente" der einzig verfügbare Integrationsweg — und ein Werkzeug, das ohnehin
Triage-Verdikt, Hintergrund und Doku-Links zusammenträgt, ist dafür gut aufgestellt.

Für den **Einzelfall** funktioniert das auch: Ein Brief ist selbsttragend, und
NotebookLM-Antworten sind nur so gut wie ihre Quellen.

Für den **Korpusfall** brach es — und ausgerechnet den bewarb `docs/07` selbst unter
„Niche research at scale" als Hauptanwendung. Gemessen an einem Connectivity-Brief:

| Anteil | Inhalt |
|---|---|
| **59%** | Knowledge-Base-Boilerplate, identisch in jedem Brief derselben Kategorie |
| **18%** | Prompt-Block, wörtlich identisch in **jedem** Brief |
| **17%** | tatsächlich issue-spezifisch |

Bei Out-of-Scope-Issues kippt das Verhältnis vollends: 54% Prompt-Block, 34% Eigeninhalt.
Wer 20 Briefs in ein Notebook lädt, füllt es zu rund drei Vierteln mit Dubletten. Auf die
von der Doku selbst vorgeschlagene Frage *„Which failure categories cluster most often?"*
sieht NotebookLM dieselben Root-Cause-Absätze dutzendfach — es gruppiert dann Wiederholung
statt Evidenz. Erschwerend: Für den beschriebenen Workflow gab es **gar keinen Endpunkt**,
die Doku zeigte eine manuelle `curl | python -c`-Extraktion pro Issue.

**Umsetzung:** Der Scan zerfällt jetzt in den Teil, der sich ändert, und den, der nicht:

- `POST /analyze/repo/corpus` — ein Dokument pro Scan: Häufigkeitstabelle der Kategorien
  (die direkte Antwort auf die Clustering-Frage), pro Issue nur Titel, Link, Triage-Verdikt,
  gerankte Kategorien und ggf. Claude-Notizen, und der Prompt-Block genau **einmal**.
- `GET /knowledge/export` — die Knowledge-Base als eigene, wiederverwendbare Quelle.

Beide liefern `text/markdown` direkt, der JSON-Extraktionsschritt entfällt.

Gemessen an 20 Issues gegenüber dem bisherigen Aneinanderhängen der Briefs:

| | Zeichen | ~Token |
|---|---|---|
| bisher: 20 Briefs | 22.569 | 6.100 |
| neu: Korpus | 5.417 | 1.464 |
| neu: Knowledge-Base (einmalig, wiederverwendbar) | 8.539 | 2.308 |

Der Korpus allein ist **76% kleiner**; beide Quellen zusammen 39%, und die
Knowledge-Base amortisiert sich über jeden weiteren Scan im selben Notebook. Der
KB-Fließtext taucht im Korpus **0×** statt 4× auf, der Prompt-Block **1×** statt 20×.

**Einzel-Briefs bleiben bewusst unverändert** — ihre Selbsttragfähigkeit ist in `docs/07`
ausdrücklich als Designziel benannt und für den Einzelfall auch die richtige Wahl.

### Was hier *nicht* geholfen hätte

Naheliegend, aber für dieses Projekt unwirksam: den Antwortstil zu komprimieren
(„caveman-Prompting" und Verwandtes). Die Calls sind One-Shot-Aufrufe mit `max_tokens`-Cap,
kein Chat; der Diagnosis-System-Prompt verbietet Präambeln bereits wörtlich; und die
System-Prompts sind 71–128 Token groß, ihre Kompression also irrelevant. **Anthropic
Prompt-Caching greift hier ebenfalls nicht** — es verlangt ein Präfix von mindestens 1024
Token. Der Hebel lag auf der Anzahl der Calls (P1-5) und einem harten Output-Budget
(P2-3), nicht am Formulierungsstil.

---

## Referenzen — Industriestandard 2026

| Thema | Standard / Werkzeug | Stand im Projekt |
|---|---|---|
| Paketverwaltung | [uv](https://docs.astral.sh/uv/), PEP 621 + [PEP 735](https://peps.python.org/pep-0735/), Lockfile im VCS | ✅ seit dieser Migration |
| Lint & Format | [ruff](https://docs.astral.sh/ruff/) statt flake8/black/isort/pyupgrade | ❌ P3-1 |
| Typprüfung | [mypy](https://mypy.readthedocs.io/) `strict` (alternativ ty/pyright) | ❌ P3-1 |
| Pre-Commit | [ruff-pre-commit](https://github.com/astral-sh/ruff-pre-commit), Lint vor Format | ❌ P3-1 |
| Container | [uv Docker-Guide](https://docs.astral.sh/uv/guides/integration/docker/): Multi-Stage, Cache-Mounts, non-root | 🟡 Multi-Stage ✅, non-root ❌ (P3-4) |
| CI | [setup-uv](https://github.com/astral-sh/setup-uv) mit Cache, `--locked`, Least-Privilege-`permissions` | 🟡 P3-3 |
| Fehlerformat | [RFC 9457 Problem Details](https://www.rfc-editor.org/info/rfc9457/) statt `{"detail": …}` | ❌ P2-9 |
| Logging | [structlog](https://www.structlog.org/) → JSON, Trace-Korrelation via [OpenTelemetry](https://opentelemetry.io/docs/languages/python/) | ❌ P2-9 |
| Konfiguration | pydantic-settings mit `SecretStr` für Secrets | 🟡 P2-6 |
| HTTP-Clients | Geteilte Clients über `lifespan`, Pooling, Timeouts, Retries | ❌ P2-1, P2-11 |
| Tests | pytest + Coverage-Gate, I/O gemockt via [respx](https://lundberg.github.io/respx/) | 🟡 P3-2 |
| Supply Chain | [pip-audit](https://pypi.org/project/pip-audit/), Dependabot/Renovate, SBOM (CycloneDX) | ❌ P3-3 |

---

## Empfohlene Reihenfolge

**Stufe 1 — Fundament (klein, hoher Hebel).** Erst das Sicherheitsnetz, damit alles
Weitere überprüfbar wird: ruff + mypy + pre-commit einziehen (P3-1), CI um Lint,
Typecheck, `permissions` und `pip-audit` erweitern (P3-3), Logging-Grundgerüst legen
(P2-9). Dabei fallen etliche kleine Findings automatisch mit ab — der lokale Import in
`main.py`, ungenutzte Variablen, tote Konfiguration.

**Stufe 2 — Die vier P1-Defekte.** `tuple` statt `list` in der Knowledge-Base (P1-4,
Zweizeiler), Fehlerbehandlung in `claude.py` differenzieren (P1-3), `prompts/` als
Package-Data über `importlib.resources` (P1-1, erlaubt danach die Dockerfile-Vereinfachung).
Das Triage-Scoring (P1-2) zuletzt und **nur mit vorher aufgebautem Fixture-Datensatz** —
ohne Messgröße ist jede Änderung an der Formel eine Wette.

**Stufe 3 — Tests an den I/O-Rändern.** `services/github.py` mit respx abdecken (P3-2) —
das einzige Modul ohne jeden Test. Für `services/claude.py` existiert inzwischen ein Test
der Budget-Auflösung, der eigentliche API-Pfad ist aber weiterhin ungetestet.
Coverage-Gate setzen. Erst damit werden die Änderungen aus Stufe 2 gegen Regressionen
abgesichert.

**Stufe 4 — Produktionsreife.** Geteilte Clients über `lifespan` (P2-1),
RFC-9457-Fehlerformat, Response-Models für `/health` und `/categories` (P2-4),
Docker-Härtung (P3-4).

Die Doku-Fixes aus P3-5 sind Minutensache und passen in jede der Stufen.
