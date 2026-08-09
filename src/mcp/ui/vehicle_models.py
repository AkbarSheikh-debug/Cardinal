"""Resolving a listing to the 3D asset that stands for it (D-060).

The catalogue carries 146 distinct `(brand, model)` pairs across 12 categories (PHASE-1), and
gate 6.7 caps the whole shipped asset bundle at 16 MB -- so "a GLB per listing" was never the
shape of this. What ships instead is a three-step fallback, most specific first:

1. **`vehicles/<slug>.glb`** -- a hand-sourced model of that actual car, for the pairs a demo
   is most likely to surface. Present only for the slugs in `VEHICLE_SLUGS`.
2. **`silhouettes/<category>.glb`** -- one body-style shape per `VehicleCategory`, so an
   unsourced car still renders as something with the right proportions rather than nothing.
3. **`powertrain/<archetype>.glb`** -- P6's existing eight cutaways, which are about the
   engine rather than the body and are what `render_detail` already shows.

Every step is a pure `(brand, model, category) -> path` lookup with no filesystem access:
which files exist is a deployment fact, and a compiler that stats the disk stops being the
pure function PHASE-6 SS4 requires. `scripts/check_vehicle_assets.py` is what reconciles this
table against `web/public/models/` and reports the gap.

Nothing here reaches a manufacturer's endpoint or serves their imagery (CONSTITUTION I.3);
these are third-party or hand-made models, and every surface that shows one labels it
"representative" the way `PowertrainExplainer` already does.
"""

from __future__ import annotations

import re
import unicodedata

from src.domain.enums import VehicleCategory

ASSET_ROOT = "/models"
VEHICLE_DIR = f"{ASSET_ROOT}/vehicles"
SILHOUETTE_DIR = f"{ASSET_ROOT}/silhouettes"
POWERTRAIN_DIR = f"{ASSET_ROOT}/powertrain"
#: Real reference photos, one per sourced car -- a sibling asset tree to `/models`, not a
#: replacement for it. `vehicle_photo_src` below stands alone: unlike the GLB fallback chain,
#: a car with no photo simply has no photo (`None`), because a photo has no silhouette-style
#: fallback that still makes sense the way a body-style GLB does for a 3D model.
PHOTO_DIR = "/photos"


def slugify(brand: str, model: str) -> str:
    """`("Škoda", "Superb Combi") -> "skoda-superb-combi"`. NFKD-folds diacritics so the
    filename a person types on any keyboard matches the catalogue's own spelling -- the
    catalogue really does carry `Škoda` and `Mégane` (PHASE-1's taxonomy is deliberately
    accurate), and `skoda-octavia.glb` is what someone downloading a model will save.
    """
    raw = f"{brand}-{model}".lower()
    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", folded)).strip("-")


#: The `(brand, model)` pairs with a real per-vehicle GLB under `web/public/models/vehicles/`.
#: Adding a car is two steps and no code change: drop `<slug>.glb` + `<slug>.png` in that
#: directory and add the slug here. `scripts/check_vehicle_assets.py` verifies the two agree.
#:
#: Derived, not guessed: these are exactly the cars the eight scripted demo prompts in
#: `docs/DEMO-SCRIPT.md` put on screen in their top four results, against the default seed.
#: Source all 28 and every card in a scripted run shows that actual car; source none and every
#: card still shows its body-style silhouette. That is the whole point of the fallback tier
#: being required and this one not being.
#:
#: Picking by catalogue frequency instead would have been worse: the most-listed cars in the
#: seed include a Tata Yodha and a Nissan Maxima Platinum, neither of which has a usable
#: downloadable model, so their "coverage" would only ever be theoretical.
#:
#: Off the scripted path this set covers ~30% of the 240 listings. Widening that is additive
#: -- add the slug, drop the two files in -- and `scripts/check_vehicle_assets.py` will tell
#: you what is still missing.
VEHICLE_SLUGS: frozenset[str] = frozenset(
    {
        # -- hatchback, EUR 4.8k-16k ---------------------------------------------------
        "suzuki-swift",
        "kia-rio",
        "renault-clio",
        # -- crossover, EUR 7.5k-26k ---------------------------------------------------
        "suzuki-vitara",
        "toyota-c-hr",
        "skoda-kamiq",
        "peugeot-2008",
        # -- sedan, EUR 7.2k-11k -------------------------------------------------------
        "bmw-3-series",
        "skoda-octavia",
        "volvo-s60",
        "peugeot-508",
        # -- SUV, EUR 10k-21k ----------------------------------------------------------
        "nissan-x-trail",
        "tata-safari",
        "mg-hector",
        "ford-explorer",
        "honda-cr-v",
        # -- electric, EUR 12k-27k -----------------------------------------------------
        "byd-atto-3",
        "peugeot-e-208",
        "kia-ev6",
        "mg-4",
        # -- wagon, EUR 13k-36k --------------------------------------------------------
        "skoda-superb-combi",
        "renault-megane-estate",
        "vw-passat-variant",
        "jaguar-xf-sportbrake",
        # -- sports, the "show me something fun" moment --------------------------------
        "honda-civic-type-r",
        "vw-golf-r",
        "jaguar-f-type-r",
        "nissan-gt-r",
    }
)


