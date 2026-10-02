# Agent SAV e-mail

Un agent IA qui lit les e-mails du service client, vérifie lui-même la commande et les conditions de vente, puis prépare un brouillon de réponse — ou transmet le dossier à un humain quand il le faut. Il n'envoie rien : un conseiller relit chaque brouillon.

Démonstration sur une boutique fictive (Maison Ardoise, thé et articles en grès). *English version below.*

![Démo : l'agent traite deux e-mails](demo/demo.gif)

## Ce qu'il fait

Pour chaque e-mail, le modèle choisit ses outils, dans l'ordre qu'il juge utile :

| Outil | Rôle | Source |
|---|---|---|
| `chercher_commande` | statut, articles, montant, suivi | base SQLite (chargée depuis `data/commandes.csv`) |
| `chercher_faq` | délais, frais, retours, garanties | recherche lexicale BM25 sur `data/faq.md` |
| `transferer_humain` | escalade avec motif et priorité | ticket pour un conseiller |

Il transfère, au lieu de répondre, dans les cas où une réponse automatique coûte cher : mise en demeure, demande RGPD, client qui exige un responsable, commande introuvable, colis « livré » mais non reçu, demande venant d'une autre adresse que celle de la commande (aucune donnée n'est alors divulguée).

Chaque appel d'outil est affiché : on voit ce que l'agent a vérifié avant d'écrire.

## Résultats mesurés

Jeu d'évaluation : 16 e-mails réalistes (`data/evals.json`), dont un en anglais. On note l'action, pas le style : outils attendus appelés, bonne décision d'escalade, langue de réponse.

| Version | Score | Ce qui a changé |
|---|---|---|
| v1 | 15/16 | colis non reçu transféré sans vérifier la commande ([journal](runs/eval-2026-10-02-v1.log)) |
| v2 | 16/16 | règle : vérifier la commande avant tout transfert. Relecture des brouillons : une adresse de retour inventée, une réponse en français à un client anglophone ([journal](runs/eval-2026-10-02-v2.log)) |
| v3 | 16/16 | FAQ complétée (procédure de retour), règles sur la langue et sur ce que l'agent ne peut pas faire, critère de langue ajouté à l'évaluation ([journal](runs/eval-2026-10-02.log)) |

Modèle : `openai/gpt-oss-120b` via Groq, température 0. Un modèle reste non déterministe : l'évaluation rejoue une fois chaque cas raté et affiche les deux scores (premier essai / après nouvelle tentative). Les journaux complets, brouillons compris, sont dans `runs/`.

## Lancer

Python 3.9+, aucune dépendance. Une clé [Groq](https://console.groq.com) gratuite suffit.

```bash
python3 test_outils.py                 # outils seuls, sans clé ni réseau
export GROQ_API_KEY=...
python3 agent.py --exemple 4           # un e-mail du jeu d'évaluation
python3 agent.py mon-email.txt         # ou un e-mail en texte brut
python3 eval.py                        # les 16 cas, journal dans runs/
```

Tout fournisseur compatible OpenAI fonctionne (Mistral, OpenAI, un modèle local) :
`LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... python3 agent.py --exemple 4`

## Choix techniques

- **Pas de framework.** Une boucle de ~30 lignes autour de l'API *tool calling* : lisible, auditable, sans dépendance qui casse.
- **Recherche lexicale, pas de base vectorielle.** Vingt sections de FAQ : BM25 en stdlib répond juste, se teste sans clé, et coûte zéro. Une base vectorielle se justifie à partir de quelques centaines de documents ou de requêtes très paraphrasées.
- **L'humain garde la main.** L'agent prépare, le conseiller envoie. Les cas à risque juridique ou de données personnelles ne reçoivent jamais de réponse automatique sur le fond.
- **Évaluer l'action, pas la prose.** Un brouillon bien écrit qui n'a pas vérifié la commande est un mauvais brouillon.

## Limites

- Démo : pas de connexion à une vraie boîte mail (IMAP, Gmail, Outlook) ni à un vrai back-office (Shopify, WooCommerce, Prestashop). Ce sont des adaptateurs à brancher sur les deux fonctions d'outil.
- Les brouillons peuvent encore paraphraser un détail d'interface ou annoncer une pièce jointe que le conseiller devra ajouter. C'est pour cela que la relecture humaine n'est pas optionnelle.
- 16 cas d'évaluation couvrent les situations courantes, pas toutes.

## Adapter à votre activité

Remplacer `data/faq.md` par vos conditions, brancher `chercher_commande` sur votre outil de commandes, ajouter vos propres e-mails réels (anonymisés) à `data/evals.json`, relancer `eval.py`. L'évaluation dit ce qui tient avant toute mise en production.

---

# Customer-service e-mail agent (English)

An AI agent that reads customer-service e-mails, checks the order and the store policy itself, then drafts a reply — or hands the case to a human when it should. It sends nothing: a person reviews every draft. Demo on a fictional French store; the agent answers in the customer's language.

**Tools** — `chercher_commande` (order lookup, SQLite), `chercher_faq` (BM25 lexical search over the FAQ, no vector DB), `transferer_humain` (escalation with reason and priority). Every tool call is printed, so you see what the agent verified before writing.

**Escalates instead of answering** on legal threats, GDPR requests, demands for a manager, unknown orders, "delivered but not received" parcels, and requests from an address that does not match the order (no order data disclosed).

**Measured** — 16 realistic e-mails, scored on action (expected tools called, correct escalation, reply language), not prose. v1 15/16, v3 16/16 with `openai/gpt-oss-120b` on Groq at temperature 0; failed cases are retried once and both scores reported. Full logs, drafts included, in `runs/`.

**Run** — Python 3.9+, no dependencies, free Groq key. `python3 test_outils.py` (no key needed), `python3 agent.py --exemple 4`, `python3 eval.py`. Any OpenAI-compatible provider works via `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

**Limits** — no live mailbox or store back-office connection (two adapter functions to write); drafts still need human review.

---

Built by [Yvoo Lab](https://github.com/yvoolab). MIT licence.
