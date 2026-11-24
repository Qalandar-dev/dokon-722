"""Administrative divisions of Uzbekistan — seed data, version 1.

FROZEN: migrations import this module. Never edit it in place. To correct the list,
create ``uzbekistan_v2.py`` with a new migration that applies the difference.
Administrators can also rename, add or deactivate entries from the admin panel.

Names are in Uzbek Latin using the official modifier letter ʻ (U+02BB) in oʻ/gʻ.
Codes: regions use ISO 3166-2:UZ; districts use ``<region code>-<nn>`` in list order.

Source: compiled from the publicly known division of Uzbekistan (12 viloyats, the
Republic of Karakalpakstan and Tashkent city with their tumans and cities). Boundaries
change occasionally (new tumans are created), so verify against the official SOATO
classifier before relying on it for anything legal.
"""

from __future__ import annotations

from typing import Final

# (region code, region name, [(district name, kind), ...]); kind is "city" or "district"
C, D = "city", "district"

REGIONS: Final[list[tuple[str, str, list[tuple[str, str]]]]] = [
    (
        "UZ-TK",
        "Toshkent shahri",
        [
            ("Bektemir tumani", D),
            ("Chilonzor tumani", D),
            ("Mirobod tumani", D),
            ("Mirzo Ulugʻbek tumani", D),
            ("Olmazor tumani", D),
            ("Sergeli tumani", D),
            ("Shayxontohur tumani", D),
            ("Uchtepa tumani", D),
            ("Yakkasaroy tumani", D),
            ("Yangihayot tumani", D),
            ("Yashnobod tumani", D),
            ("Yunusobod tumani", D),
        ],
    ),
    (
        "UZ-TO",
        "Toshkent viloyati",
        [
            ("Nurafshon shahri", C),
            ("Angren shahri", C),
            ("Bekobod shahri", C),
            ("Chirchiq shahri", C),
            ("Olmaliq shahri", C),
            ("Ohangaron shahri", C),
            ("Yangiyoʻl shahri", C),
            ("Bekobod tumani", D),
            ("Boʻka tumani", D),
            ("Boʻstonliq tumani", D),
            ("Chinoz tumani", D),
            ("Ohangaron tumani", D),
            ("Oqqoʻrgʻon tumani", D),
            ("Oʻrtachirchiq tumani", D),
            ("Parkent tumani", D),
            ("Piskent tumani", D),
            ("Qibray tumani", D),
            ("Quyichirchiq tumani", D),
            ("Toshkent tumani", D),
            ("Yangiyoʻl tumani", D),
            ("Yuqorichirchiq tumani", D),
            ("Zangiota tumani", D),
        ],
    ),
    (
        "UZ-AN",
        "Andijon viloyati",
        [
            ("Andijon shahri", C),
            ("Xonobod shahri", C),
            ("Andijon tumani", D),
            ("Asaka tumani", D),
            ("Baliqchi tumani", D),
            ("Boʻston tumani", D),
            ("Buloqboshi tumani", D),
            ("Izboskan tumani", D),
            ("Jalaquduq tumani", D),
            ("Marhamat tumani", D),
            ("Oltinkoʻl tumani", D),
            ("Paxtaobod tumani", D),
            ("Qoʻrgʻontepa tumani", D),
            ("Shahrixon tumani", D),
            ("Ulugʻnor tumani", D),
            ("Xoʻjaobod tumani", D),
        ],
    ),
    (
        "UZ-FA",
        "Fargʻona viloyati",
        [
            ("Fargʻona shahri", C),
            ("Margʻilon shahri", C),
            ("Qoʻqon shahri", C),
            ("Quvasoy shahri", C),
            ("Bagʻdod tumani", D),
            ("Beshariq tumani", D),
            ("Buvayda tumani", D),
            ("Dangʻara tumani", D),
            ("Fargʻona tumani", D),
            ("Furqat tumani", D),
            ("Oltiariq tumani", D),
            ("Oʻzbekiston tumani", D),
            ("Qoʻshtepa tumani", D),
            ("Quva tumani", D),
            ("Rishton tumani", D),
            ("Soʻx tumani", D),
            ("Toshloq tumani", D),
            ("Uchkoʻprik tumani", D),
            ("Yozyovon tumani", D),
        ],
    ),
    (
        "UZ-NG",
        "Namangan viloyati",
        [
            ("Namangan shahri", C),
            ("Chortoq tumani", D),
            ("Chust tumani", D),
            ("Kosonsoy tumani", D),
            ("Mingbuloq tumani", D),
            ("Namangan tumani", D),
            ("Norin tumani", D),
            ("Pop tumani", D),
            ("Toʻraqoʻrgʻon tumani", D),
            ("Uchqoʻrgʻon tumani", D),
            ("Uychi tumani", D),
            ("Yangiqoʻrgʻon tumani", D),
        ],
    ),
    (
        "UZ-SA",
        "Samarqand viloyati",
        [
            ("Samarqand shahri", C),
            ("Kattaqoʻrgʻon shahri", C),
            ("Bulungʻur tumani", D),
            ("Ishtixon tumani", D),
            ("Jomboy tumani", D),
            ("Kattaqoʻrgʻon tumani", D),
            ("Narpay tumani", D),
            ("Nurobod tumani", D),
            ("Oqdaryo tumani", D),
            ("Pastdargʻom tumani", D),
            ("Paxtachi tumani", D),
            ("Payariq tumani", D),
            ("Qoʻshrabot tumani", D),
            ("Samarqand tumani", D),
            ("Toyloq tumani", D),
            ("Urgut tumani", D),
        ],
    ),
    (
        "UZ-BU",
        "Buxoro viloyati",
        [
            ("Buxoro shahri", C),
            ("Kogon shahri", C),
            ("Buxoro tumani", D),
            ("Gʻijduvon tumani", D),
            ("Jondor tumani", D),
            ("Kogon tumani", D),
            ("Olot tumani", D),
            ("Peshku tumani", D),
            ("Qorakoʻl tumani", D),
            ("Qorovulbozor tumani", D),
            ("Romitan tumani", D),
            ("Shofirkon tumani", D),
            ("Vobkent tumani", D),
        ],
    ),
    (
        "UZ-NW",
        "Navoiy viloyati",
        [
            ("Navoiy shahri", C),
            ("Zarafshon shahri", C),
            ("Gʻozgʻon shahri", C),
            ("Karmana tumani", D),
            ("Konimex tumani", D),
            ("Navbahor tumani", D),
            ("Nurota tumani", D),
            ("Qiziltepa tumani", D),
            ("Tomdi tumani", D),
            ("Uchquduq tumani", D),
            ("Xatirchi tumani", D),
        ],
    ),
    (
        "UZ-QA",
        "Qashqadaryo viloyati",
        [
            ("Qarshi shahri", C),
            ("Shahrisabz shahri", C),
            ("Chiroqchi tumani", D),
            ("Dehqonobod tumani", D),
            ("Gʻuzor tumani", D),
            ("Kasbi tumani", D),
            ("Kitob tumani", D),
            ("Koson tumani", D),
            ("Koʻkdala tumani", D),
            ("Mirishkor tumani", D),
            ("Muborak tumani", D),
            ("Nishon tumani", D),
            ("Qamashi tumani", D),
            ("Qarshi tumani", D),
            ("Shahrisabz tumani", D),
            ("Yakkabogʻ tumani", D),
        ],
    ),
    (
        "UZ-SU",
        "Surxondaryo viloyati",
        [
            ("Termiz shahri", C),
            ("Angor tumani", D),
            ("Bandixon tumani", D),
            ("Boysun tumani", D),
            ("Denov tumani", D),
            ("Jarqoʻrgʻon tumani", D),
            ("Muzrabot tumani", D),
            ("Oltinsoy tumani", D),
            ("Qiziriq tumani", D),
            ("Qumqoʻrgʻon tumani", D),
            ("Sariosiyo tumani", D),
            ("Sherobod tumani", D),
            ("Shoʻrchi tumani", D),
            ("Termiz tumani", D),
            ("Uzun tumani", D),
        ],
    ),
    (
        "UZ-JI",
        "Jizzax viloyati",
        [
            ("Jizzax shahri", C),
            ("Arnasoy tumani", D),
            ("Baxmal tumani", D),
            ("Doʻstlik tumani", D),
            ("Forish tumani", D),
            ("Gʻallaorol tumani", D),
            ("Mirzachoʻl tumani", D),
            ("Paxtakor tumani", D),
            ("Sharof Rashidov tumani", D),
            ("Yangiobod tumani", D),
            ("Zafarobod tumani", D),
            ("Zarbdor tumani", D),
            ("Zomin tumani", D),
        ],
    ),
    (
        "UZ-SI",
        "Sirdaryo viloyati",
        [
            ("Guliston shahri", C),
            ("Shirin shahri", C),
            ("Yangiyer shahri", C),
            ("Boyovut tumani", D),
            ("Guliston tumani", D),
            ("Mirzaobod tumani", D),
            ("Oqoltin tumani", D),
            ("Sardoba tumani", D),
            ("Sayxunobod tumani", D),
            ("Sirdaryo tumani", D),
            ("Xovos tumani", D),
        ],
    ),
    (
        "UZ-XO",
        "Xorazm viloyati",
        [
            ("Urganch shahri", C),
            ("Xiva shahri", C),
            ("Bogʻot tumani", D),
            ("Gurlan tumani", D),
            ("Hazorasp tumani", D),
            ("Qoʻshkoʻpir tumani", D),
            ("Shovot tumani", D),
            ("Tuproqqalʼa tumani", D),
            ("Urganch tumani", D),
            ("Xiva tumani", D),
            ("Xonqa tumani", D),
            ("Yangiariq tumani", D),
            ("Yangibozor tumani", D),
        ],
    ),
    (
        "UZ-QR",
        "Qoraqalpogʻiston Respublikasi",
        [
            ("Nukus shahri", C),
            ("Amudaryo tumani", D),
            ("Beruniy tumani", D),
            ("Boʻzatov tumani", D),
            ("Chimboy tumani", D),
            ("Ellikqalʼa tumani", D),
            ("Kegeyli tumani", D),
            ("Moʻynoq tumani", D),
            ("Nukus tumani", D),
            ("Qanlikoʻl tumani", D),
            ("Qoraoʻzak tumani", D),
            ("Qoʻngʻirot tumani", D),
            ("Shumanay tumani", D),
            ("Taxiatosh tumani", D),
            ("Taxtakoʻpir tumani", D),
            ("Toʻrtkoʻl tumani", D),
            ("Xoʻjayli tumani", D),
        ],
    ),
]


def region_rows() -> list[dict[str, object]]:
    return [
        {"id": i, "code": code, "name": name, "sort_order": i}
        for i, (code, name, _) in enumerate(REGIONS, start=1)
    ]


def district_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    next_id = 1
    for region_id, (code, _, districts) in enumerate(REGIONS, start=1):
        for n, (name, kind) in enumerate(districts, start=1):
            rows.append(
                {
                    "id": next_id,
                    "region_id": region_id,
                    "code": f"{code}-{n:02d}",
                    "name": name,
                    "kind": kind,
                    "sort_order": n,
                }
            )
            next_id += 1
    return rows
