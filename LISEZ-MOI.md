# Ma Grille TV

Programme TV en timeline pour les chaînes du bouquet Free, mis à jour automatiquement deux fois par jour.
Une fois installé, il suffit d'ouvrir l'icône sur l'iPad.

Tout se fait depuis un ordinateur, une seule fois (environ 15 minutes).

## 1. Créer le dépôt GitHub

1. Créez un compte gratuit sur https://github.com.
2. Cliquez sur **New repository**. Nom : `grille-tv`. Choisissez **Public** (nécessaire pour l'hébergement gratuit). Validez avec **Create repository**.
3. Sur la page du dépôt, cliquez sur **uploading an existing file**, puis glissez le contenu du dossier **sauf** `workflow-visible` (ce dossier sert à l'étape suivante). Validez avec **Commit changes**.
4. Le fichier qui lance la mise à jour automatique se trouve dans un dossier caché (`.github`) que Mac, Windows et l'iPad n'affichent pas. Pour éviter ce problème, créez-le à la main : sur la page du dépôt, **Add file → Create new file**. Dans la case du nom, tapez exactement `.github/workflows/update-guide.yml` (GitHub crée les dossiers tout seul quand vous tapez les `/`). Ouvrez le fichier `workflow-visible/update-guide.yml`, copiez tout son contenu, collez-le dans la grande zone de texte, puis validez avec **Commit changes**.

   (Si vous préférez afficher les fichiers cachés : sur Mac, touches **Cmd + Maj + .** dans le Finder ; sur Windows, **Affichage → Éléments masqués**. Le dossier `.github` est bien dans le zip.)

## 2. Activer le site

1. Dans le dépôt : **Settings → Pages**.
2. *Source* : **Deploy from a branch**. *Branch* : **main**, dossier **/ (root)**. Cliquez sur **Save**.
3. Après une ou deux minutes, l'adresse de votre site s'affiche en haut de la page : `https://VOTRE-NOM.github.io/grille-tv/`.

## 3. Charger le guide la première fois

1. Onglet **Actions**. S'il demande d'activer les workflows, acceptez.
2. Cliquez sur **Mettre à jour le guide TV**, puis **Run workflow**.
3. Au bout de quelques minutes, une coche verte apparaît. Le fichier `data/guide.json` est alors créé et le site affiche les vrais programmes.

Ensuite, la mise à jour se fait seule deux fois par jour.

Si le workflow échoue avec « Aucune adresse de flux ne répond » : l'adresse du flux a changé. Récupérez l'adresse du fichier XMLTV sur https://xmltvfr.fr, puis dans **Settings → Secrets and variables → Actions → Variables**, créez une variable `FEED_URL` avec cette adresse et relancez.

## 4. Ajouter les affiches (facultatif)

Sans clé, la fiche d'un programme affiche l'image du guide quand il en fournit une, sinon un visuel illustratif.
Pour avoir les affiches des films et séries :

1. Créez un compte gratuit sur https://www.themoviedb.org, puis **Paramètres → API** et demandez une clé (usage personnel).
2. Dans votre dépôt : **Settings → Secrets and variables → Actions → New repository secret**. Nom : `TMDB_API_KEY`. Valeur : votre clé.
3. Relancez le workflow (étape 3).

Les affiches viennent de TMDB (« Ce produit utilise l'API TMDB mais n'est ni approuvé ni certifié par TMDB »). Allociné et IMDb ne sont pas utilisés : leurs conditions interdisent la récupération automatique.

## 5. Installer sur l'iPad

1. Ouvrez l'adresse de votre site dans **Safari**.
2. Bouton **Partager → Sur l'écran d'accueil**.

## Notes

- Le guide vient du flux public xmltvfr.fr. Ses conditions d'utilisation ne sont pas précisées : gardez ce site pour votre usage personnel.
- La liste des chaînes et leurs numéros suivent le plan de service Free d'août 2026 (TNT 1 à 29, Canal+ au 40). Pour modifier la liste, éditez `CHANNELS` en haut de `scripts/build_guide.py`.
- Si le guide ne se met plus à jour, allez dans **Actions** et relancez le workflow à la main.
- En l'absence de `data/guide.json`, la page passe en « mode démo » avec des programmes inventés.
