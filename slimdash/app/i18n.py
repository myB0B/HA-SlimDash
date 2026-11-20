"""SlimDash - language of the texts SlimDash itself produces.

The language is the one set in Home Assistant (get_config); English is the default and the fallback.
The state labels ("On", "Closed"...) come from Home Assistant itself, in its language (render.TR).
This module covers the rest: number format, month and day names, relative times ("3 minutes ago")
and short dates. The same data is sent to the browser (client_data) so that the clock and the
"ago" texts kept up to date by s.js use the same words.

To add a language: add an entry to LANGS (same keys as "en") and, if its plural rule is new, to
plural_index() and to plural() in s.js.
"""
import time

LANG = "en"

# u = the 7 units (second, minute, hour, day, week, month, year): forms by plural category.
# pl = plural rule: "en" (1 | other), "fr" (0-1 | other), "ru" / "pl" (1 | few | many).
# past = pattern around the duration; d1 / d2 / w1 / m1 / y1 = words for 1 day ago, 2 days ago,
# 1 week ago, 1 month ago, 1 year ago (d2 None: "2 days ago"). dec / thou = decimal and thousands
# separators. ds / df = short date and date with year (strftime). st / sd = "since" patterns
# (a time today / a date).
LANGS = {
    "en": {
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
        "months3": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                    "Dec"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "days3": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "dec": ".", "thou": ",", "pl": "en",
        "past": "%s ago", "now": "now", "d1": "yesterday", "d2": None,
        "w1": "last week", "m1": "last month", "y1": "last year",
        "u": [["second", "seconds"], ["minute", "minutes"], ["hour", "hours"], ["day", "days"],
              ["week", "weeks"], ["month", "months"], ["year", "years"]],
        "ds": "%m/%d", "df": "%m/%d/%Y", "st": "since %s", "sd": "since %s",
    },
    "fr": {
        "months": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                   "septembre", "octobre", "novembre", "décembre"],
        "months3": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.",
                    "oct.", "nov.", "déc."],
        "days": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "days3": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
        "dec": ",", "thou": " ", "pl": "fr",
        "past": "il y a %s", "now": "maintenant", "d1": "hier", "d2": "avant-hier",
        "w1": "la semaine dernière", "m1": "le mois dernier", "y1": "l’année dernière",
        "u": [["seconde", "secondes"], ["minute", "minutes"], ["heure", "heures"],
              ["jour", "jours"], ["semaine", "semaines"], ["mois", "mois"], ["an", "ans"]],
        "ds": "%d/%m", "df": "%d/%m/%Y", "st": "depuis %s", "sd": "depuis le %s",
    },
    "de": {
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
                   "September", "Oktober", "November", "Dezember"],
        "months3": ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.",
                    "Nov.", "Dez."],
        "days": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "days3": ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."],
        "dec": ",", "thou": ".", "pl": "en",
        "past": "vor %s", "now": "jetzt", "d1": "gestern", "d2": "vorgestern",
        "w1": "letzte Woche", "m1": "letzten Monat", "y1": "letztes Jahr",
        "u": [["Sekunde", "Sekunden"], ["Minute", "Minuten"], ["Stunde", "Stunden"],
              ["Tag", "Tage"], ["Woche", "Wochen"], ["Monat", "Monate"], ["Jahr", "Jahre"]],
        "ds": "%d.%m.", "df": "%d.%m.%Y", "st": "seit %s", "sd": "seit %s",
    },
    "es": {
        "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                   "septiembre", "octubre", "noviembre", "diciembre"],
        "months3": ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.",
                    "oct.", "nov.", "dic."],
        "days": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        "days3": ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."],
        "dec": ",", "thou": ".", "pl": "en",
        "past": "hace %s", "now": "ahora", "d1": "ayer", "d2": "anteayer",
        "w1": "la semana pasada", "m1": "el mes pasado", "y1": "el año pasado",
        "u": [["segundo", "segundos"], ["minuto", "minutos"], ["hora", "horas"], ["día", "días"],
              ["semana", "semanas"], ["mes", "meses"], ["año", "años"]],
        "ds": "%d/%m", "df": "%d/%m/%Y", "st": "desde %s", "sd": "desde el %s",
    },
    "it": {
        "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                   "agosto", "settembre", "ottobre", "novembre", "dicembre"],
        "months3": ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov",
                    "dic"],
        "days": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"],
        "days3": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
        "dec": ",", "thou": ".", "pl": "en",
        "past": "%s fa", "now": "adesso", "d1": "ieri", "d2": "l’altro ieri",
        "w1": "la settimana scorsa", "m1": "il mese scorso", "y1": "l’anno scorso",
        "u": [["secondo", "secondi"], ["minuto", "minuti"], ["ora", "ore"], ["giorno", "giorni"],
              ["settimana", "settimane"], ["mese", "mesi"], ["anno", "anni"]],
        "ds": "%d/%m", "df": "%d/%m/%Y", "st": "da %s", "sd": "dal %s",
    },
    "pt": {
        "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                   "setembro", "outubro", "novembro", "dezembro"],
        "months3": ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.",
                    "nov.", "dez."],
        "days": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                 "sábado", "domingo"],
        "days3": ["seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom."],
        "dec": ",", "thou": ".", "pl": "fr",
        "past": "há %s", "now": "agora", "d1": "ontem", "d2": "anteontem",
        "w1": "semana passada", "m1": "mês passado", "y1": "ano passado",
        "u": [["segundo", "segundos"], ["minuto", "minutos"], ["hora", "horas"], ["dia", "dias"],
              ["semana", "semanas"], ["mês", "meses"], ["ano", "anos"]],
        "ds": "%d/%m", "df": "%d/%m/%Y", "st": "desde %s", "sd": "desde %s",
    },
    "nl": {
        "months": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
                   "september", "oktober", "november", "december"],
        "months3": ["jan.", "feb.", "mrt.", "apr.", "mei", "jun.", "jul.", "aug.", "sep.", "okt.",
                    "nov.", "dec."],
        "days": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
        "days3": ["ma", "di", "wo", "do", "vr", "za", "zo"],
        "dec": ",", "thou": ".", "pl": "en",
        "past": "%s geleden", "now": "nu", "d1": "gisteren", "d2": "eergisteren",
        "w1": "vorige week", "m1": "vorige maand", "y1": "vorig jaar",
        "u": [["seconde", "seconden"], ["minuut", "minuten"], ["uur", "uur"], ["dag", "dagen"],
              ["week", "weken"], ["maand", "maanden"], ["jaar", "jaar"]],
        "ds": "%d-%m", "df": "%d-%m-%Y", "st": "sinds %s", "sd": "sinds %s",
    },
    "ru": {
        "months": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                   "сентября", "октября", "ноября", "декабря"],
        "months3": ["янв.", "февр.", "мар.", "апр.", "мая", "июн.", "июл.", "авг.", "сент.",
                    "окт.", "нояб.", "дек."],
        "days": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота",
                 "воскресенье"],
        "days3": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
        "dec": ",", "thou": " ", "pl": "ru",
        "past": "%s назад", "now": "сейчас", "d1": "вчера", "d2": "позавчера",
        "w1": "на прошлой неделе", "m1": "в прошлом месяце", "y1": "в прошлом году",
        "u": [["секунда", "секунды", "секунд"], ["минута", "минуты", "минут"],
              ["час", "часа", "часов"], ["день", "дня", "дней"],
              ["неделя", "недели", "недель"], ["месяц", "месяца", "месяцев"],
              ["год", "года", "лет"]],
        "ds": "%d.%m", "df": "%d.%m.%Y", "st": "с %s", "sd": "с %s",
    },
    "pl": {
        "months": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
                   "sierpnia", "września", "października", "listopada", "grudnia"],
        "months3": ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis",
                    "gru"],
        "days": ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"],
        "days3": ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."],
        "dec": ",", "thou": " ", "pl": "pl",
        "past": "%s temu", "now": "teraz", "d1": "wczoraj", "d2": "przedwczoraj",
        "w1": "w zeszłym tygodniu", "m1": "w zeszłym miesiącu", "y1": "w zeszłym roku",
        "u": [["sekunda", "sekundy", "sekund"], ["minuta", "minuty", "minut"],
              ["godzina", "godziny", "godzin"], ["dzień", "dni", "dni"],
              ["tydzień", "tygodnie", "tygodni"], ["miesiąc", "miesiące", "miesięcy"],
              ["rok", "lata", "lat"]],
        "ds": "%d.%m", "df": "%d.%m.%Y", "st": "od %s", "sd": "od %s",
    },
    "hu": {
        "months": ["január", "február", "március", "április", "május", "június", "július",
                   "augusztus", "szeptember", "október", "november", "december"],
        "months3": ["jan.", "febr.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.",
                    "okt.", "nov.", "dec."],
        "days": ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"],
        "days3": ["H", "K", "Sze", "Cs", "P", "Szo", "V"],
        "dec": ",", "thou": " ", "pl": "en",
        "past": "%s ezelőtt", "now": "most", "d1": "tegnap", "d2": "tegnapelőtt",
        "w1": "múlt héten", "m1": "múlt hónapban", "y1": "tavaly",
        # no plural after a number in Hungarian
        "u": [["másodperc", "másodperc"], ["perc", "perc"], ["óra", "óra"], ["nap", "nap"],
              ["hét", "hét"], ["hónap", "hónap"], ["év", "év"]],
        "ds": "%m. %d.", "df": "%Y. %m. %d.", "st": "%s óta", "sd": "%s óta",
    },
}
D = LANGS["en"]


