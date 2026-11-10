# Assistant d'onboarding Agent IA

Application web générique d'assistance à l'onboarding. Elle comprend une interface React,
une API FastAPI, PostgreSQL pour les données applicatives, Qdrant pour la recherche
vectorielle et Ollama pour la génération de réponses et les embeddings.

Ce dépôt public ne contient aucun document métier. Après installation, un
administrateur peut importer ses propres fichiers PDF ou DOCX depuis l'interface.

## Architecture

| Composant | Rôle | Accès par défaut |
| --- | --- | --- |
| Frontend React/Nginx | Interface et proxy vers l'API | `http://localhost:8080` |
| API FastAPI | Authentification, administration et RAG | `http://localhost:8001` |
| PostgreSQL 16 | Données applicatives | port `5433` |
| Qdrant | Index vectoriel | port `6333` |
| Ollama | LLM et embeddings | service externe, port `11434` |

Nginx transmet les requêtes `/api` à FastAPI. Le navigateur n'accède donc pas
directement à l'adresse interne du backend en production.

## Prérequis

- Docker Engine avec Docker Compose v2 ;
- Ollama installé sur l'hôte Docker ou accessible sur une machine dédiée ;
- environ 16 Go de RAM système recommandés pour le modèle `llama3` par défaut ;
- facultativement un GPU compatible avec environ 6 Go de VRAM ou plus selon la
  quantification choisie.

La mémoire réellement nécessaire dépend du modèle et de sa quantification. Mesurer
la latence et la consommation sur l'infrastructure cible avant la mise en production.

## Configuration d'Ollama

Installer Ollama selon le système cible, puis télécharger les deux modèles :

```bash
ollama pull llama3
ollama pull nomic-embed-text
ollama list
```

Tester le service depuis l'hôte :

```bash
curl http://localhost:11434/api/tags
```

Par défaut, le conteneur API utilise `http://host.docker.internal:11434`. Sur Linux,
Docker Compose crée l'entrée `host.docker.internal` avec `host-gateway`. Ollama doit
écouter sur une interface joignable depuis Docker. Par exemple, selon le mode
d'installation :

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

Ne pas exposer le port Ollama publiquement. Le limiter au réseau du serveur ou à un
réseau privé. Pour un Ollama distant, définir `DOCKER_OLLAMA_URL` avec son URL privée.

Les modèles sont configurables avec `OLLAMA_LLM_MODEL` et `OLLAMA_EMBED_MODEL`. Un
changement de modèle d'embeddings nécessite la réindexation des documents dans
Qdrant.

## Variables d'environnement

Créer le fichier local à partir du modèle :

```bash
cp .env.example .env
```

Remplacer toutes les valeurs `replace-with-...`. Ne jamais envoyer ni commiter le
fichier `.env`.

Variables sensibles obligatoires :

- `POSTGRES_PASSWORD` : mot de passe PostgreSQL aléatoire ;
- `STAGING_DATABASE_URL` : URL interne utilisant ce même mot de passe ;
- `JWT_SECRET_KEY` : secret de signature des sessions ;
- `INITIAL_ADMIN_PASSWORD` : mot de passe temporaire du premier administrateur.

Exemples de génération :

```bash
openssl rand -base64 36
openssl rand -hex 32
```

Si un mot de passe contient des caractères réservés dans une URL, les encoder dans
`STAGING_DATABASE_URL`. Les identifiants présents dans `.env.example` sont uniquement
des exemples et ne doivent pas être utilisés en production.

## Premier déploiement

1. Démarrer Ollama et vérifier que les deux modèles sont présents.
2. Configurer `.env`.
3. Construire et démarrer les services :

   ```bash
   docker compose up -d --build
   ```

4. Vérifier les services :

   ```bash
   docker compose ps
   curl http://localhost:8001/health
   curl http://localhost:8080/
   ```

Au démarrage, l'API exécute automatiquement `alembic upgrade head`. Pour lancer la
migration manuellement :

```bash
docker compose exec api-staging alembic upgrade head
```