#: One real reference photo sourced per pair, independent of `VEHICLE_SLUGS` -- a much wider
#: set (180 of the taxonomy's 180 catalogue pairs at time of writing) because a stock photo is
#: far cheaper to source at scale than a hand-fit GLB. Each slug names a single curated file
#: at `web/public/photos/<slug>.jpg`; `scripts/check_vehicle_assets.py` does not reconcile this
#: set the way it does `VEHICLE_SLUGS` yet -- there is no fallback tier to verify against.
PHOTO_SLUGS: frozenset[str] = frozenset(
    {
        "audi-a4",
        "audi-a4-avant",
        "audi-a5",
        "audi-a5-cabriolet",
        "audi-a8",
        "audi-q4-e-tron",
        "audi-q5",
        "audi-rs5",
        "bmw-3-series",
        "bmw-3-series-touring",
        "bmw-4-series",
        "bmw-7-series",
        "bmw-i4",
        "bmw-m4",
        "bmw-x3",
        "bmw-z4",
        "byd-atto-3",
        "ford-explorer",
        "ford-fiesta",
        "ford-focus-estate",
        "ford-mondeo",
        "ford-mustang",
        "ford-mustang-convertible",
        "ford-mustang-gt",
        "ford-mustang-mach-e",
        "ford-puma",
        "ford-ranger",
        "ford-tourneo",
        "honda-civic",
        "honda-civic-type-r",
        "honda-cr-v",
        "honda-hr-v",
        "honda-jazz",
        "honda-odyssey",
        "honda-prelude",
        "honda-s2000",
        "hyundai-elantra",
        "hyundai-grandeur",
        "hyundai-i20",
        "hyundai-i30-n",
        "hyundai-i30-wagon",
        "hyundai-ioniq-5",
        "hyundai-kona",
        "hyundai-santa-cruz",
        "hyundai-staria",
        "hyundai-tucson",
        "hyundai-veloster",
        "jaguar-f-type",
        "jaguar-f-type-convertible",
        "jaguar-f-type-r",
        "jaguar-xf-sportbrake",
        "jaguar-xj",
        "kia-carnival",
        "kia-ceed-sw",
        "kia-ev6",
        "kia-k5",
        "kia-k8",
        "kia-niro",
        "kia-rio",
        "kia-sportage",
        "kia-stinger",
        "kia-stinger-gt",
        "kia-tasman",
        "mahindra-marazzo",
        "mahindra-scorpio-pik-up",
        "mahindra-xuv700",
        "mazda-2",
        "mazda-6",
        "mazda-6-wagon",
        "mazda-bt-50",
        "mazda-cx-30",
        "mazda-cx-5",
        "mazda-cx-90-signature",
        "mazda-mx-5",
        "mazda-mx-5-rf",
        "mazda-rx-8",
        "mercedes-benz-amg-gt",
        "mercedes-benz-c-class",
        "mercedes-benz-c-class-estate",
        "mercedes-benz-cle",
        "mercedes-benz-eqb",
        "mercedes-benz-glc",
        "mercedes-benz-s-class",
        "mercedes-benz-sl",
        "mercedes-benz-v-class",
        "mercedes-benz-x-class",
        "mg-3",
        "mg-4",
        "mg-extender",
        "mg-hector",
        "mg-maxus-9",
        "mg-zs",
        "nissan-370z-roadster",
        "nissan-400z",
        "nissan-gt-r",
        "nissan-juke",
        "nissan-leaf",
        "nissan-maxima-platinum",
        "nissan-micra",
        "nissan-navara",
        "nissan-primastar",
        "nissan-sentra",
        "nissan-x-trail",
        "peugeot-2008",
        "peugeot-208",
        "peugeot-308-cc",
        "peugeot-308-sw",
        "peugeot-508",
        "peugeot-e-208",
        "peugeot-landtrek",
        "peugeot-rcz",
        "peugeot-traveller",
        "polestar-2",
        "polestar-2-bst",
        "polestar-3",
        "porsche-718-boxster",
        "porsche-718-cayman",
        "porsche-911",
        "porsche-panamera",
        "renault-alaskan",
        "renault-captur",
        "renault-clio",
        "renault-megane-cc",
        "renault-megane-coupe",
        "renault-megane-e-tech",
        "renault-megane-estate",
        "renault-megane-rs",
        "renault-talisman",
        "renault-trafic",
        "skoda-fabia",
        "skoda-kamiq",
        "skoda-kodiaq",
        "skoda-octavia",
        "skoda-superb-combi",
        "suzuki-equator",
        "suzuki-ertiga",
        "suzuki-swift",
        "suzuki-vitara",
        "tata-altroz",
        "tata-nexon",
        "tata-nexon-ev",
        "tata-safari",
        "tata-tigor",
        "tata-winger",
        "tata-yodha",
        "tesla-model-3",
        "tesla-model-3-performance",
        "tesla-model-s",
        "toyota-bz4x",
        "toyota-c-hr",
        "toyota-corolla",
        "toyota-corolla-touring-sports",
        "toyota-crown",
        "toyota-gr86",
        "toyota-gr86-roadster",
        "toyota-gr-supra",
        "toyota-hilux",
        "toyota-proace-verso",
        "toyota-rav4",
        "toyota-yaris",
        "volvo-c70",
        "volvo-c70-cabrio",
        "volvo-ex30",
        "volvo-s60",
        "volvo-s90",
        "volvo-v60",
        "volvo-xc40",
        "volvo-xc60",
        "vw-amarok",
        "vw-arteon",
        "vw-golf-r",
        "vw-id-4",
        "vw-multivan",
        "vw-passat",
        "vw-passat-variant",
        "vw-polo",
        "vw-scirocco",
        "vw-t-roc",
        "vw-t-roc-cabriolet",
        "vw-tiguan",
    }
)