def set_language(code):
    """Language of Home Assistant ("fr", "pt-BR"...) -> the supported language, else English.
    Returns True if the language changed."""
    global LANG, D
    base = str(code or "").replace("_", "-").split("-")[0].lower()
    new = base if base in LANGS else "en"
    changed = new != LANG
    LANG, D = new, LANGS[new]
    return changed


def plural_index(rule, n):
    """Index of the plural form of n in the list of forms of a unit."""
    if rule == "fr":
        return 0 if n < 2 else 1
    if rule in ("ru", "pl"):
        if n == 1 and rule == "pl":
            return 0
        if rule == "ru" and n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    return 0 if n == 1 else 1


def _count(unit, n):
    forms = D["u"][unit]
    return "%d %s" % (n, forms[min(plural_index(D["pl"], n), len(forms) - 1)])


def rel_time(t, now=None, total=False):
    """Elapsed time since t (epoch seconds): "3 minutes ago", "Yesterday"...
    total=True: duration only ("1 month"), like the HA "total" format.
    Same computation as relTime() in s.js, which keeps it up to date."""
    if t is None:
        return "—"
    s = max(0, int((now or time.time()) - t))
    if total:
        for lim, div, u in ((45, 1, 0), (2700, 60, 1), (79200, 3600, 2), (432000, 86400, 3),
                            (2419200, 604800, 4), (31536000, 2592000, 5), (None, 31536000, 6)):
            if lim is None or s < lim:
                return _count(u, max(1, int(round(s / float(div)))) if u else s)
    past = D["past"]
    if s < 45:
        txt = D["now"] if s < 1 else past % _count(0, s)
    elif s < 2700:
        txt = past % _count(1, max(1, int(round(s / 60.0))))
    elif s < 79200:
        txt = past % _count(2, max(1, int(round(s / 3600.0))))
    elif s < 432000:
        d = max(1, int(round(s / 86400.0)))
        txt = D["d1"] if d == 1 else (D["d2"] if d == 2 and D["d2"] else past % _count(3, d))
    elif s < 2419200:
        w = max(1, int(round(s / 604800.0)))
        txt = D["w1"] if w == 1 else past % _count(4, w)
    elif s < 31536000:
        m = max(1, int(round(s / 2592000.0)))
        txt = D["m1"] if m == 1 else past % _count(5, m)
    else:
        y = max(1, int(round(s / 31536000.0)))
        txt = D["y1"] if y == 1 else past % _count(6, y)
    return txt[:1].upper() + txt[1:]


def group_digits(numstr):
    """"1003.5" -> "1 003,5" in the language (decimal point -> decimal separator, thousands
    grouped)."""
    neg = numstr.startswith("-")
    body = numstr[1:] if neg else numstr
    ent, _, dec = body.partition(".")
    if len(ent) > 3 and ent.isdigit():
        parts = []
        while len(ent) > 3:
            parts.insert(0, ent[-3:])
            ent = ent[:-3]
        parts.insert(0, ent)
        ent = D["thou"].join(parts)
    return ("-" if neg else "") + ent + (D["dec"] + dec if "." in body else "")


def date_short(dt):
    return dt.strftime(D["ds"])


def date_full(dt):
    return dt.strftime(D["df"])


def month_name(dt, short=False):
    return D["months3" if short else "months"][dt.month - 1]


def day_name(weekday, short=False):
    """weekday: 0 = Monday (datetime.weekday())."""
    return D["days3" if short else "days"][weekday]


def client_data():
    """What s.js needs (clock and "ago" texts)."""
    return {k: D[k] for k in ("months", "months3", "days", "days3", "pl", "past", "now", "d1", "d2",
                              "w1", "m1", "y1", "u")}
