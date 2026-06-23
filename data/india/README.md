# India manufacturer scraping targets

`manufacturers.csv` — **~95 verified Indian (and global-with-India-ops) manufacturers/suppliers**
across the workplace-fit-out categories the Dsource Studio (GCC) deck spans: seating,
workstations, office furniture, storage, soft seating, acoustics, partitions/glazing, ceilings,
flooring/carpet, laminates/surfaces, lighting, biophilia, signage, contract textiles, ergonomic
accessories. Every URL was verified live; fake/out-of-category names were dropped.

## The key finding — India's price wall is LOWER than the US
Unlike US contract furniture (prices quote-gated everywhere), **a meaningful slice of Indian
suppliers publish INR prices online**, and many run on **Shopify**, which exposes a structured
`/<collection>/products.json` feed — clean, priced product data with near-zero scraping effort.

## Scrape tiers (work top-down)

### Tier 1 — easy: structured + priced (do these first)
- **Shopify `/products.json`** (prices + specs, JSON): Nilkamal, Crompton, Ugaoo, Nurturing Green,
  TrustBasket, Rife, Orient Electric, Steelcase India, Haworth India, Godrej Interio.
- **Other e-commerce with INR prices**: Durian, Human Method Ergo, Ergosphere, Prolegend,
  D'Decor, Royale Touche, S Cube, Havells.
- → fastest path to a real, priced India catalog. Start here.

### Tier 2 — medium: specs in PDFs / prices on marketplaces
- **PDF catalogs + spec sheets** (rich specs, no prices — reuse our pricebook PDF parser):
  Transteel, Anutone, Gyproc, iQubx (STC 54), Interface, Welspun, Tarkett, Forbo, Shaw Contract,
  Greenlam, Merino (TVOC values!), Advance Laminates, Signify, Wipro Lighting, GM Modular,
  Halonix, Bajaj.
- **IndiaMART / TradeIndia storefronts** carry INR prices + images for B2B makers whose own sites
  don't: Methodex, Decibels, Responsive Industries, Narain, Usha Shriram (steel).
- WELL/sustainability data is genuinely present here (FSC, Greenguard, GREENPRO, IGBC, LEED,
  EPDs, TVOC) — feeds the wellcatalog layer for real.

### Tier 3 — hard: WAF / bot-blocked (need headless browser + proxies)
Wipro Furniture, Damro, USG Boral, Saint-Gobain (Glass + Gyproc variants), Armstrong, Bajaj
(pages), Jaquar (Cloudflare), Merino (homepage), Responsive (homepage). Use Playwright headless;
several still expose their data via PDFs or IndiaMART mirrors, so prefer those over fighting the WAF.

### Skip / deprioritize — thin marketing sites, low data value
AFC, Whitemark, Princeboard, Virgo, Aerolam, Vantage, CRM India, Treemendous, etc.

## Honest caveats
- "Verified live" = homepage fetched and confirmed real; depth of product data varies (flagged
  per row in `has_prices` / `data_type` / `scrape`).
- Global brands (Herman Miller India, Knoll, Framery, Sound Seal) reach India via dealers and
  often lack a priced India storefront — treat as spec sources, not price sources.
- Reusing manufacturer catalog content commercially still needs the same legal review flagged for
  the US (facts are fine; creative copy/images are not).

## Suggested first build
A **Shopify `/products.json` ingester** (Tier 1) → real priced India products into the catalog,
mirroring how the US price-book parser works — then the PDF-spec parser (Tier 2) for the
materials/WELL data.