def vehicle_model_src(brand: str, model: str, category: VehicleCategory) -> str:
    """The GLB a card for this listing should show. Always returns a path -- the silhouette
    step means there is no "no model" case for the renderer to branch on.
    """
    slug = slugify(brand, model)
    if slug in VEHICLE_SLUGS:
        return f"{VEHICLE_DIR}/{slug}.glb"
    return f"{SILHOUETTE_DIR}/{category.value}.glb"


def vehicle_poster_src(brand: str, model: str, category: VehicleCategory) -> str:
    """The still shown before the GLB streams. Gate 6.8 requires every `<model-viewer>` to
    carry a poster, and the two always come from the same directory as a matched pair.
    """
    return vehicle_model_src(brand, model, category).removesuffix(".glb") + ".png"


def is_representative(brand: str, model: str) -> bool:
    """True when the card is falling back to a body-style silhouette rather than showing a
    model of this actual car. The UI says so out loud either way -- no GLB is a photograph of
    the specific vehicle on offer -- but a silhouette is a weaker claim than a matched model
    and the label distinguishes them.
    """
    return slugify(brand, model) not in VEHICLE_SLUGS


def vehicle_photo_src(brand: str, model: str) -> str | None:
    """The reference photo for this listing's card, or `None` if this pair was never sourced.

    Unlike `vehicle_model_src`, there is no fallback tier here -- a category-level "generic
    SUV photo" would misrepresent every SUV it stood in for the same way a manufacturer stock
    shot would, so a miss is `None` and the caller decides what a card with no photo looks
    like, rather than this function inventing a plausible-looking wrong answer.
    """
    slug = slugify(brand, model)
    return f"{PHOTO_DIR}/{slug}.jpg" if slug in PHOTO_SLUGS else None
