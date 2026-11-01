# VERSION 1.0.0
#
# Skill Alexa Custom — affichage d'une vue Jeedom sur un device Alexa avec écran
# (Echo Show 5/8/10/15, Echo Hub, Fire TV).
#
# Invocation :
#   "Alexa, ouvre afficheur jeedom"           → splash + ouverture vue par défaut
#   "Alexa, ouvre la cuisine"                 → vue de l'objet "Cuisine"
#   "Alexa, ouvre page 5"                     → vue de l'objet d'ID 5 (legacy)
#
# Architecture :
#   Alexa device → Lambda (ce code) → URL endpoint Jeedom (jeeViewer.php du plugin
#   alexaapiv2) → page Jeedom rendue dans le navigateur de l'écran Alexa.
#
# L'endpoint Jeedom (jeeViewer.php) gère l'auto-login via l'apikey du plugin —
# plus besoin du plugin tiers "autologin".

import glob
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler,
    AbstractExceptionHandler,
)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.interfaces.alexa.presentation.apl import (
    RenderDocumentDirective,
    ExecuteCommandsDirective,
    OpenUrlCommand,
)



def load_config(path):
    """Lit config.py sans jamais lever d'exception : une faute de frappe laisse les
    réglages vides au lieu de faire planter le skill."""
    # Lu et exécuté directement (pas d'import) : aucun cache __pycache__ qui pourrait
    # resservir une ancienne version du fichier réécrit dans la même seconde.
    try:
        with open(path, encoding="utf-8") as f:
            values = {}
            exec(compile(f.read(), path, "exec"), values)
        return {k: v for k, v in values.items() if k.isupper()}
    except Exception as exc:  # SyntaxError, fichier absent…
        logging.getLogger(__name__).error("config.py illisible : %s", exc)
        return {}


CONFIG = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py"))

# ─── Textes parlés : locale/<langue>.lang (comme Frida / HomeAssistantAssist) ──
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")
DEFAULT_LOCALE = "en-US"
_TEXTS = {}


def _read_lang(path):
    """Fichier `clé=valeur` (lignes vides et `#` ignorées)."""
    texts = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    texts[key.strip()] = value.strip()
    except OSError:
        pass
    return texts


def texts_for(locale):
    """Textes de la langue de l'Echo (même langue d'un autre pays sinon, ex. fr-CA → fr-FR),
    complétés par l'anglais."""
    locale = locale or DEFAULT_LOCALE
    if locale not in _TEXTS:
        texts = _read_lang(os.path.join(LOCALE_DIR, DEFAULT_LOCALE + ".lang"))
        path = os.path.join(LOCALE_DIR, locale + ".lang")
        if not os.path.exists(path):
            same = sorted(glob.glob(os.path.join(LOCALE_DIR, locale.split("-")[0] + "-*.lang")))
            path = same[0] if same else None
        if path:
            texts.update(_read_lang(path))
        _TEXTS[locale] = texts
    return _TEXTS[locale]


def _t(handler_input, key, *args):
    text = texts_for(getattr(handler_input.request_envelope.request, "locale", None)).get(key, key)
    return text.format(*args) if args else text
JEEDOM_URL = str(CONFIG.get("JEEDOM_URL") or "")
APIKEY = str(CONFIG.get("JEEDOM_APIKEY") or "")
DEBUG = bool(CONFIG.get("DEBUG", False))

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

APL_TOKEN = "jeeViewer"
ENDPOINT_PATH = "/plugins/alexaapiv2/core/php/jeeViewer.php"


# ─── Helpers ──────────────────────────────────────────────────────────────

def _viewport_mode(handler_input):
    """
    Renvoie 'mobile' si le viewport Alexa est petit (Echo Show 5, Hub rond),
    'desktop' sinon (Show 8/10/15, Fire TV). Utilisé par jeeViewer.php pour
    choisir la skin Jeedom adaptée.
    """
    try:
        ctx = handler_input.request_envelope.context
        viewport = ctx.viewport
        if viewport and viewport.pixel_width and viewport.pixel_width < 800:
            return "mobile"
    except Exception:
        pass
    return "desktop"


