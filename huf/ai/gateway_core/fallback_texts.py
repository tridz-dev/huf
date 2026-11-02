"""Localised fallback reply texts."""

from __future__ import annotations

_FALLBACK_TEXTS = {
    "en": {
        "error": "Sorry, something went wrong on our side and I could not answer. Please try again in a moment.",
        "attachment": "Sorry, I could not open the file you sent. Please send it again or describe it in a message.",
    },
    "es": {
        "error": "Lo sentimos, algo salio mal y no pude responder. Por favor intentalo de nuevo en un momento.",
        "attachment": "Lo sentimos, no pude abrir el archivo que enviaste. Envialo de nuevo o descríbelo en un mensaje.",
    },
    "fr": {
        "error": "Désolé, un problème est survenu et je n'ai pas pu répondre. Veuillez réessayer dans un instant.",
        "attachment": "Désolé, je n'ai pas pu ouvrir le fichier envoyé. Renvoyez-le ou décrivez-le dans un message.",
    },
    "pt": {
        "error": "Desculpe, algo deu errado e nao consegui responder. Tente novamente em instantes.",
        "attachment": "Desculpe, nao consegui abrir o arquivo enviado. Envie novamente ou descreva em uma mensagem.",
    },
    "de": {
        "error": "Entschuldigung, es ist ein Fehler aufgetreten und ich konnte nicht antworten. Bitte versuchen Sie es gleich noch einmal.",
        "attachment": "Entschuldigung, ich konnte die gesendete Datei nicht öffnen. Bitte senden Sie sie erneut oder beschreiben Sie sie kurz.",
    },
    "ar": {
        "error": "عذرا، حدث خطأ ولم أتمكن من الرد. يرجى المحاولة مرة أخرى بعد قليل.",
        "attachment": "عذرا، لم أتمكن من فتح الملف الذي أرسلته. يرجى إرساله مرة أخرى أو وصفه في رسالة.",
    },
}
ATTACHMENT_UNAVAILABLE_NOTE = "[Attachment unavailable: the file the user sent could not be downloaded]"
