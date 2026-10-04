"""Answer templates for the template expert, in the four capture languages.

Each topic has a "direct" form (states the number or approver) and, where it
makes sense, a "vague" form that leaves the detail out so the debrief has to
ask for it. Placeholders: {T} connection floor, {M} deadline margin, {A} approver.
"""

APPROVERS = {
    "duty manager": {"en": "the duty manager", "fr": "le responsable de permanence", "de": "der Duty Manager",
                     "hi": "ड्यूटी मैनेजर", "keywords": ["duty"]},
    "station supervisor": {"en": "the station supervisor", "fr": "le superviseur d'escale", "de": "der Stationsleiter",
                           "hi": "स्टेशन सुपरवाइज़र", "keywords": ["station", "escale", "ground"]},
    "shift lead": {"en": "the shift lead", "fr": "le chef d'équipe", "de": "die Schichtleitung",
                   "hi": "शिफ़्ट लीड", "keywords": ["shift", "team"]},
}

P = {
    "connection_direct": {
        "en": "That connection is too tight with a checked bag. I never go below {T} minutes when there's a bag.",
        "fr": "Cette correspondance est trop courte avec un bagage enregistré. Je ne descends jamais en dessous de {T} minutes quand il y a un bagage.",
        "de": "Die Verbindung ist mit aufgegebenem Gepäck zu knapp. Mit Gepäck gehe ich nie unter {T} Minuten.",
        "hi": "चेक्ड बैग के साथ यह कनेक्शन बहुत टाइट है। बैग हो तो मैं {T} मिनट से कम कभी नहीं लेती।",
    },
    "connection_vague": {
        "en": "With a checked bag that transfer is just too tight, the bag won't make it.",
        "fr": "Avec un bagage enregistré, ce transfert est trop juste, le bagage ne suivra pas.",
        "de": "Mit aufgegebenem Gepäck ist der Umstieg einfach zu knapp, das Gepäck schafft das nicht.",
        "hi": "चेक्ड बैग के साथ यह ट्रांसफ़र बहुत टाइट है, बैग नहीं पहुँचेगा।",
    },
    "connection_number": {
        "en": "At least {T} minutes with a bag.",
        "fr": "Au moins {T} minutes avec un bagage.",
        "de": "Mindestens {T} Minuten mit Gepäck.",
        "hi": "बैग के साथ कम से कम {T} मिनट।",
    },
    "deadline_direct": {
        "en": "It lands after her deadline, she'd miss the signing. I want at least {M} minutes of margin before the deadline.",
        "fr": "Il arrive après son heure limite, elle raterait la signature. Je veux au moins {M} minutes de marge avant l'heure limite.",
        "de": "Er landet nach ihrer Deadline, sie würde die Unterzeichnung verpassen. Ich will mindestens {M} Minuten Puffer vor der Deadline.",
        "hi": "यह उसकी डेडलाइन के बाद लैंड करता है, वह साइनिंग मिस कर देगी। मुझे डेडलाइन से कम से कम {M} मिनट का मार्जिन चाहिए।",
    },
    "deadline_vague": {
        "en": "It lands after her deadline, so she'd miss the signing. Landing late is not an option.",
        "fr": "Il arrive après son heure limite, elle raterait la signature. Arriver en retard n'est pas une option.",
        "de": "Er landet nach ihrer Deadline, sie würde die Unterzeichnung verpassen. Zu spät landen geht nicht.",
        "hi": "यह उसकी डेडलाइन के बाद लैंड करता है, वह साइनिंग मिस कर देगी। देर से पहुँचना कोई विकल्प नहीं है।",
    },
    "deadline_margin": {
        "en": "I need at least {M} minutes of margin before the deadline.",
        "fr": "Il me faut au moins {M} minutes de marge avant l'heure limite.",
        "de": "Ich brauche mindestens {M} Minuten Puffer vor der Deadline.",
        "hi": "मुझे डेडलाइन से पहले कम से कम {M} मिनट का मार्जिन चाहिए।",
    },
    "deadline_no_margin": {
        "en": "No margin needed, it just has to land before the deadline.",
        "fr": "Pas besoin de marge, il doit juste arriver avant l'heure limite.",
        "de": "Kein Puffer nötig, er muss nur vor der Deadline landen.",
        "hi": "मार्जिन की ज़रूरत नहीं, बस डेडलाइन से पहले लैंड होना चाहिए।",
    },
    "authority_direct": {
        "en": "That's an upgrade to business. I can't approve that myself, {A} has to sign it off.",
        "fr": "C'est un surclassement en affaires. Je ne peux pas l'approuver moi-même, {A} doit le valider.",
        "de": "Das ist ein Upgrade in die Business Class. Das darf ich nicht selbst freigeben, {A} muss zustimmen.",
        "hi": "यह बिज़नेस में अपग्रेड है। मैं इसे खुद अप्रूव नहीं कर सकती, {A} को मंज़ूरी देनी होगी।",
    },
    "authority_vague": {
        "en": "That's an upgrade to business. I can't approve that myself, it needs sign-off.",
        "fr": "C'est un surclassement en affaires. Je ne peux pas l'approuver moi-même, il faut une validation.",
        "de": "Das ist ein Upgrade in die Business Class. Das darf ich nicht selbst freigeben, das braucht eine Freigabe.",
        "hi": "यह बिज़नेस में अपग्रेड है। मैं इसे खुद अप्रूव नहीं कर सकती, इसके लिए मंज़ूरी चाहिए।",
    },
    "authority_who": {
        "en": "{A} on shift has to approve it.",
        "fr": "C'est {A} de service qui doit l'approuver.",
        "de": "{A} im Dienst muss das genehmigen.",
        "hi": "शिफ़्ट पर मौजूद {A} को इसे अप्रूव करना होगा।",
    },
    "no_exception": {
        "en": "No exceptions, never.", "fr": "Aucune exception, jamais.", "de": "Keine Ausnahmen, niemals.",
        "hi": "कोई अपवाद नहीं, कभी नहीं।",
    },
    "no_bag": {
        "en": "With carry-on only the bag rule doesn't apply.",
        "fr": "Avec seulement un bagage cabine, la règle du bagage ne s'applique pas.",
        "de": "Nur mit Handgepäck gilt die Gepäckregel nicht.",
        "hi": "सिर्फ़ कैरी-ऑन हो तो बैग वाला नियम लागू नहीं होता।",
    },
    "weather": {
        "en": "Bad weather at the hub makes me more careful, but the rules stay the same.",
        "fr": "Le mauvais temps au hub me rend plus prudente, mais les règles restent les mêmes.",
        "de": "Schlechtes Wetter am Drehkreuz macht mich vorsichtiger, aber die Regeln bleiben gleich.",
        "hi": "हब पर खराब मौसम हो तो मैं ज़्यादा सावधान रहती हूँ, पर नियम वही रहते हैं।",
    },
    "confirm": {"en": "Yes, that's right.", "fr": "Oui, c'est exact.", "de": "Ja, genau so.", "hi": "हाँ, बिल्कुल सही।"},
    "correct_connection": {
        "en": "No, the minimum with a bag is {T} minutes.",
        "fr": "Non, le minimum avec un bagage est de {T} minutes.",
        "de": "Nein, das Minimum mit Gepäck sind {T} Minuten.",
        "hi": "नहीं, बैग के साथ न्यूनतम {T} मिनट है।",
    },
    "correct_authority": {
        "en": "No, it's {A} who approves upgrades.",
        "fr": "Non, c'est {A} qui approuve les surclassements.",
        "de": "Nein, {A} genehmigt Upgrades.",
        "hi": "नहीं, अपग्रेड {A} अप्रूव करते हैं।",
    },
    "generic": {
        "en": "It depends on the passenger, but the same rules apply.",
        "fr": "Ça dépend du passager, mais les mêmes règles s'appliquent.",
        "de": "Das hängt vom Passagier ab, aber es gelten dieselben Regeln.",
        "hi": "यह यात्री पर निर्भर करता है, पर नियम वही लागू होते हैं।",
    },
}


def say(key: str, lang: str, **kw) -> str:
    text = P[key][lang].format(**kw)
    return text[0].upper() + text[1:] if lang in ("en", "fr", "de") else text
