#!/usr/bin/env python3
"""Évalue l'agent sur data/evals.json.

On note l'ACTION, pas le style : les outils attendus ont-ils été appelés,
l'escalade est-elle la bonne, le brouillon contient-il les mots exigés ? Un modèle à température 0 reste non déterministe,
donc chaque cas raté est rejoué une fois ; le journal distingue les deux scores.
"""
import json, sys, time
from datetime import date
from pathlib import Path
import agent

def juger(r: dict, attendu: dict) -> list:
    manque = [o for o in attendu["outils"] if o not in r["outils"]]
    err = [f"outil manquant : {o}" for o in manque]
    if (r["action"] == "escalade") != attendu["escalade"]:
        err.append(f"escalade attendue : {attendu['escalade']}, obtenue : {r['action'] == 'escalade'}")
    for mot in attendu.get("contient", []):
        if mot.lower() not in r["brouillon"].lower():
            err.append(f"brouillon sans « {mot} »")
    return err

def main():
    cas = json.loads((agent.ROOT / "data" / "evals.json").read_text(encoding="utf-8"))
    log_path = agent.ROOT / "runs" / f"eval-{date.today()}.log"
    lines = []
    def out(s=""):
        print(s); lines.append(s)
    out(f"modèle : {agent.MODEL} · {len(cas)} cas")
    premier, final = 0, 0
    for i, c in enumerate(cas, 1):
        email = agent.format_email(c)
        for essai in (1, 2):
            out(f"\n[{i:02d}] {c['objet']} (essai {essai})")
            r = agent.traiter(email, trace=out)
            err = juger(r, c["attendu"])
            out(f"  = {r['action']}" + (f" — {r['motif']}" if r["motif"] else ""))
            out("  " + ("OK" if not err else "ÉCHEC : " + " ; ".join(err)))
            if essai == 1:
                out("  brouillon : " + r["brouillon"].replace("\n", "\n  │ "))
            if not err:
                premier += essai == 1
                final += 1
                break
    out(f"\nRÉSULTAT : {premier}/{len(cas)} au premier essai · {final}/{len(cas)} après une nouvelle tentative")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"journal : {log_path}")
    sys.exit(0 if final == len(cas) else 1)

if __name__ == "__main__":
    main()
