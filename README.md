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
   ↓ GET https://JEEDOM_URL/plugins/alexaapiv2/core/php/jeeViewer.php?apikey=...&object_name=Cuisine
   ↓
Endpoint Jeedom (alexaapiv2 plugin) :
  - Auth via apikey
  - Auto-login Jeedom natif (plus de dépendance autologin)
  - Adapter la vue selon viewport (mobile/desktop)
  - Redirige vers la vue Jeedom appropriée
```

## Invocations

| Phrase | Action |
|---|---|
| *« Alexa, ouvre afficheur jeedom »* | Vue par défaut (objet racine) |
| *« Alexa, demande à afficheur jeedom d'ouvrir la **cuisine** »* | Vue de l'objet "Cuisine" |
| *« Alexa, demande à afficheur jeedom de montrer le **salon** »* | Vue de l'objet "Salon" |
| *« Alexa, demande à afficheur jeedom **page 5** »* | Legacy : vue par object_id Jeedom |

Langues : français (fr-FR, fr-CA, « afficheur jeedom »), anglais (en-US, « jeedom display »), espagnol (es-ES, « pantalla jeedom »), allemand (de-DE, « jeedom anzeige »). Textes parlés dans `lambda/locale/<langue>.lang`.

## Réglages (`lambda/config.py`)

| Réglage | Valeur écrite au déploiement |
|---|---|
| `JEEDOM_URL` | adresse interne de Jeedom (`network::getNetworkAccess('internal')`), externe en repli ou si `urlMode` = `external` |
| `JEEDOM_APIKEY` | clé API du plugin alexaapiv2 (`jeedom::getApiKey('alexaapiv2')`) : signe l'adresse, n'y apparaît jamais |
| `VERIFY_SSL`, `DEBUG` | format commun aux skills du plugin |

Installation à la main : renseigner `lambda/config.py` (valeurs entre guillemets, `True` / `False` sans guillemets). Une faute de frappe laisse les réglages vides au lieu de faire planter le skill.

Le déploiement est automatisé par le plugin alexaapiv2 (action AJAX `deployJeeViewerSkill`).

## Prérequis Jeedom

- Plugin **alexaapiv2** installé et configuré
- Endpoint `/plugins/alexaapiv2/core/php/jeeViewer.php` disponible (fourni par le plugin)
- Jeedom accessible publiquement en HTTPS avec certificat valide (Let's Encrypt OK)

**Note** : la dépendance au plugin tiers `autologin` de la version originale a été **supprimée**. Le plugin `alexaapiv2` fournit son propre endpoint d'auto-login.

## Structure

```
.
├── skill-package/                            — lu par Amazon à l'import GitHub
│   ├── skill.json                            — Manifest Alexa avec viewports + locales
│   ├── assets/images/                        — icônes
│   └── interactionModels/custom/
│       └── <langue>.json                     — fr-FR, fr-CA, en-US, es-ES, de-DE : OpenObjectIntent / OpenPageIntent
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
