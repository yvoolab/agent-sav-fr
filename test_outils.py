#!/usr/bin/env python3
"""Vérifie les outils sans appel au modèle (aucune clé requise) : python3 test_outils.py"""
import agent

assert agent.chercher_commande(numero="cmd-1042")["commandes"][0]["statut"] == "en préparation"
assert agent.chercher_commande(email="K.Nguyen@example.com")["commandes"][0]["numero"] == "CMD-1047"
assert agent.chercher_commande(numero="CMD-9999")["commandes"] == []
assert "erreur" in agent.chercher_commande()
assert agent.bm25("délai de remboursement après retour")[0].startswith("## Délai de remboursement")
assert agent.bm25("livrez-vous en Suisse ?")[0].startswith("## Pays desservis")
assert agent.bm25("tasse cassée à la réception")[0].startswith("## Article cassé")
assert agent.bm25("supprimer mes données personnelles")[0].startswith("## Données personnelles")
assert agent.bm25("tasse fêlée")[0].startswith("## Article cassé")
assert agent.bm25("xyzzy") == []
assert agent.transferer_humain("test", "haute")["transfere"] is True
print("outils : OK")
