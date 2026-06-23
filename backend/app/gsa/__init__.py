"""GSA Advantage furniture price-list connector.

Legitimately acquires REAL US office-furniture data (manufacturer part numbers +
GSA contract / net prices) from public GSA Advantage "Authorized FSS Schedule Price
List" pages — no dealer / login required.

Furniture lives under MAS SIN 33721 (Office Furniture). Each contractor's price list is
public at:

    https://www.gsaadvantage.gov/ref_text/<CONTRACT>/<CONTRACT>_online.htm

Those pages are JS / WAF-gated (a plain HTTP GET returns an empty body), so the scraper
uses a headless browser (Playwright). The parser is network-independent and runs against
saved HTML so it is fully testable offline.

Legal posture (brief):
  * GSA Advantage is a public US-government catalog; access requires no login and
    robots.txt is permissive for ref_text price lists.
  * The data we extract — part numbers and government net prices — are *facts*, which are
    not copyrightable (Feist v. Rural Telephone).
  * We deliberately do NOT redistribute manufacturer creative content (marketing copy,
    images, long descriptions). We keep the part number, a short description, and price.
"""

from .parser import GsaPriceRecord, parse_price_list
from .scraper import GsaScraperError, fetch_price_list, price_list_url

__all__ = [
    "GsaPriceRecord",
    "parse_price_list",
    "GsaScraperError",
    "fetch_price_list",
    "price_list_url",
]
