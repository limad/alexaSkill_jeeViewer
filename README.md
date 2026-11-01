# premium_jeeViewer_skill

Skill **Alexa Custom** pour afficher le tableau de bord Jeedom sur les appareils Alexa avec écran (Echo Show 5/8/10/15, Echo Hub, Fire TV).

> Ré-écriture optimisée de [`alexaPremium_jee_viewer`](https://github.com/limad/alexaPremium_jee_viewer) — voir section [Changements vs original](#changements-vs-original).

## Architecture

```
Alexa Echo Show / Hub / Fire TV
   ↓ "Alexa, ouvre la cuisine"
   ↓
Lambda Python (Alexa-hosted)
   ↓ APL RenderDocument + ExecuteCommands(OpenURL)
   ↓
Navigateur du device Alexa
   ↓ GET https://JEEDOM_URL/plugins/alexaapiv2/core/php/jeeViewer.php?t=…&view=…&object_name=Cuisine&sig=…
   ↓
Endpoint Jeedom (alexaapiv2 plugin) :
  - Adresse signée HMAC (clé du plugin, jamais dans l'adresse), valable 60 s
  - Auto-login Jeedom natif (utilisateur dédié alexa_viewer, plus de dépendance autologin)
  - Version mobile ou bureau selon la taille de l'écran
  - Redirige vers le dashboard de l'objet demandé, sinon vers la page choisie
    dans la configuration du plugin (« Page affichée par défaut »)
```

## Invocations

| Phrase | Action |
|---|---|
| *« Alexa, ouvre afficheur jeedom »* | Vue par défaut (objet racine) |
| *« Alexa, demande à afficheur jeedom d'ouvrir la **cuisine** »* | Vue de l'objet "Cuisine" |
| *« Alexa, demande à afficheur jeedom de montrer le **salon** »* | Vue de l'objet "Salon" |
| *« Alexa, demande à afficheur jeedom **page 5** »* | Legacy : vue par object_id Jeedom |

Langues : français (fr-FR, fr-CA, « afficheur jeedom »), anglais (en-US, en-GB, en-CA, « jeedom display »), espagnol (es-ES, « pantalla jeedom »), allemand (de-DE, « jeedom anzeige »). Textes parlés dans `lambda/locale/<langue>.lang`.

## Réglages (`lambda/config.py`)

| Réglage | Valeur écrite au déploiement |
|---|---|
| `JEEDOM_URL` | adresse interne de Jeedom (`network::getNetworkAccess('internal')`), externe en repli ou si `urlMode` = `external` |
| `JEEDOM_APIKEY` | clé API du plugin alexaapiv2 (`jeedom::getApiKey('alexaapiv2')`) : signe l'adresse, n'y apparaît jamais |
| `VERIFY_SSL`, `DEBUG` | format commun aux skills du plugin |

## Installation

**Avec le plugin alexaapiv2** : page du plugin → **Déployer Skill JeeViewer**. Le plugin télécharge ce dépôt, écrit `lambda/config.py`, puis crée ou met à jour le skill sur votre compte développeur Amazon.

**À la main**, tout se fait dans la [console développeur Alexa](https://developer.amazon.com/alexa/console/ask) :

1. **Create Skill** : modèle **Custom**, hébergement **Alexa-hosted (Python)**, région EU (Ireland), modèle de départ **Import skill** avec l'URL de ce dépôt (`https://github.com/limad/alexaSkill_jeeViewer.git`). Amazon importe le code (`lambda/`), la fiche avec l'écran APL (`skill-package/skill.json`), les icônes et le modèle vocal de la langue choisie dans le formulaire (et ses variantes), puis le compile. Le nom du skill est celui tapé dans le formulaire.
2. Onglet **Code** : ouvrez `lambda/config.py`, renseignez-le (valeurs entre guillemets, `True` / `False` sans guillemets), puis **Save** et **Deploy**. Une faute de frappe laisse les réglages vides au lieu de faire planter le skill.
3. Autre langue : *Build* → *Language settings* → ajoutez-la, collez `skill-package/interactionModels/custom/<langue>.json` dans le *JSON Editor*, puis **Build skill**.
4. Onglet **Test** → *Development*, ou sur l'Echo Show : « Alexa, ouvre afficheur jeedom ».

## Prérequis Jeedom

- Plugin **alexaapiv2** installé et configuré
- Endpoint `/plugins/alexaapiv2/core/php/jeeViewer.php` disponible (fourni par le plugin)
- Jeedom joignable par l'Echo Show : adresse interne par défaut (l'écran est sur le réseau local), adresse externe HTTPS si `urlMode` = `external`

**Note** : la dépendance au plugin tiers `autologin` de la version originale a été **supprimée**. Le plugin `alexaapiv2` fournit son propre endpoint d'auto-login.

## Structure

```
.
├── skill-package/                            — lu par Amazon à l'import GitHub
│   ├── skill.json                            — Manifest Alexa avec viewports + locales
│   ├── assets/images/                        — icônes
│   └── interactionModels/custom/
│       └── <langue>.json                     — fr-FR, fr-CA, en-US, en-GB, en-CA, es-ES, de-DE : OpenObjectIntent / OpenPageIntent
├── lambda/
│   ├── lambda_function.py                    — Handlers ASK SDK
│   ├── config.py                             — Réglages (réécrit au déploiement)
│   ├── locale/<langue>.lang                  — Textes parlés (fr-FR, en-US, es-ES, de-DE)
│   ├── requirements.txt                      — ask-sdk-core uniquement
│   ├── apl_splash.json                       — APL splash écran d'accueil
│   └── apl_empty.json                        — APL minimal (déclencheur OpenURL)
└── .github/workflows/test.yml                — CI Python 3.10-3.12 + JSON validation
```

## Changements vs original

| Aspect | Avant | Après |
|---|---|---|
| Plugin tiers `autologin` | obligatoire | supprimé (endpoint plugin alexaapiv2 dédié) |
| `boto3` + S3 presigned URL (jamais utilisé fonctionnellement) | dépendance | supprimé |
| `test.py` (code mort, syntax error) | présent | supprimé |
| Templates APL morts (1, 4, 5) | présents | supprimés |
| Templates renommés | `template{2,3}.json` | `apl_empty.json`, `apl_splash.json` |
| Slot intent | `page` (NUMBER) uniquement | + `ObjectName` (SearchQuery — ouvre par nom de pièce) |
| Help / Cancel / Exception | muets | messages parlants |
| `IntentReflectorHandler` | exposé en prod (debug) | supprimé |
| `MOBILE_MODE` global | flag binaire | adaptive viewport (HUB rond → mobile, HUB rectangle large → desktop) |
| Config | hardcodé URL+apikey | placeholders injectés au déploiement |
| `ExceptionHandler` | "Erreur survenue" générique | message contextualisé + log précis |

## Licence

AGPL-3.0 — même licence que le plugin alexaapiv2.