def _sign_url_params(t, view, object_id, object_name):
    """
    HMAC-SHA256 sur les paramètres + timestamp.
    Doit matcher jeeViewer.php :
        payload = "{t}|{view}|{object_id}|{object_name}"
        secret  = APIKEY  (apikey du plugin alexaapiv2)
    L'apikey n'est JAMAIS dans l'URL — elle reste secrète côté Lambda.
    """
    payload = f"{t}|{view}|{object_id or ''}|{object_name or ''}"
    return hmac.new(
        APIKEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_url(handler_input, object_name=None, object_id=None):
    """Construit l'URL jeeViewer.php signée HMAC (fenêtre de validité 60s)."""
    view = _viewport_mode(handler_input)
    t    = str(int(time.time()))
    sig  = _sign_url_params(t, view, object_id, object_name)
    params = {"t": t, "view": view, "sig": sig}
    if object_name:
        params["object_name"] = object_name
    elif object_id:
        params["object_id"] = str(object_id)
    return JEEDOM_URL.rstrip("/") + ENDPOINT_PATH + "?" + urllib.parse.urlencode(params)


def _open_url_command(url):
    """Commande APL pour ouvrir une URL dans le navigateur du device Alexa."""
    return OpenUrlCommand(source=url)


def _load_apl(filename):
    """Charge un document APL depuis le répertoire du Lambda."""
    path = os.path.join(os.path.dirname(__file__), filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _render_then_open(handler_input, url, splash="apl_empty.json"):
    """
    Pattern Alexa : il faut d'abord render un document APL, puis envoyer
    une ExecuteCommandsDirective avec le OpenUrlCommand. Sans le render
    initial, OpenURL est ignoré (workaround documenté Amazon).
    """
    rb = handler_input.response_builder
    rb.add_directive(RenderDocumentDirective(
        token=APL_TOKEN,
        document=_load_apl(splash),
    ))
    rb.add_directive(ExecuteCommandsDirective(
        token=APL_TOKEN,
        commands=[_open_url_command(url)],
    ))
    return rb


# ─── Handlers ─────────────────────────────────────────────────────────────

class LaunchRequestHandler(AbstractRequestHandler):
    """« Alexa, ouvre afficheur jeedom »  →  vue par défaut."""

    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        logger.info("LaunchRequest")
        url = _build_url(handler_input)
        rb = _render_then_open(handler_input, url, splash="apl_splash.json")
        return rb.speak(_t(handler_input, "launch")).response


class OpenObjectIntentHandler(AbstractRequestHandler):
    """« Alexa, ouvre la cuisine »  →  vue de l'objet nommé."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("OpenObjectIntent")(handler_input)

    def handle(self, handler_input):
        logger.info("OpenObjectIntent")
        slot = ask_utils.request_util.get_slot(handler_input, "ObjectName")
        object_name = slot.value if slot and slot.value else None
        if not object_name:
            return handler_input.response_builder.speak(_t(handler_input, "no_object")).response

        url = _build_url(handler_input, object_name=object_name)
        rb = _render_then_open(handler_input, url)
        return rb.speak(_t(handler_input, "open_object", object_name)).response


class OpenPageIntentHandler(AbstractRequestHandler):
    """« Alexa, ouvre page 5 »  →  legacy : par object_id Jeedom."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("OpenPageIntent")(handler_input)

    def handle(self, handler_input):
        logger.info("OpenPageIntent")
        slot = ask_utils.request_util.get_slot(handler_input, "page")
        page_id = slot.value if slot and slot.value else "1"

        url = _build_url(handler_input, object_id=page_id)
        rb = _render_then_open(handler_input, url)
        return rb.speak(_t(handler_input, "open_page", page_id)).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak(_t(handler_input, "help")).ask(_t(handler_input, "help_reprompt")).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (
            ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input)
            or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
        )

    def handle(self, handler_input):
        return handler_input.response_builder.speak(_t(handler_input, "goodbye")).response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak(_t(handler_input, "fallback")).ask(_t(handler_input, "fallback_reprompt")).response


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        logger.info("SessionEnded: %s", handler_input.request_envelope.request.reason)
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error("Skill error: %s", exception, exc_info=True)
        return handler_input.response_builder.speak(_t(handler_input, "error")).response


# ─── Skill builder ────────────────────────────────────────────────────────

sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(OpenObjectIntentHandler())
sb.add_request_handler(OpenPageIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
