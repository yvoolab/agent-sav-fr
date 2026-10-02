#!/usr/bin/env python3
"""Agent SAV e-mail : lit un e-mail client, choisit ses outils, prépare un brouillon.

Trois outils, un seul modèle, une boucle courte :
  chercher_commande  -> base de commandes (SQLite, chargée depuis data/commandes.csv)
  chercher_faq       -> recherche lexicale BM25 dans data/faq.md (aucune base vectorielle)
  transferer_humain  -> escalade vers un conseiller, avec motif et priorité
Le brouillon n'est jamais envoyé : un conseiller le relit. Python 3.9+, stdlib seule.
"""
import argparse, csv, json, math, os, re, sqlite3, sys, time, unicodedata, urllib.error, urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
MAX_STEPS = 6

SYSTEM = """Tu es l'agent du service client de Maison Ardoise, boutique en ligne (fictive) de thé et d'articles en grès. Tu traites un e-mail client et tu prépares un brouillon de réponse qu'un conseiller relira avant envoi.

Règles :
1. N'invente jamais. Statut, dates, suivi et montants viennent de chercher_commande ; délais, frais et politiques viennent de chercher_faq. Ne promets aucun délai, montant ou geste qui ne figure pas dans un résultat d'outil. Si l'information manque, dis-le ou transfère.
2. Dès que l'e-mail porte sur une commande précise, appelle chercher_commande (par numéro, sinon par l'e-mail de l'expéditeur), y compris avant un transfert : le conseiller doit recevoir un dossier vérifié.
3. Pour toute question de politique (livraison, retour, remboursement, annulation, facture...), appelle chercher_faq avant de répondre.
4. Appelle transferer_humain, puis rédige un court accusé de réception, quand : menace juridique ou mise en demeure ; demande liée aux données personnelles (RGPD) ; client qui exige un responsable ; commande introuvable ; colis marqué livré mais non reçu ; e-mail de l'expéditeur différent de celui de la commande (ne divulgue alors aucun détail de la commande) ; geste commercial ou remboursement hors politique ; cas non couvert par la FAQ.
5. Réponds dans la langue de l'e-mail du client (anglais si le client écrit en anglais), même si les outils renvoient du français. Ton clair, courtois, direct, sans formules creuses. Signe « Le service client Maison Ardoise ».
6. Tu ne peux ni joindre de fichier, ni modifier ou annuler une commande toi-même : écris ce que le conseiller va faire après relecture, ou renvoie vers l'espace client.
7. Ta réponse finale contient uniquement le texte de l'e-mail, sans commentaire."""

TOOLS = [
    {"type": "function", "function": {
        "name": "chercher_commande",
        "description": "Cherche une commande par numéro (ex. CMD-1042) ou par e-mail client. Renvoie statut, articles, montant, transporteur, suivi.",
        "parameters": {"type": "object", "properties": {
            "numero": {"type": "string", "description": "Numéro de commande, ex. CMD-1042"},
            "email": {"type": "string", "description": "E-mail du client"}}}}},
    {"type": "function", "function": {
        "name": "chercher_faq",
        "description": "Recherche dans la FAQ et les conditions de vente de la boutique. Renvoie les 3 passages les plus pertinents.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "La question, en quelques mots"}},
            "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "transferer_humain",
        "description": "Transfère le dossier à un conseiller humain. À utiliser pour les cas listés dans les règles.",
        "parameters": {"type": "object", "properties": {
            "motif": {"type": "string", "description": "Pourquoi un humain doit reprendre, en une phrase"},
            "priorite": {"type": "string", "enum": ["normale", "haute"]}},
            "required": ["motif", "priorite"]}}},
]

# ---------- données ----------

def load_orders() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    with open(ROOT / "data" / "commandes.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0])
    db.execute(f"CREATE TABLE commandes ({', '.join(cols)})")
    db.executemany(f"INSERT INTO commandes VALUES ({', '.join('?' * len(cols))})",
                   [[r[c] for c in cols] for r in rows])
    return db

DB = load_orders()

STOP = set("le la les un une des de du d l et ou a au aux en dans sur pour par avec mon ma mes ce cet cette est je j vous nous il elle on que qui quoi comment quel quelle quels quelles ne pas plus se s y the a of to my is".split())

def tokens(text: str) -> list:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    # Racinisation minimale : pluriel et e final (cassée, cassé, casses -> cass).
    return [re.sub(r"(es|s|e+)$", "", w) if len(w) > 3 else w
            for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 1]

def load_faq() -> list:
    text = (ROOT / "data" / "faq.md").read_text(encoding="utf-8")
    return [("## " + s).strip() for s in text.split("\n## ")[1:]]

FAQ = load_faq()
FAQ_TOK = [tokens(s) for s in FAQ]

def bm25(query: str, k: int = 3, k1: float = 1.5, b: float = 0.75) -> list:
    """BM25 classique (Robertson). Corpus de ~20 sections : pas besoin d'index."""
    q = tokens(query)
    n, avg = len(FAQ_TOK), sum(map(len, FAQ_TOK)) / len(FAQ_TOK)
    df = Counter(w for doc in FAQ_TOK for w in set(doc))
    scores = []
    for i, doc in enumerate(FAQ_TOK):
        tf, s = Counter(doc), 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(doc) / avg))
        scores.append((s, i))
    return [FAQ[i] for s, i in sorted(scores, reverse=True)[:k] if s > 0]

