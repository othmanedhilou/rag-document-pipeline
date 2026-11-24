"""Generates a small set of internal documentation (PDF + Markdown) to try the pipeline.

    python scripts/make_sample_docs.py --out samples
"""
import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

DOCS = {
    "politique_teletravail.pdf": [
        ("Politique de télétravail", [
            "Le télétravail est ouvert à tous les collaborateurs en CDI ou CDD ayant terminé leur période d'essai. "
            "Il est organisé sur la base du volontariat et doit être validé par le manager direct.",
            "Le nombre de jours de télétravail est limité à deux jours par semaine. Les jours sont fixés avec le "
            "manager en début de mois et peuvent être modifiés avec un préavis de 48 heures.",
            "Une présence sur site est obligatoire le mardi pour toutes les équipes, ce jour étant réservé aux "
            "réunions d'équipe et aux points de suivi de projet.",
        ]),
        ("Équipement et frais", [
            "L'entreprise fournit un ordinateur portable, un écran et un casque. Le collaborateur reste "
            "responsable du matériel confié et doit signaler toute panne au support informatique.",
            "Une indemnité forfaitaire de 30 euros par mois est versée aux collaborateurs qui télétravaillent "
            "au moins quatre jours par mois. Elle couvre les frais d'électricité et de connexion internet.",
        ]),
        ("Sécurité", [
            "La connexion au système d'information se fait obligatoirement via le VPN de l'entreprise. "
            "L'utilisation d'un réseau Wi-Fi public sans VPN est interdite.",
            "Les documents classés confidentiels ne doivent pas être imprimés au domicile.",
        ]),
    ],
    "gestion_incidents_it.pdf": [
        ("Procédure de gestion des incidents", [
            "Tout incident informatique est déclaré dans l'outil de ticketing ou par téléphone au poste 4400. "
            "Le support enregistre l'incident, lui attribue une priorité et informe le demandeur.",
            "Les priorités sont définies ainsi. P1 : service critique indisponible pour tous les utilisateurs. "
            "P2 : service dégradé ou indisponible pour une équipe. P3 : gêne individuelle avec contournement possible. "
            "P4 : demande d'information ou d'évolution.",
        ]),
        ("Délais de traitement", [
            "Les délais de prise en charge sont de 15 minutes pour un P1, 1 heure pour un P2, 4 heures ouvrées "
            "pour un P3 et 2 jours ouvrés pour un P4.",
            "Les délais de résolution cibles sont de 4 heures pour un P1, 1 jour ouvré pour un P2, 3 jours ouvrés "
            "pour un P3. Un incident P1 déclenche une cellule de crise et un point toutes les 30 minutes.",
        ]),
        ("Clôture et retour d'expérience", [
            "Un incident est clôturé après confirmation du demandeur ou sans réponse de sa part sous 5 jours ouvrés. "
            "Chaque incident P1 donne lieu à un retour d'expérience écrit sous 10 jours, avec la cause racine "
            "et les actions correctives.",
        ]),
    ],
    "politique_mots_de_passe.pdf": [
        ("Politique de mots de passe", [
            "Un mot de passe contient au moins 12 caractères, dont une majuscule, une minuscule, un chiffre et "
            "un caractère spécial. Il ne doit pas contenir le nom ou le prénom de l'utilisateur.",
            "Le mot de passe du compte principal est changé tous les 180 jours. Les 5 derniers mots de passe "
            "ne peuvent pas être réutilisés.",
            "Après 5 tentatives échouées, le compte est verrouillé pendant 15 minutes.",
            "L'authentification multifacteur est obligatoire pour l'accès à distance, à la messagerie et aux "
            "applications financières.",
        ]),
    ],
}

MARKDOWN = {
    "notes_de_frais.md": """# Notes de frais

## Principes

Les frais professionnels sont remboursés sur présentation d'un justificatif original. La note de frais est
saisie dans l'outil de gestion au plus tard 30 jours après la dépense.

## Plafonds

- Repas d'affaires : 35 euros par personne.
- Hôtel : 120 euros par nuit à Paris, 90 euros en province.
- Train : seconde classe, première classe autorisée pour un trajet de plus de 3 heures.
- Avion : classe économique, réservation par l'agence de voyage de l'entreprise.

## Validation

La note est validée par le manager puis par le service comptable. Le remboursement est effectué avec la
paie du mois suivant la validation.
""",
}


def build_pdf(path: Path, sections):
    styles = getSampleStyleSheet()
    story = []
    for i, (title, paragraphs) in enumerate(sections):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(title, styles["Heading1"]))
        for text in paragraphs:
            story.append(Paragraph(text, styles["BodyText"]))
            story.append(Spacer(1, 8))
    SimpleDocTemplate(str(path), pagesize=A4).build(story)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="samples")
    out = Path(p.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for name, sections in DOCS.items():
        build_pdf(out / name, sections)
    for name, text in MARKDOWN.items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"{len(DOCS) + len(MARKDOWN)} documents written to {out}")


if __name__ == "__main__":
    main()
