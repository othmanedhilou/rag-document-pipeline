# RAG Document Pipeline

Pipeline de données qui maintient à jour un index vectoriel de documents internes (PDF, Markdown,
texte) et un assistant qui répond aux questions en citant le fichier et la page d'où vient la réponse.

L'essentiel du travail est côté données : détection des changements, retraitement incrémental,
gestion des suppressions et des fichiers en erreur, journalisation de chaque run et suivi de la
fraîcheur de l'index avec dbt.

## Architecture

```
 Blob Storage (documents)
        │  dépôt / modification / suppression d'un fichier
        ▼
 Azure Data Factory  ── déclencheur horaire + déclencheur sur événement Blob
        │
        ├─ Plan       (Function)  liste le conteneur, compare au manifeste
        │                         -> nouveaux / modifiés / supprimés
        ├─ ForEach    (4 en parallèle, 2 tentatives)
        │     └─ Process (Function)  extraction texte -> découpage -> embeddings
        │                            -> upsert Azure AI Search -> manifeste
        └─ Finalize   (Function)  retire les documents supprimés, écrit le run
                                  
 pipeline-logs (Blob)  manifeste + journaux JSON Lines (runs, documents)
        │
        ▼
 dbt (DuckDB)  staging -> dim_documents, fct_runs, mart_index_freshness, mart_document_coverage
        │
        ▼
 Tableau de bord Streamlit  +  /api/ask (réponse avec sources)
```

| Brique | Service Azure | En local |
|---|---|---|
| Stockage des documents | Blob Storage | dossier `samples/` |
| Orchestration | Data Factory | `docpipe sync` |
| Traitement | Function App (Python) | même code, dans le processus |
| Extraction | pypdf, Document Intelligence pour les PDF scannés | pypdf |
| Embeddings | Azure OpenAI `text-embedding-3-small` | vecteurs par hachage ou modèle local |
| Index vectoriel | Azure AI Search (HNSW, recherche hybride) | index NumPy sur disque |
| Réponse | Azure OpenAI `gpt-4o-mini` | meilleur passage avec sa référence |
| Suivi | dbt sur les journaux | dbt-duckdb |

## Traitement incrémental

Chaque document a une entrée dans le manifeste (`manifest/<doc_id>.json`) : chemin, empreinte
SHA-256, taille, date de modification, nombre de chunks, date d'indexation.

1. **Plan** : un fichier absent du manifeste est nouveau ; un fichier dont la taille ou la date a
   changé est candidat à la mise à jour ; une entrée du manifeste sans fichier correspondant est
   une suppression.
2. **Process** : pour un candidat, l'empreinte SHA-256 est recalculée. Si le contenu est identique
   (fichier simplement réenregistré), seules les métadonnées sont mises à jour, sans nouvel appel
   d'embeddings. Sinon les anciens chunks du document sont supprimés de l'index avant d'écrire les nouveaux.
3. **Finalize** : les documents supprimés sont retirés de l'index et le run est enregistré avec son
   statut (`success`, `partial` si au moins un fichier a échoué, `failed`).

Un fichier illisible n'arrête pas le run : il est journalisé avec son erreur, apparaît en échec
dans dbt et sera retenté au prochain run.

Une entrée de manifeste par document (et non un fichier unique) permet aux instances de la Function
App qui traitent des documents en parallèle de ne jamais écraser l'état des autres.

## Suivi avec dbt

Les journaux sont lus directement par DuckDB (`read_json_auto`). Modèles :

- `stg_runs`, `stg_document_events` : typage des journaux ;
- `dim_documents` : état courant de chaque document (indexé, en échec, supprimé), délai entre
  modification et indexation ;
- `fct_runs` : historique des runs, taux d'échec ;
- `mart_index_freshness` : une ligne, temps écoulé depuis le dernier run réussi, nombre de documents
  et de chunks, documents en échec, indicateur `is_stale` ;
- `mart_document_coverage` : documents et chunks par type de fichier.

22 tests : unicité, non-nullité, valeurs autorisées, intégrité référentielle entre événements et runs,
et deux tests métier (aucun document indexé avant sa date de modification, aucun document indexé sans chunk).

## Lancer en local

```bash
pip install -e ".[dev,dashboard]"
pytest -q

python scripts/make_sample_docs.py --out samples
docpipe sync
docpipe ask "combien de jours de télétravail par semaine ?"

cd dbt && dbt build --profiles-dir . && cd ..
streamlit run dashboard/app.py
```

Exemple après un second run où un fichier a été modifié, un autre supprimé et un PDF corrompu ajouté :

```
run 20261124T182310-a97ece: 4 seen, 1 new, 1 changed, 1 deleted
new       failed   fichier_corrompu.pdf (0 chunks)
changed   indexed  notes_de_frais.md (1 chunks)
"status": "partial"

dbt build: PASS=22 WARN=0 ERROR=0
```

Par défaut les embeddings sont calculés par hachage de mots et de bigrammes (aucun modèle à
télécharger). `--embedder local` utilise un modèle sentence-transformers multilingue,
`--embedder azure` Azure OpenAI. Changer d'embedder demande un `docpipe sync --full`.

## Déploiement sur Azure

```bash
az login
cd infra/terraform
terraform init
terraform apply
```

Terraform crée le stockage (conteneurs `documents` et `pipeline-logs`), Azure AI Search,
Azure OpenAI avec les deux déploiements, Document Intelligence, Key Vault, la Function App
(plan consommation) avec Application Insights, et Data Factory avec son pipeline et ses deux
déclencheurs. Le pipeline Data Factory est lu depuis `adf/pipeline/pl_index_documents.json`,
le même fichier que celui qu'on peut importer dans l'interface ADF.

Publication de la Function App :

```bash
cp -r src/docpipe function_app/docpipe
cd function_app && func azure functionapp publish func-docpipe-dev --python
```

Ensuite il suffit de déposer des fichiers dans le conteneur `documents` : le déclencheur
d'événement lance l'indexation, et l'endpoint `POST /api/ask` répond aux questions.

Le workflow `deploy.yml` fait tout cela avec une authentification OIDC
(secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).

## Structure

```
src/docpipe/      sources, extraction, découpage, embeddings, index, état, pipeline, réponses, CLI
function_app/     endpoints HTTP appelés par Data Factory
adf/              pipeline, services liés et déclencheurs Data Factory (JSON)
dbt/              modèles et tests de suivi
dashboard/        tableau de bord Streamlit
infra/terraform/  infrastructure Azure
scripts/          génération des documents d'exemple
tests/            tests unitaires et de bout en bout
```