# ---------- outils ----------

def chercher_commande(numero: str = "", email: str = "") -> dict:
    if numero:
        rows = DB.execute("SELECT * FROM commandes WHERE upper(numero) = upper(?)", (numero.strip(),)).fetchall()
    elif email:
        rows = DB.execute("SELECT * FROM commandes WHERE lower(email) = lower(?)", (email.strip(),)).fetchall()
    else:
        return {"erreur": "Fournir un numéro ou un e-mail."}
    return {"commandes": [dict(r) for r in rows]} if rows else {"commandes": [], "note": "Aucune commande trouvée."}

def chercher_faq(question: str) -> dict:
    return {"passages": bm25(question) or ["Aucun passage pertinent dans la FAQ."]}

def transferer_humain(motif: str, priorite: str = "normale") -> dict:
    return {"transfere": True, "ticket": f"ESC-{abs(hash(motif)) % 10000:04d}",
            "consigne": "Rédige maintenant un court accusé de réception pour le client, sans promesse ni détail de commande non vérifié."}

IMPLS = {"chercher_commande": chercher_commande, "chercher_faq": chercher_faq, "transferer_humain": transferer_humain}

# ---------- boucle agent ----------

def llm(messages: list) -> dict:
    body = json.dumps({"model": MODEL, "messages": messages, "tools": TOOLS, "temperature": 0}).encode()
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions", body, {
        "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json", "User-Agent": "agent-sav-fr"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == 4:
                raise RuntimeError(f"LLM HTTP {e.code}: {e.read()[:300]!r}")
            time.sleep(float(e.headers.get("retry-after") or 2 ** attempt))

def short(result: dict) -> str:
    if "commandes" in result:
        c = result["commandes"]
        return "aucune commande" if not c else "; ".join(f"{x['numero']} · {x['statut']}" for x in c)
    if "passages" in result:
        return " | ".join(p.splitlines()[0][3:] for p in result["passages"])
    if result.get("transfere"):
        return "ticket " + result["ticket"]
    return json.dumps(result, ensure_ascii=False)[:120]

def traiter(email: str, trace=print) -> dict:
    """Traite un e-mail. Renvoie {action, outils, motif, brouillon}."""
    system = SYSTEM + f"\n\nDate du jour : {date.today().isoformat()}."
    messages = [{"role": "system", "content": system}, {"role": "user", "content": email}]
    appels, motif = [], None
    for _ in range(MAX_STEPS):
        msg = llm(messages)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"action": "escalade" if motif else "brouillon", "outils": appels,
                    "motif": motif, "brouillon": (msg.get("content") or "").strip()}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = IMPLS[name](**args)
            except (KeyError, TypeError, json.JSONDecodeError) as e:
                result = {"erreur": f"appel invalide : {e}"}
            appels.append(name)
            if name == "transferer_humain":
                motif = args.get("motif")
            trace(f"  → {name}({json.dumps(args, ensure_ascii=False)})")
            trace(f"  ← {short(result)}")
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, ensure_ascii=False)})
    return {"action": "escalade", "outils": appels, "motif": f"limite de {MAX_STEPS} étapes atteinte", "brouillon": ""}

def format_email(e: dict) -> str:
    return f"De : {e['de']}\nObjet : {e['objet']}\n\n{e['corps']}"

def main():
    p = argparse.ArgumentParser(description="Agent SAV e-mail (démo).")
    p.add_argument("fichier", nargs="?", help="E-mail en texte brut (sinon : entrée standard)")
    p.add_argument("--exemple", type=int, help="Traiter l'e-mail n° N du jeu d'évaluation")
    a = p.parse_args()
    if not API_KEY:
        sys.exit("Définir GROQ_API_KEY (ou LLM_API_KEY + LLM_BASE_URL pour un autre fournisseur compatible OpenAI).")
    if a.exemple:
        cas = json.loads((ROOT / "data" / "evals.json").read_text(encoding="utf-8"))
        email = format_email(cas[a.exemple - 1])
    else:
        email = Path(a.fichier).read_text(encoding="utf-8") if a.fichier else sys.stdin.read()
    print(email, "\n" + "─" * 60)
    r = traiter(email)
    print("─" * 60)
    print(f"ACTION : {r['action'].upper()}" + (f" — {r['motif']}" if r["motif"] else ""))
    print("BROUILLON (à relire avant envoi) :\n")
    print(r["brouillon"])

if __name__ == "__main__":
    main()