Créer ensuite le premier administrateur :

```bash
set -a
. ./.env
set +a
docker compose exec \
  -e INITIAL_ADMIN_EMAIL \
  -e INITIAL_ADMIN_PASSWORD \
  -e INITIAL_ADMIN_NAME \
  api-staging python scripts/create_initial_admin.py
unset INITIAL_ADMIN_EMAIL INITIAL_ADMIN_PASSWORD INITIAL_ADMIN_NAME
```

La commande est idempotente : elle ne recrée pas un compte ayant la même adresse.
Le mot de passe est temporaire et doit être modifié à la première connexion. Les
variables d'initialisation sont injectées uniquement pendant cette commande et ne
sont pas conservées dans le conteneur API. Retirer ensuite ces trois valeurs du
fichier `.env` ou les archiver dans le gestionnaire de secrets de l'entreprise.

L'interface est disponible sur `http://localhost:8080`. Le port public peut être
changé avec `FRONTEND_PORT`.

## Chargement des documents

1. Se connecter avec un compte administrateur.
2. Ouvrir **Administration > Documents**.
3. Importer un fichier PDF ou DOCX.
4. Attendre le statut **Prêt**.
5. Poser une question de contrôle et vérifier les sources affichées.

Les fichiers sont conservés dans le volume `uploaded_documents_staging` et leurs
vecteurs dans `qdrant_data`. Ces deux volumes doivent être sauvegardés avec PostgreSQL.

## Contacts

Les contacts sont persistés dans PostgreSQL et gérés par les endpoints protégés
`/api/admin/contacts`. Seuls les administrateurs peuvent les consulter ou les
modifier. Ils ne reposent plus sur des données fictives dans le navigateur.

## Sauvegardes

Créer un répertoire de sauvegarde protégé, puis sauvegarder PostgreSQL :

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > postgres-backup.sql
```

Créer un snapshot Qdrant de la collection configurée :

```bash
curl -X POST http://localhost:6333/collections/onboarding_docs/snapshots
```

Sauvegarder également le volume des documents :

```bash
docker run --rm -v agent-ia_uploaded_documents_staging:/data -v "$PWD":/backup alpine tar czf /backup/uploaded-documents.tar.gz -C /data .
```

Adapter le nom du projet Docker et de la collection si leur configuration diffère.
Tester périodiquement la restauration sur un environnement isolé. Une sauvegarde non
testée ne constitue pas une stratégie de reprise fiable.

## Mise à jour et retour arrière

Avant toute mise à jour :

1. créer les trois sauvegardes ;
2. noter le tag Git et les versions d'images actuellement déployés ;
3. tester la nouvelle version sur un environnement de préproduction.

Mise à jour :

```bash
git fetch --tags
git checkout <nouveau-tag>
docker compose up -d --build
```

Pour revenir en arrière, restaurer le tag précédent puis relancer Compose. Si la
nouvelle version a appliqué une migration incompatible, restaurer la sauvegarde
PostgreSQL correspondante plutôt que d'exécuter un downgrade sans validation.

## Production et sécurité

- placer le frontend derrière HTTPS avec un certificat valide ;
- ne pas publier directement PostgreSQL, Qdrant, l'API ou Ollama sur Internet ;
- limiter les ports avec le pare-feu ou supprimer leurs sections `ports` lorsque
  seuls les services Docker doivent y accéder ;
- stocker les secrets dans le gestionnaire de secrets de la plateforme ;
- renouveler immédiatement tout secret qui aurait été transmis par e-mail ou ajouté
  à une archive ;
- conserver des sauvegardes chiffrées avec une politique de rétention ;
- centraliser les logs et superviser les endpoints de santé.

## Développement et tests

Frontend :

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

Backend, dans un environnement Python 3.11 isolé :

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Pour une livraison, créer un tag puis une archive contenant uniquement les fichiers
versionnés :

```bash
git tag release-1.0.0
git archive --format=zip --output=agent-ia-release-1.0.0.zip release-1.0.0
```
